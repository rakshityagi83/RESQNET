
"""Real PostgreSQL integration tests for RESQNET login."""

import os
import uuid
from csrf_protection import verify_csrf_token
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import auth_api
from session_service import get_authenticated_user
from account_service import create_user
from login_rate_limiter import fingerprint_ip, fingerprint_username
from models import LoginRateLimit, User, UserSession
from session_tokens import hash_session_token


TEST_PASSWORD = "secure-postgres-test-password-123"
TEST_ORIGIN = "http://localhost:5173"


@pytest.fixture
def postgres_login(monkeypatch):
    raw_url = os.getenv("RESQNET_PG_TEST_URL")

    if not raw_url:
        pytest.fail("Local PostgreSQL test URL is missing")

    url = make_url(raw_url)

    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "127.0.0.1"
        or url.port != 5432
        or url.database != "resqnet_test_concurrency"
    ):
        pytest.fail("Unsafe database URL. Test cancelled.")

    # Disposable test identity, unique to this test.
    unique_id = uuid.uuid4().hex
    username = "loginpg_" + unique_id[:20]
    client_ip = (
        f"2001:db8::{unique_id[:4]}:{unique_id[4:8]}"
    )

    monkeypatch.setenv(
         "RESQNET_CSRF_HMAC_KEY",
         "test-only-" + "x" * 48,
    )
    monkeypatch.setenv(
        "RESQNET_RATE_LIMIT_HMAC_KEY",
        "test-only-" + "x" * 48,
    )
    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", TEST_ORIGIN)

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    user_id = None

    try:
        # Verify the connected server before creating any records.
        with engine.connect() as conn:
            database, port = conn.execute(
                text(
                    "SELECT current_database(), inet_server_port()"
                )
            ).one()

            revision = conn.scalar(
                text("SELECT version_num FROM alembic_version")
            )

            table_exists = conn.scalar(
                text(
                    "SELECT to_regclass("
                    "'public.login_rate_limits') IS NOT NULL"
                )
            )

            if (
                database != "resqnet_test_concurrency"
                or port != 5432
                or revision != "6da8640f44e0"
                or not table_exists
            ):
                pytest.fail("Unexpected PostgreSQL database state")

        TestSession = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )

        with TestSession.begin() as db:
            user = create_user(
                db,
                username=username,
                password=TEST_PASSWORD,
                role="operator",
            )
            user_id = user.id

        monkeypatch.setattr(
            auth_api,
            "SessionLocal",
            TestSession,
        )

        # Only the ASGI client-IP extraction is substituted here.
        # All PostgreSQL rate-limit and locking functions are real.
        monkeypatch.setattr(
            auth_api,
            "get_login_client_ip",
            lambda request: client_ip,
        )

        app = FastAPI()
        app.include_router(auth_api.router)

        yield app, TestSession, username, client_ip, user_id

    finally:
        # Delete only records belonging to this test identity.
        if user_id is not None:
            with sessionmaker(bind=engine).begin() as db:
                db.execute(
                    delete(UserSession).where(
                        UserSession.user_id == user_id
                    )
                )

                db.execute(
                    delete(User).where(User.id == user_id)
                )

                db.execute(
                    delete(LoginRateLimit).where(
                        LoginRateLimit.key_hash.in_([
                            fingerprint_username(username),
                            fingerprint_ip(client_ip),
                        ])
                    )
                )

        engine.dispose()


def send_login(client, username, password):
    return client.post(
        "/auth/login",
        headers={"Origin": TEST_ORIGIN},
        json={
            "username": username,
            "password": password,
        },
    )


def test_wrong_password_persists_postgres_counters(
    postgres_login,
):
    app, TestSession, username, client_ip, _ = postgres_login

    with TestClient(app) as client:
        response = send_login(
            client,
            username,
            "incorrect-password",
        )

    assert response.status_code == 401
    assert "resqnet_session" not in response.cookies

    with TestSession() as db:
        username_record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        ip_record = db.get(
            LoginRateLimit,
            fingerprint_ip(client_ip),
        )

        assert username_record is not None
        assert ip_record is not None
        assert username_record.failed_attempts == 1
        assert ip_record.failed_attempts == 1


def test_five_failures_block_correct_password(
    postgres_login,
):
    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    with TestClient(app) as client:
        for _ in range(5):
            response = send_login(
                client,
                username,
                "incorrect-password",
            )
            assert response.status_code == 401

        blocked = send_login(
            client,
            username,
            TEST_PASSWORD,
        )

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "resqnet_session" not in blocked.cookies

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )

        assert record.failed_attempts == 5
        assert record.blocked_until is not None

        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert sessions == []


