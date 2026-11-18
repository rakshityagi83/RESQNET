
"""Isolated security tests for the RESQNET login API."""
from csrf_protection import verify_csrf_token
from session_tokens import generate_session_token
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth_api
from account_service import create_user
from database import Base
from models import User, UserSession
from session_service import get_authenticated_user
from session_tokens import hash_session_token


VALID_ORIGIN = "http://localhost:5173"

VALID_CREDENTIALS = {
    "username": "testoperator",
    "password": "secure-example-password-123",
}


@pytest.fixture
def isolated_auth(monkeypatch):
    """Create a fully isolated authentication test application."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    with TestSession.begin() as db:
        create_user(
            db,
            username="testoperator",
            password="secure-example-password-123",
            role="operator",
        )

    monkeypatch.setattr(
        auth_api,
        "SessionLocal",
        TestSession,
    )
        # Unit tests use SQLite; PostgreSQL behavior is tested
    # separately in tests_postgres.
    monkeypatch.setattr(
        auth_api,
        "get_login_client_ip",
        lambda request: "127.0.0.1",
    )

    monkeypatch.setattr(
        auth_api,
        "acquire_login_attempt_locks",
        lambda db, username, client_ip: None,
    )

    monkeypatch.setattr(
        auth_api,
        "login_block_remaining_seconds",
        lambda db, username, client_ip: 0,
    )

    monkeypatch.setattr(
        auth_api,
        "record_failed_login",
        lambda db, username, client_ip: None,
    )

    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", VALID_ORIGIN)
    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "test-only-" + "x" * 48,
    )
    app = FastAPI()
    app.include_router(auth_api.router)

    yield app, TestSession

    engine.dispose()


def login(client, credentials=None, origin=VALID_ORIGIN):
    headers = {}

    if origin is not None:
        headers["Origin"] = origin

    return client.post(
        "/auth/login",
        headers=headers,
        json=credentials or VALID_CREDENTIALS,
    )


def test_successful_login_issues_httponly_cookie(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        response = login(client)

    assert response.status_code == 200

    assert response.json()["user"]["username"] == "testoperator"
    assert response.json()["user"]["role"] == "operator"

    cookie = response.headers["set-cookie"].lower()

    assert "resqnet_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=43200" in cookie

    # The session token must not appear in the JSON body.
    token = response.cookies.get("resqnet_session")
    assert token
    assert token not in response.text


def test_only_hashed_session_token_is_stored(isolated_auth):
    app, TestSession = isolated_auth

    with TestClient(app) as client:
        response = login(client)

    assert response.status_code == 200

    token = response.cookies.get("resqnet_session")

    with TestSession() as db:
        records = db.scalars(select(UserSession)).all()

        assert len(records) == 1
        assert records[0].token_hash == hash_session_token(token)
        assert records[0].token_hash != token

        user = get_authenticated_user(db, token)

        assert user is not None
        assert user.username == "testoperator"


def test_wrong_password_rejected(isolated_auth):
    app, TestSession = isolated_auth

    with TestClient(app) as client:
        response = login(
            client,
            {
                "username": "testoperator",
                "password": "incorrect-password",
            },
        )

    assert response.status_code == 401
    assert "resqnet_session" not in response.cookies

    with TestSession() as db:
        assert db.scalars(select(UserSession)).all() == []


def test_unknown_user_rejected(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        response = login(
            client,
            {
                "username": "unknownuser",
                "password": "secure-example-password-123",
            },
        )

    assert response.status_code == 401
    assert "resqnet_session" not in response.cookies


def test_disabled_account_cannot_login(isolated_auth):
    app, TestSession = isolated_auth

    with TestSession.begin() as db:
        user = db.scalar(
            select(User).where(
                User.username == "testoperator"
            )
        )
        user.is_active = False

    with TestClient(app) as client:
        response = login(client)

    assert response.status_code == 401
    assert "resqnet_session" not in response.cookies


def test_missing_origin_rejected(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        response = login(client, origin=None)

    assert response.status_code == 403
    assert "resqnet_session" not in response.cookies


def test_untrusted_origin_rejected(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        response = login(
            client,
            origin="https://untrusted.example",
        )

    assert response.status_code == 403
    assert "resqnet_session" not in response.cookies


def test_production_cookie_requires_https(
    isolated_auth, monkeypatch
):
    app, _ = isolated_auth

    monkeypatch.setenv("RESQNET_ENV", "production")
    monkeypatch.setenv(
        "FRONTEND_URL",
        "https://resqnet.example",
    )

    with TestClient(app) as client:
        response = login(
            client,
            origin="https://resqnet.example",
        )

    assert response.status_code == 200

    cookie = response.headers["set-cookie"].lower()

    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_session_creation_failure_rolls_back(
    isolated_auth, monkeypatch
):
    app, TestSession = isolated_auth

    original_create_session = auth_api.create_session

    def fail_after_session_creation(db, user_id):
        original_create_session(db, user_id)

        # Simulate an unexpected failure before commit.
        raise RuntimeError("Simulated transaction failure")

    monkeypatch.setattr(
        auth_api,
        "create_session",
        fail_after_session_creation,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = login(client)

    assert response.status_code == 500
    assert "resqnet_session" not in response.cookies

    with TestSession() as db:
        # The failed transaction must not persist a session.
        assert db.scalars(select(UserSession)).all() == []

def test_rate_limited_login_returns_429(
    isolated_auth, monkeypatch
):
    app, TestSession = isolated_auth

    monkeypatch.setattr(
        auth_api,
        "login_block_remaining_seconds",
        lambda db, username, client_ip: 90,
    )

    def authentication_must_not_run(*args):
        raise AssertionError(
            "Blocked credentials must not be authenticated"
        )

    monkeypatch.setattr(
        auth_api,
        "authenticate_user",
        authentication_must_not_run,
    )

    with TestClient(app) as client:
        result = login(client)

    assert result.status_code == 429
    assert result.headers["retry-after"] == "90"
    assert "resqnet_session" not in result.cookies

    with TestSession() as db:
        assert db.scalars(select(UserSession)).all() == []


def test_failed_login_counter_commits_before_401(
    isolated_auth, monkeypatch
):
    from datetime import datetime, timezone
    from models import LoginRateLimit

    app, TestSession = isolated_auth

    test_key = "f" * 64

    def simulate_failure_record(db, username, client_ip):
        db.add(
            LoginRateLimit(
                key_hash=test_key,
                failed_attempts=1,
                window_started_at=datetime.now(timezone.utc),
                blocked_until=None,
            )
        )

    monkeypatch.setattr(
        auth_api,
        "record_failed_login",
        simulate_failure_record,
    )

    with TestClient(app) as client:
        result = login(
            client,
            {
                "username": "testoperator",
                "password": "incorrect-password",
            },
        )

    assert result.status_code == 401
    assert "resqnet_session" not in result.cookies

    # A fresh session confirms the failure was committed.
    with TestSession() as db:
        record = db.get(LoginRateLimit, test_key)
        assert record is not None
        assert record.failed_attempts == 1
        assert db.scalars(select(UserSession)).all() == []

def test_logout_revokes_session_and_clears_cookie(
    isolated_auth,
):
    app, TestSession = isolated_auth

    with TestClient(app) as client:
        login_response = login(client)
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        logout_response = client.post(
            "/auth/logout",
            headers={
                "Origin": VALID_ORIGIN,
                "X-CSRF-Token": login_response.json()["csrf_token"],
            },
        )

        assert logout_response.status_code == 204
        assert logout_response.content == b""

        cookie_header = logout_response.headers[
            "set-cookie"
        ].lower()

        assert "resqnet_session=" in cookie_header
        assert "max-age=0" in cookie_header
        assert client.cookies.get("resqnet_session") is None

    with TestSession() as db:
        record = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )

        assert record is not None
        assert record.revoked_at is not None
        assert get_authenticated_user(db, token) is None


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_logout_rejects_untrusted_origin(
    isolated_auth, origin
):
    app, TestSession = isolated_auth

    with TestClient(app) as client:
        login_response = login(client)
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")

        headers = {}
        if origin is not None:
            headers["Origin"] = origin

        result = client.post(
            "/auth/logout",
            headers=headers,
        )

        assert result.status_code == 403

    # An untrusted request must not revoke the session.
    with TestSession() as db:
        assert get_authenticated_user(db, token) is not None


def test_logout_without_session_is_idempotent(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        first = client.post(
            "/auth/logout",
            headers={"Origin": VALID_ORIGIN},
        )
        second = client.post(
            "/auth/logout",
            headers={"Origin": VALID_ORIGIN},
        )

    assert first.status_code == 204
    assert second.status_code == 204


def test_logout_db_failure_does_not_revoke_session(
    isolated_auth, monkeypatch
):
    app, TestSession = isolated_auth

    original_revoke = auth_api.revoke_session

    def fail_after_revocation(db, token):
        assert original_revoke(db, token) is True
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        auth_api,
        "revoke_session",
        fail_after_revocation,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        login_response = login(client)
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")

        result = client.post(
            "/auth/logout",
            headers={
                "Origin": VALID_ORIGIN,
                "X-CSRF-Token": login_response.json()["csrf_token"],
            },
        )

        assert result.status_code == 500
        assert "set-cookie" not in result.headers

    # The failed transaction must roll back the revocation.
    with TestSession() as db:
        assert get_authenticated_user(db, token) is not None

def test_login_issues_session_bound_csrf_token(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        result = login(client)

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"

    session_token = result.cookies.get("resqnet_session")
    csrf_token = result.json().get("csrf_token")

    assert session_token
    assert csrf_token
    assert csrf_token != session_token

    assert verify_csrf_token(session_token, csrf_token)

    # The token must not work with another browser session.
    another_session = generate_session_token()

    assert not verify_csrf_token(
        another_session,
        csrf_token,
    )

    # The raw session token must never appear in JSON.
    assert session_token not in result.text


def test_missing_csrf_key_rolls_back_login(
    isolated_auth, monkeypatch
):
    app, TestSession = isolated_auth

    monkeypatch.delenv(
        "RESQNET_CSRF_HMAC_KEY",
        raising=False,
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        result = login(client)

    assert result.status_code == 500
    assert "resqnet_session" not in result.cookies

    # CSRF generation failed inside the transaction.
    # No authenticated session should have been committed.
    with TestSession() as db:
        assert db.scalars(select(UserSession)).all() == []


@pytest.mark.parametrize(
    "submitted_token",
    [None, "0" * 64],
)
def test_logout_rejects_missing_or_invalid_csrf(
    isolated_auth, submitted_token
):
    app, TestSession = isolated_auth

    with TestClient(app) as client:
        login_response = login(client)
        assert login_response.status_code == 200

        token = login_response.cookies.get("resqnet_session")
        assert token

        headers = {"Origin": VALID_ORIGIN}

        if submitted_token is not None:
            headers["X-CSRF-Token"] = submitted_token

        response = client.post(
            "/auth/logout",
            headers=headers,
        )

        assert response.status_code == 403
        assert "set-cookie" not in response.headers

    with TestSession() as db:
        assert get_authenticated_user(db, token) is not None


def test_logout_rejects_csrf_from_another_session(
    isolated_auth,
):
    app, TestSession = isolated_auth

    with TestClient(app) as first_client:
        with TestClient(app) as second_client:
            first = login(first_client)
            second = login(second_client)

            assert first.status_code == 200
            assert second.status_code == 200

            first_token = first.cookies.get("resqnet_session")
            second_token = second.cookies.get("resqnet_session")

            assert first_token != second_token

            response = first_client.post(
                "/auth/logout",
                headers={
                    "Origin": VALID_ORIGIN,
                    "X-CSRF-Token": second.json()["csrf_token"],
                },
            )

            assert response.status_code == 403
            assert "set-cookie" not in response.headers

    with TestSession() as db:
        assert get_authenticated_user(db, first_token) is not None
        assert get_authenticated_user(db, second_token) is not None


def test_logout_clears_invalid_session_cookie(isolated_auth):
    app, _ = isolated_auth

    with TestClient(app) as client:
        response = client.post(
            "/auth/logout",
            headers={
                "Origin": VALID_ORIGIN,
                "Cookie": "resqnet_session=invalid-token",
            },
        )

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