def test_valid_login_creates_postgres_session(
    postgres_login,
):
    app, TestSession, username, _, user_id = postgres_login

    with TestClient(app) as client:
        response = send_login(
            client,
            username,
            TEST_PASSWORD,
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == username
    assert response.json()["user"]["role"] == "operator"

    cookie = response.cookies.get("resqnet_session")
    assert cookie is not None
    csrf_token = response.json()["csrf_token"]

    assert verify_csrf_token(cookie, csrf_token)
    assert response.headers["cache-control"] == "no-store"

    with TestSession() as db:
        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert len(sessions) == 1
        assert sessions[0].token_hash == hash_session_token(
            cookie
        )
        assert sessions[0].token_hash != cookie

def test_concurrent_login_requests_respect_rate_limit(
    postgres_login,
):
    """Simultaneous login attempts cannot bypass the threshold."""

    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    number_of_attempts = 8
    barrier = Barrier(number_of_attempts)

    def attempt_login():
        # Give each worker its own HTTP test client.
        with TestClient(app) as client:
            barrier.wait(timeout=20)

            response = send_login(
                client,
                username,
                "incorrect-password",
            )

            return {
                "status": response.status_code,
                "retry_after": response.headers.get("retry-after"),
                "has_cookie": (
                    "resqnet_session" in response.cookies
                ),
            }

    with ThreadPoolExecutor(
        max_workers=number_of_attempts
    ) as executor:
        futures = [
            executor.submit(attempt_login)
            for _ in range(number_of_attempts)
        ]

        results = [
            future.result(timeout=60)
            for future in futures
        ]

    status_codes = sorted(
        result["status"] for result in results
    )

    # Exactly five failures are accepted before blocking.
    assert status_codes == [401] * 5 + [429] * 3

    # Blocked responses must include Retry-After.
    for result in results:
        assert result["has_cookie"] is False

        if result["status"] == 429:
            assert int(result["retry_after"]) > 0

    # Verify the actual persisted PostgreSQL records.
    with TestSession() as db:
        username_record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )

        ip_record = db.get(
            LoginRateLimit,
            fingerprint_ip(client_ip),
        )

        assert username_record is not None
        assert ip_record is not None

        assert username_record.failed_attempts == 5
        assert ip_record.failed_attempts == 5

        assert username_record.blocked_until is not None

        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert sessions == []

def test_postgres_logout_revokes_session(postgres_login):
    """Logout must permanently invalidate the database session."""
    app, TestSession, username, _, _ = postgres_login

    with TestClient(app) as client:
        login_response = send_login(
            client, username, TEST_PASSWORD
        )
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        logout_response = client.post(
            "/auth/logout",
            headers={
                "Origin": TEST_ORIGIN,
                "X-CSRF-Token": login_response.json()["csrf_token"],
            },
        )

        assert logout_response.status_code == 204
        assert logout_response.content == b""
        assert client.cookies.get("resqnet_session") is None

        # Repeating logout must also be harmless.
        repeated = client.post(
            "/auth/logout",
            headers={"Origin": TEST_ORIGIN},
        )
        assert repeated.status_code == 204

    with TestSession() as db:
        record = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )

        assert record is not None
        assert record.revoked_at is not None
        assert get_authenticated_user(db, token) is None


def test_postgres_logout_rejects_untrusted_origin(
    postgres_login,
):
    """An untrusted origin cannot revoke another user's session."""
    app, TestSession, username, _, _ = postgres_login

    with TestClient(app) as client:
        login_response = send_login(
            client, username, TEST_PASSWORD
        )
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        response = client.post(
            "/auth/logout",
            headers={"Origin": "https://untrusted.example"},
        )

        assert response.status_code == 403

    with TestSession() as db:
        assert get_authenticated_user(db, token) is not None


def test_postgres_logout_failure_rolls_back(
    postgres_login, monkeypatch
):
    """A database exception must not partially revoke a session."""
    app, TestSession, username, _, _ = postgres_login

    original_revoke = auth_api.revoke_session

    def simulate_failure(db, token):
        assert original_revoke(db, token) is True
        raise RuntimeError("Simulated PostgreSQL failure")

    monkeypatch.setattr(
        auth_api,
        "revoke_session",
        simulate_failure,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        login_response = send_login(
            client, username, TEST_PASSWORD
        )
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        response = client.post(
            "/auth/logout",
            headers={
                "Origin": TEST_ORIGIN,
                "X-CSRF-Token": login_response.json()["csrf_token"],
            },
        )

        assert response.status_code == 500
        assert "set-cookie" not in response.headers

    with TestSession() as db:
        # Revocation must have been rolled back.
        assert get_authenticated_user(db, token) is not None


@pytest.mark.parametrize(
    "submitted_token",
    [None, "0" * 64],
)
def test_postgres_logout_rejects_missing_or_invalid_csrf(
    postgres_login, submitted_token
):
    app, TestSession, username, _, _ = postgres_login

    with TestClient(app) as client:
        login_response = send_login(
            client, username, TEST_PASSWORD
        )

        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        headers = {"Origin": TEST_ORIGIN}

        if submitted_token is not None:
            headers["X-CSRF-Token"] = submitted_token

        response = client.post(
            "/auth/logout",
            headers=headers,
        )

        assert response.status_code == 403
        assert "set-cookie" not in response.headers
        assert client.cookies.get("resqnet_session") == token

    with TestSession() as db:
        assert get_authenticated_user(db, token) is not None

        record = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )

        assert record is not None
        assert record.revoked_at is None


def test_postgres_logout_rejects_cross_session_csrf(
    postgres_login,
):
    app, TestSession, username, _, _ = postgres_login

    with TestClient(app) as first_client:
        with TestClient(app) as second_client:
            first = send_login(
                first_client, username, TEST_PASSWORD
            )
            second = send_login(
                second_client, username, TEST_PASSWORD
            )

            assert first.status_code == 200
            assert second.status_code == 200

            first_token = first.cookies.get("resqnet_session")
            second_token = second.cookies.get("resqnet_session")

            assert first_token
            assert second_token
            assert first_token != second_token

            response = first_client.post(
                "/auth/logout",
                headers={
                    "Origin": TEST_ORIGIN,
                    "X-CSRF-Token": second.json()["csrf_token"],
                },
            )

            assert response.status_code == 403
            assert "set-cookie" not in response.headers

    with TestSession() as db:
        assert get_authenticated_user(db, first_token) is not None
        assert get_authenticated_user(db, second_token) is not None
