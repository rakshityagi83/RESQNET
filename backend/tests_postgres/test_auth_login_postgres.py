
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
                or revision != "8f27c4b19d62"
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


@pytest.fixture
def postgres_write_app(postgres_login, monkeypatch):
    from fastapi import Depends
    import session_authorization

    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    monkeypatch.setattr(
        session_authorization,
        "SessionLocal",
        TestSession,
    )

    executed = []

    @app.post("/test/admin-write")
    def admin_write(
        principal=Depends(
            session_authorization.require_admin_write
        ),
    ):
        executed.append("admin")
        return {"role": principal.role}

    @app.post("/test/operator-write")
    def operator_write(
        principal=Depends(
            session_authorization.require_operator_write
        ),
    ):
        executed.append("operator")
        return {"role": principal.role}

    return app, TestSession, username, user_id, executed


@pytest.mark.parametrize(
    "role, endpoint, expected_status",
    [
        ("admin", "admin", 200),
        ("admin", "operator", 200),
        ("operator", "operator", 200),
        ("operator", "admin", 403),
    ],
)
def test_postgres_session_write_permissions(
    postgres_write_app, role, endpoint, expected_status
):
    app, TestSession, username, user_id, executed = (
        postgres_write_app
    )

    # Modify only the disposable test account.
    with TestSession.begin() as db:
        user = db.get(User, user_id)
        user.role = role

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        response = client.post(
            "/test/" + endpoint + "-write",
            headers={
                "Origin": TEST_ORIGIN,
                "X-CSRF-Token": authenticated.json()["csrf_token"],
            },
        )

    assert response.status_code == expected_status

    if expected_status == 200:
        assert executed == [endpoint]
    else:
        assert executed == []


@pytest.mark.parametrize(
    "condition",
    [
        "missing_csrf",
        "invalid_csrf",
        "cross_session_csrf",
        "untrusted_origin",
    ],
)
def test_postgres_session_write_rejects_unsafe_requests(
    postgres_write_app, condition
):
    app, TestSession, username, user_id, executed = (
        postgres_write_app
    )

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        headers = {
            "Origin": TEST_ORIGIN,
            "X-CSRF-Token": authenticated.json()["csrf_token"],
        }

        if condition == "missing_csrf":
            headers.pop("X-CSRF-Token")

        elif condition == "invalid_csrf":
            headers["X-CSRF-Token"] = "0" * 64

        elif condition == "cross_session_csrf":
            with TestClient(app) as another_client:
                another = send_login(
                    another_client,
                    username,
                    TEST_PASSWORD,
                )

                assert another.status_code == 200

                headers["X-CSRF-Token"] = (
                    another.json()["csrf_token"]
                )

        elif condition == "untrusted_origin":
            headers["Origin"] = "https://untrusted.example"

        response = client.post(
            "/test/operator-write",
            headers=headers,
        )

    assert response.status_code == 403
    assert executed == []


def test_postgres_session_write_rejects_revoked_session(
    postgres_write_app,
):
    app, TestSession, username, user_id, executed = (
        postgres_write_app
    )

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        token = authenticated.cookies.get("resqnet_session")
        assert token

        headers = {
            "Origin": TEST_ORIGIN,
            "X-CSRF-Token": authenticated.json()["csrf_token"],
        }

        logout = client.post(
            "/auth/logout",
            headers=headers,
        )

        assert logout.status_code == 204

        # Simulate someone replaying the revoked session cookie.
        client.cookies.set("resqnet_session", token)

        response = client.post(
            "/test/operator-write",
            headers=headers,
        )

        assert response.status_code == 401

    assert executed == []

    with TestSession() as db:
        assert get_authenticated_user(db, token) is None


def test_postgres_session_write_enforces_role_changes(
    postgres_write_app,
):
    app, TestSession, username, user_id, executed = (
        postgres_write_app
    )

    with TestSession.begin() as db:
        db.get(User, user_id).role = "admin"

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200
        assert authenticated.json()["user"]["role"] == "admin"

        headers = {
            "Origin": TEST_ORIGIN,
            "X-CSRF-Token": authenticated.json()["csrf_token"],
        }

        before = client.post(
            "/test/admin-write",
            headers=headers,
        )

        assert before.status_code == 200

        # Remove administrative permissions from the account.
        with TestSession.begin() as db:
            db.get(User, user_id).role = "operator"

        after = client.post(
            "/test/admin-write",
            headers=headers,
        )

        assert after.status_code == 403

        operator = client.post(
            "/test/operator-write",
            headers=headers,
        )

        assert operator.status_code == 200

    assert executed == ["admin", "operator"]


@pytest.fixture
def postgres_protected_routes(postgres_login, monkeypatch):
    import json
    import main
    import session_authorization

    from models import Warehouse, Inventory, Allocation

    auth_app, TestSession, username, _, user_id = postgres_login

    monkeypatch.setattr(main, "SessionLocal", TestSession)

    monkeypatch.setattr(
        session_authorization,
        "SessionLocal",
        TestSession,
    )

    unique = uuid.uuid4().hex
    warehouse_name = "PG Security Test " + unique
    new_name = "PG Registered Test " + unique
    allocation_id = str(uuid.uuid4())
    incident_id = "TEST-" + unique

    monkeypatch.setattr(
        main,
        "fetch_gdacs",
        lambda: [{
            "id": incident_id,
            "location": "Test Location",
            "severity": "Orange",
        }],
    )

    warehouse_id = None

    try:
        with TestSession.begin() as db:
            warehouse = Warehouse(
                name=warehouse_name,
                state="Haryana",
                district="Faridabad",
                verified_by="Automated Test",
            )

            db.add(warehouse)
            db.flush()

            warehouse_id = warehouse.id

            db.add(Inventory(
                warehouse_id=warehouse_id,
                food=100,
                water=200,
                medicine=50,
            ))

            db.add(Allocation(
                id=allocation_id,
                incident_id=incident_id,
                warehouse_id=warehouse_id,
                requirements=json.dumps({
                    "requested": {
                        "food": 40,
                        "water": 60,
                        "medicine": 10,
                    },
                    "allocation": {
                        "food": 40,
                        "water": 60,
                        "medicine": 10,
                    },
                    "shortages": {
                        "food": 0,
                        "water": 0,
                        "medicine": 0,
                    },
                }),
                status="PENDING",
            ))

        yield (
            auth_app, main.app, TestSession,
            username, user_id, warehouse_id,
            allocation_id, incident_id, new_name,
        )

    finally:
        # Clean up only warehouses belonging to this test.
        if warehouse_id is not None:
            with TestSession.begin() as db:
                ids = db.scalars(
                    select(Warehouse.id).where(
                        Warehouse.name.in_([
                            warehouse_name,
                            new_name,
                        ])
                    )
                ).all()

                if ids:
                    db.execute(
                        delete(Allocation).where(
                            Allocation.warehouse_id.in_(ids)
                        )
                    )

                    db.execute(
                        delete(Inventory).where(
                            Inventory.warehouse_id.in_(ids)
                        )
                    )

                    db.execute(
                        delete(Warehouse).where(
                            Warehouse.id.in_(ids)
                        )
                    )


@pytest.mark.parametrize(
    "operation",
    ["register", "inventory", "preview", "approve"],
)
@pytest.mark.parametrize(
    "condition",
    ["admin", "operator", "missing_csrf"],
)
def test_postgres_actual_protected_routes(
    postgres_protected_routes, operation, condition
):
    from models import Warehouse, Inventory, Allocation

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    role = "operator" if condition == "operator" else "admin"

    with TestSession.begin() as db:
        db.get(User, user_id).role = role

    # Authenticate through the real PostgreSQL login endpoint.
    with TestClient(auth_app) as auth_client:
        authenticated = send_login(
            auth_client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        token = authenticated.cookies.get("resqnet_session")
        csrf_token = authenticated.json()["csrf_token"]

        assert token

    headers = {"Origin": TEST_ORIGIN}

    if condition != "missing_csrf":
        headers["X-CSRF-Token"] = csrf_token

    stock = {
        "food": 40,
        "water": 60,
        "medicine": 10,
    }

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", token)

        if operation == "register":
            response = client.post(
                "/warehouses",
                headers=headers,
                json={
                    "name": new_name,
                    "state": "Haryana",
                    "district": "Faridabad",
                    "verified_by": "Automated Test",
                },
            )

        elif operation == "inventory":
            response = client.put(
                f"/warehouses/{warehouse_id}/inventory",
                headers=headers,
                json={
                    **stock,
                    "expected": {
                        "food": 100,
                        "water": 200,
                        "medicine": 50,
                    },
                },
            )

        elif operation == "preview":
            response = client.post(
                "/allocation/preview",
                headers=headers,
                json={
                    "incident_id": incident_id,
                    "warehouse_id": warehouse_id,
                    **stock,
                },
            )

        else:
            response = client.post(
                f"/allocation/{allocation_id}/approve",
                headers=headers,
            )

    allowed = (
        condition == "admin"
        or (
            condition == "operator"
            and operation == "preview"
        )
    )

    assert response.status_code == (200 if allowed else 403)

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        allocation = db.get(Allocation, allocation_id)

        registered = db.scalar(
            select(Warehouse).where(
                Warehouse.name == new_name
            )
        )

        allocations = db.scalars(
            select(Allocation).where(
                Allocation.warehouse_id == warehouse_id
            )
        ).all()

        actual_stock = (
            inventory.food,
            inventory.water,
            inventory.medicine,
        )

        if not allowed:
            assert registered is None
            assert actual_stock == (100, 200, 50)
            assert allocation.status == "PENDING"
            assert len(allocations) == 1
            return

        if operation == "register":
            assert registered is not None

            new_inventory = db.get(
                Inventory, registered.id
            )

            assert (
                new_inventory.food,
                new_inventory.water,
                new_inventory.medicine,
            ) == (0, 0, 0)

            assert actual_stock == (100, 200, 50)

        elif operation == "inventory":
            assert actual_stock == (40, 60, 10)

        elif operation == "preview":
            assert len(allocations) == 2

            preview = db.get(
                Allocation,
                response.json()["allocation_id"],
            )

            assert preview.status == "PENDING"
            assert actual_stock == (100, 200, 50)

        elif operation == "approve":
            assert allocation.status == "APPROVED"
            assert actual_stock == (60, 140, 40)


@pytest.fixture
def postgres_session_profile(postgres_login, monkeypatch):
    import session_authorization

    app, TestSession, username, _, user_id = postgres_login

    monkeypatch.setattr(
        session_authorization,
        "SessionLocal",
        TestSession,
    )

    return app, TestSession, username, user_id


def test_postgres_profile_recovers_existing_session(
    postgres_session_profile,
):
    app, TestSession, username, user_id = (
        postgres_session_profile
    )

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        token = authenticated.cookies.get("resqnet_session")
        assert token

        response = client.post(
            "/auth/session",
            headers={"Origin": TEST_ORIGIN},
        )

    assert response.status_code == 200

    assert response.json()["user"] == (
        authenticated.json()["user"]
    )

    assert response.json()["csrf_token"] == (
        authenticated.json()["csrf_token"]
    )

    assert response.headers["Cache-Control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert token not in response.text
    assert "password_hash" not in response.text

    with TestSession() as db:
        records = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert len(records) == 1
        assert get_authenticated_user(db, token) is not None


@pytest.mark.parametrize(
    "origin",
    [None, "https://untrusted.example"],
)
def test_postgres_profile_rejects_untrusted_origin(
    postgres_session_profile, origin
):
    app, _, username, _ = postgres_session_profile

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        headers = {}

        if origin is not None:
            headers["Origin"] = origin

        response = client.post(
            "/auth/session",
            headers=headers,
        )

    assert response.status_code == 403
    assert "csrf_token" not in response.json()


def test_postgres_profile_detects_role_change(
    postgres_session_profile,
):
    app, TestSession, username, user_id = (
        postgres_session_profile
    )

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200
        assert authenticated.json()["user"]["role"] == "operator"

        with TestSession.begin() as db:
            db.get(User, user_id).role = "admin"

        response = client.post(
            "/auth/session",
            headers={"Origin": TEST_ORIGIN},
        )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


@pytest.mark.parametrize(
    "condition",
    ["expired", "revoked", "disabled"],
)
def test_postgres_profile_rejects_unusable_session(
    postgres_session_profile, condition
):
    from datetime import datetime, timedelta, timezone

    app, TestSession, username, user_id = (
        postgres_session_profile
    )

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        with TestSession.begin() as db:
            record = db.scalar(
                select(UserSession).where(
                    UserSession.user_id == user_id
                )
            )

            if condition == "expired":
                record.expires_at = (
                    datetime.now(timezone.utc)
                    - timedelta(seconds=1)
                )

            elif condition == "revoked":
                record.revoked_at = datetime.now(timezone.utc)

            elif condition == "disabled":
                db.get(User, user_id).is_active = False

        response = client.post(
            "/auth/session",
            headers={"Origin": TEST_ORIGIN},
        )

    assert response.status_code == 401
    assert "csrf_token" not in response.json()


def test_postgres_profile_complete_authentication_lifecycle(
    postgres_session_profile,
):
    from fastapi import Depends
    import session_authorization

    app, TestSession, username, user_id = (
        postgres_session_profile
    )

    executed = []

    @app.post("/test/session-lifecycle-write")
    def protected_write(
        principal=Depends(
            session_authorization.require_operator_write
        ),
    ):
        executed.append(principal.user_id)
        return {"role": principal.role}

    with TestClient(app) as client:
        authenticated = send_login(
            client, username, TEST_PASSWORD
        )

        assert authenticated.status_code == 200

        token = authenticated.cookies.get("resqnet_session")
        assert token

        # Simulate a fresh frontend session that has lost
        # its in-memory CSRF token.
        recovered = client.post(
            "/auth/session",
            headers={"Origin": TEST_ORIGIN},
        )

        assert recovered.status_code == 200

        headers = {
            "Origin": TEST_ORIGIN,
            "X-CSRF-Token": recovered.json()["csrf_token"],
        }

        write = client.post(
            "/test/session-lifecycle-write",
            headers=headers,
        )

        assert write.status_code == 200
        assert executed == [user_id]

        logout = client.post(
            "/auth/logout",
            headers=headers,
        )

        assert logout.status_code == 204

        # Attempt to reuse the revoked cookie.
        client.cookies.set("resqnet_session", token)

        recovery_after_logout = client.post(
            "/auth/session",
            headers={"Origin": TEST_ORIGIN},
        )

        assert recovery_after_logout.status_code == 401

        write_after_logout = client.post(
            "/test/session-lifecycle-write",
            headers=headers,
        )

        assert write_after_logout.status_code == 401

    assert executed == [user_id]

    with TestSession() as db:
        assert get_authenticated_user(db, token) is None


def test_postgres_normalized_username_shares_rate_limit(
    postgres_login,
):
    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    variants = [
        username,
        username.upper(),
        "  " + username + "  ",
        username.title(),
        " " + username.upper() + " ",
    ]

    with TestClient(app) as client:
        for variant in variants:
            response = send_login(
                client,
                variant,
                "incorrect-password",
            )

            assert response.status_code == 401

        # Correct credentials must also be blocked.
        blocked = send_login(
            client,
            username.upper(),
            TEST_PASSWORD,
        )

        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0
        assert "set-cookie" not in blocked.headers

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
        assert username_record.failed_attempts == 5
        assert username_record.blocked_until is not None

        assert ip_record is not None
        assert ip_record.failed_attempts == 5

        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert sessions == []


@pytest.mark.parametrize(
    "malformed_username",
    [
        "   ",
        "a" * 33,
        "\u0130" * 80,
    ],
    ids=[
        "whitespace",
        "oversized",
        "unicode-expansion",
    ],
)
def test_postgres_malformed_login_rejected(
    postgres_login, monkeypatch, malformed_username
):
    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    class ForbiddenDatabase:
        def begin(self):
            raise AssertionError(
                "Malformed login reached PostgreSQL"
            )

    monkeypatch.setattr(
        auth_api,
        "SessionLocal",
        ForbiddenDatabase(),
    )

    with TestClient(app) as client:
        response = send_login(
            client,
            malformed_username,
            TEST_PASSWORD,
        )

    assert response.status_code == 422
    assert "set-cookie" not in response.headers

    with TestSession() as db:
        assert db.get(
            LoginRateLimit,
            fingerprint_ip(client_ip),
        ) is None

        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id
            )
        ).all()

        assert sessions == []


def test_postgres_normalized_username_authenticates(
    postgres_login,
):
    app, TestSession, username, client_ip, user_id = (
        postgres_login
    )

    with TestClient(app) as client:
        response = send_login(
            client,
            "  " + username.upper() + "  ",
            TEST_PASSWORD,
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == username
    assert response.json()["user"]["id"] == user_id

    token = response.cookies.get("resqnet_session")
    assert token

    with TestSession() as db:
        user = get_authenticated_user(db, token)

        assert user is not None
        assert user.id == user_id

        assert db.get(
            LoginRateLimit,
            fingerprint_username(username),
        ) is None

        assert db.get(
            LoginRateLimit,
            fingerprint_ip(client_ip),
        ) is None


@pytest.fixture
def postgres_provisioning(postgres_login, monkeypatch):
    import provision_user

    _, TestSession, _, _, _ = postgres_login

    username = "provision_" + uuid.uuid4().hex[:20]

    password = "disposable-provision-password-123"

    def invoke(role, supplied_password=password):
        values = iter([
            supplied_password,
            supplied_password,
        ])

        monkeypatch.setattr(
            provision_user,
            "getpass",
            lambda prompt: next(values),
        )

        return provision_user.main([
            "--username", username,
            "--role", role,
        ])

    try:
        yield TestSession, username, password, invoke

    finally:
        # Remove only the disposable account created
        # specifically for this provisioning test.
        with TestSession.begin() as db:
            user_ids = db.scalars(
                select(User.id).where(
                    User.username == username
                )
            ).all()

            if user_ids:
                db.execute(
                    delete(UserSession).where(
                        UserSession.user_id.in_(user_ids)
                    )
                )

                db.execute(
                    delete(User).where(
                        User.id.in_(user_ids)
                    )
                )


@pytest.mark.parametrize(
    "role",
    ["admin", "operator"],
)
def test_postgres_provisioning_creates_account(
    postgres_provisioning, role, capsys
):
    from account_service import authenticate_user
    from passwords import verify_password

    TestSession, username, password, invoke = (
        postgres_provisioning
    )

    result = invoke(role)

    assert result == 0

    output = capsys.readouterr().out

    assert "Account created successfully" in output
    assert username in output
    assert password not in output
    assert "$argon2id$" not in output

    with TestSession() as db:
        user = db.scalar(
            select(User).where(
                User.username == username
            )
        )

        assert user is not None
        assert user.role == role
        assert user.is_active is True

        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != password

        assert verify_password(
            password,
            user.password_hash,
        )

        authenticated = authenticate_user(
            db, username, password
        )

        assert authenticated is not None
        assert authenticated.id == user.id

        # Provisioning must not automatically create
        # an authenticated browser session.
        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id
            )
        ).all()

        assert sessions == []


def test_postgres_provisioning_rejects_duplicate_username(
    postgres_provisioning,
):
    from passwords import verify_password

    TestSession, username, password, invoke = (
        postgres_provisioning
    )

    assert invoke("operator") == 0

    with TestSession() as db:
        original = db.scalar(
            select(User).where(
                User.username == username
            )
        )

        original_id = original.id
        original_hash = original.password_hash

    # Try to overwrite the existing account with
    # administrative privileges and a different password.
    replacement = "another-test-password-456"

    assert invoke("admin", replacement) == 1

    with TestSession() as db:
        records = db.scalars(
            select(User).where(
                User.username == username
            )
        ).all()

        assert len(records) == 1

        user = records[0]

        assert user.id == original_id
        assert user.role == "operator"
        assert user.password_hash == original_hash

        assert verify_password(
            password,
            user.password_hash,
        )

        assert not verify_password(
            replacement,
            user.password_hash,
        )


def test_postgres_provisioning_rolls_back_failed_creation(
    postgres_provisioning, monkeypatch, capsys
):
    import account_service

    TestSession, username, password, invoke = (
        postgres_provisioning
    )

    original_create = account_service.create_user

    def simulate_failure(db, **kwargs):
        user = original_create(db, **kwargs)

        assert user.id is not None

        # Simulate a failure after INSERT and flush,
        # but before the transaction commits.
        raise ValueError("Simulated provisioning failure")

    monkeypatch.setattr(
        account_service,
        "create_user",
        simulate_failure,
    )

    result = invoke("admin")

    assert result == 1

    output = capsys.readouterr().out

    assert "Account created successfully" not in output
    assert password not in output

    with TestSession() as db:
        user = db.scalar(
            select(User).where(
                User.username == username
            )
        )

        assert user is None


def test_postgres_provisioning_rejects_schema_mismatch(
    postgres_provisioning, monkeypatch
):
    import account_service
    import provision_user

    TestSession, username, _, invoke = (
        postgres_provisioning
    )

    # Simulate an unexpected schema revision without
    # modifying the actual database or migration history.
    monkeypatch.setattr(
        provision_user,
        "EXPECTED_REVISION",
        "unexpected_revision",
    )

    def forbidden_creation(*args, **kwargs):
        raise AssertionError(
            "Unsafe account creation attempted"
        )

    monkeypatch.setattr(
        account_service,
        "create_user",
        forbidden_creation,
    )

    assert invoke("admin") == 1

    with TestSession() as db:
        user = db.scalar(
            select(User).where(
                User.username == username
            )
        )

        assert user is None


def read_pending_queue(client):
    """Read all queue pages without assuming an empty database."""

    records = []
    offset = 0

    for _ in range(100):
        response = client.get(
            "/allocations/pending",
            params={
                "limit": 100,
                "offset": offset,
            },
        )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"

        data = response.json()

        assert data["count"] == len(data["allocations"])

        records.extend(data["allocations"])

        if not data["has_more"]:
            return records

        offset += data["count"]

    raise AssertionError("Unexpected queue pagination")


@pytest.mark.parametrize(
    "role, expected",
    [
        (None, 401),
        ("operator", 403),
        ("admin", 200),
    ],
)
def test_postgres_pending_queue_access(
    postgres_protected_routes, role, expected
):
    from models import Inventory, Allocation

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    if role is not None:
        with TestSession.begin() as db:
            db.get(User, user_id).role = role

    with TestClient(app) as client:
        if role is not None:
            with TestClient(auth_app) as auth_client:
                authenticated = send_login(
                    auth_client,
                    username,
                    TEST_PASSWORD,
                )

                assert authenticated.status_code == 200

                token = authenticated.cookies.get(
                    "resqnet_session"
                )

                assert token

            client.cookies.set("resqnet_session", token)

        response = client.get("/allocations/pending")

        assert response.status_code == expected

        if expected == 200:
            records = read_pending_queue(client)

            matching = [
                record for record in records
                if record["allocation_id"] == allocation_id
            ]

            assert len(matching) == 1

            record = matching[0]

            assert record["status"] == "PENDING"
            assert record["incident_id"] == incident_id
            assert record["warehouse_id"] == warehouse_id

            assert record["proposed_allocation"] == {
                "food": 40,
                "water": 60,
                "medicine": 10,
            }

        else:
            assert "allocations" not in response.json()

    # Reading or attempting to access the queue
    # must never deduct inventory.
    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)

        allocation = db.get(Allocation, allocation_id)

        assert allocation.status == "PENDING"


def test_postgres_pending_queue_excludes_approved(
    postgres_protected_routes,
):
    from models import Allocation, Inventory

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestSession.begin() as db:
        db.get(User, user_id).role = "admin"

    with TestClient(auth_app) as auth_client:
        authenticated = send_login(
            auth_client,
            username,
            TEST_PASSWORD,
        )

        assert authenticated.status_code == 200

        token = authenticated.cookies.get("resqnet_session")

        assert token

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", token)

        before = read_pending_queue(client)

        assert any(
            row["allocation_id"] == allocation_id
            for row in before
        )

        # Modify only the disposable test record.
        # This isolates the queue's status filtering.
        with TestSession.begin() as db:
            db.get(
                Allocation, allocation_id
            ).status = "APPROVED"

        after = read_pending_queue(client)

        assert not any(
            row["allocation_id"] == allocation_id
            for row in after
        )

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)


@pytest.mark.parametrize(
    "role, csrf_mode, expected",
    [
        (None, "missing", 401),
        ("operator", "valid", 403),
        ("admin", "missing", 403),
        ("admin", "invalid", 403),
        ("admin", "valid", 200),
    ],
)
def test_postgres_rejection_permissions(
    postgres_protected_routes,
    role,
    csrf_mode,
    expected,
):
    from models import Allocation, Inventory

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestSession() as db:
        original = db.get(
            Allocation, allocation_id
        ).requirements

    headers = {"Origin": TEST_ORIGIN}

    with TestClient(app) as client:
        if role is not None:
            with TestSession.begin() as db:
                db.get(User, user_id).role = role

            with TestClient(auth_app) as auth_client:
                login = send_login(
                    auth_client, username, TEST_PASSWORD
                )

                assert login.status_code == 200

                token = login.cookies.get("resqnet_session")
                assert token

                client.cookies.set(
                    "resqnet_session", token
                )

                if csrf_mode == "valid":
                    headers["X-CSRF-Token"] = (
                        login.json()["csrf_token"]
                    )
                elif csrf_mode == "invalid":
                    headers["X-CSRF-Token"] = "0" * 64

        response = client.post(
            f"/allocation/{allocation_id}/reject", json={"reason": "  Duplicate test allocation request  "},
            headers=headers,
        )

        assert response.status_code == expected

        if expected == 200:
            assert response.json()["status"] == "REJECTED"

            repeated = client.post(
                f"/allocation/{allocation_id}/reject", json={"reason": "  Duplicate test allocation request  "},
                headers=headers,
            )

            assert repeated.status_code == 409

            approval = client.post(
                f"/allocation/{allocation_id}/approve",
                headers=headers,
            )

            assert approval.status_code == 409

            pending = read_pending_queue(client)

            assert not any(
                row["allocation_id"] == allocation_id
                for row in pending
            )

    with TestSession() as db:
        record = db.get(Allocation, allocation_id)

        assert record.requirements == original
        assert record.status == (
            "REJECTED" if expected == 200 else "PENDING"
        )

        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)


@pytest.mark.parametrize(
    "actions",
    [
        ("approve", "reject"),
        ("reject", "reject"),
    ],
)
def test_postgres_rejection_concurrency(
    postgres_protected_routes, actions
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from models import Allocation, Inventory

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestSession.begin() as db:
        db.get(User, user_id).role = "admin"

    credentials = []

    # Create two independent authenticated sessions.
    with TestClient(auth_app) as auth_client:
        for _ in range(2):
            login = send_login(
                auth_client, username, TEST_PASSWORD
            )

            assert login.status_code == 200

            token = login.cookies.get("resqnet_session")
            assert token

            credentials.append((
                token,
                login.json()["csrf_token"],
            ))

    assert credentials[0][0] != credentials[1][0]

    barrier = Barrier(2)

    def perform_action(action, credentials):
        token, csrf_token = credentials

        with TestClient(app) as client:
            client.cookies.set("resqnet_session", token)

            barrier.wait(timeout=15)

            response = client.post(
                f"/allocation/{allocation_id}/{action}", **({"json": {"reason": "  Duplicate test allocation request  "}} if action == "reject" else {}),
                headers={
                    "Origin": TEST_ORIGIN,
                    "X-CSRF-Token": csrf_token,
                },
            )

            return action, response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                perform_action,
                action,
                credentials[index],
            )
            for index, action in enumerate(actions)
        ]

        results = [
            future.result(timeout=30)
            for future in futures
        ]

    assert sorted(
        status for _, status in results
    ) == [200, 409]

    winner = next(
        action for action, status in results
        if status == 200
    )

    with TestSession() as db:
        record = db.get(Allocation, allocation_id)
        inventory = db.get(Inventory, warehouse_id)

        actual_stock = (
            inventory.food,
            inventory.water,
            inventory.medicine,
        )

        if winner == "approve":
            assert record.status == "APPROVED"
            assert actual_stock == (60, 140, 40)
        else:
            assert record.status == "REJECTED"
            assert actual_stock == (100, 200, 50)


@pytest.mark.parametrize(
    "role, expected",
    [
        (None, 401),
        ("operator", 403),
        ("admin", 200),
    ],
)
def test_postgres_history_permissions(
    postgres_protected_routes, role, expected
):
    from models import Allocation, Inventory

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestClient(app) as client:
        if role is not None:
            with TestSession.begin() as db:
                db.get(User, user_id).role = role

            with TestClient(auth_app) as auth_client:
                login = send_login(
                    auth_client, username, TEST_PASSWORD
                )

                assert login.status_code == 200

                token = login.cookies.get("resqnet_session")
                assert token

                client.cookies.set(
                    "resqnet_session", token
                )

        response = client.get(
            "/allocations/history",
            params={"q": allocation_id},
        )

        assert response.status_code == expected

        if expected == 200:
            data = response.json()

            assert data["count"] == 1
            assert data["has_more"] is False
            assert response.headers["Cache-Control"] == "no-store"

            record = data["allocations"][0]

            assert record["allocation_id"] == allocation_id
            assert record["warehouse_id"] == warehouse_id
            assert record["status"] == "PENDING"

        else:
            assert "allocations" not in response.json()

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)

        assert db.get(
            Allocation, allocation_id
        ).status == "PENDING"


@pytest.mark.parametrize(
    "status",
    ["PENDING", "APPROVED", "REJECTED"],
)
def test_postgres_history_status_filters(
    postgres_protected_routes, status
):
    from models import Allocation, Inventory

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestSession.begin() as db:
        db.get(User, user_id).role = "admin"

        # Change only this disposable fixture record.
        db.get(Allocation, allocation_id).status = status

    with TestClient(auth_app) as auth_client:
        login = send_login(
            auth_client, username, TEST_PASSWORD
        )

        assert login.status_code == 200

        token = login.cookies.get("resqnet_session")
        assert token

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", token)

        for requested_status in (
            "ALL", "PENDING", "APPROVED", "REJECTED"
        ):
            response = client.get(
                "/allocations/history",
                params={
                    "status": requested_status,
                    "q": allocation_id,
                },
            )

            assert response.status_code == 200

            data = response.json()

            if requested_status in ("ALL", status):
                assert data["count"] == 1
                assert data["allocations"][0]["status"] == status
            else:
                assert data["count"] == 0

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)

        assert db.get(
            Allocation, allocation_id
        ).status == status


def test_postgres_history_search_and_pagination(
    postgres_protected_routes,
):
    from models import Warehouse

    (
        auth_app, app, TestSession,
        username, user_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    with TestSession.begin() as db:
        db.get(User, user_id).role = "admin"

        warehouse_name = db.get(
            Warehouse, warehouse_id
        ).name

    with TestClient(auth_app) as auth_client:
        login = send_login(
            auth_client, username, TEST_PASSWORD
        )

        assert login.status_code == 200

        token = login.cookies.get("resqnet_session")
        assert token

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", token)

        for search in (
            allocation_id.upper(),
            incident_id.upper(),
            warehouse_name.swapcase(),
        ):
            offset = 0
            found = False

            for _ in range(100):
                response = client.get(
                    "/allocations/history",
                    params={
                        "q": search,
                        "limit": 100,
                        "offset": offset,
                    },
                )

                assert response.status_code == 200

                data = response.json()

                if any(
                    row["allocation_id"] == allocation_id
                    for row in data["allocations"]
                ):
                    found = True
                    break

                if not data["has_more"]:
                    break

                offset += data["count"]

            assert found

        response = client.get(
            "/allocations/history",
            params={
                "q": allocation_id,
                "limit": 1,
                "offset": 1,
            },
        )

        assert response.status_code == 200
        assert response.json()["count"] == 0
        assert response.json()["has_more"] is False

        # Percent signs must not behave as SQL wildcards.
        response = client.get(
            "/allocations/history",
            params={"q": allocation_id + "%"},
        )

        assert response.status_code == 200
        assert response.json()["count"] == 0


@pytest.mark.parametrize(
    "action, simulate_rollback",
    [
        ("approve", False),
        ("reject", False),
        ("approve", True),
        ("reject", True),
    ],
)
def test_postgres_allocation_audit_integrity(
    postgres_protected_routes,
    action,
    simulate_rollback,
):
    from datetime import datetime, timezone
    from sqlalchemy import event
    from models import Allocation, Inventory
    from session_service import create_session
    from csrf_protection import generate_csrf_token

    (
        auth_app, app, TestSession,
        username, operator_id, warehouse_id,
        allocation_id, incident_id, new_name,
    ) = postgres_protected_routes

    admin_id = None

    try:
        # Create genuinely separate operator and administrator
        # accounts with independent authenticated sessions.
        with TestSession.begin() as db:
            operator = db.get(User, operator_id)
            operator.role = "operator"

            admin = create_user(
                db,
                username="auditpg_" + uuid.uuid4().hex[:20],
                password=TEST_PASSWORD,
                role="admin",
            )

            admin_id = admin.id

            assert admin_id != operator_id

            operator_token = create_session(db, operator_id)
            admin_token = create_session(db, admin_id)

        with TestClient(app) as operator_client:
            operator_client.cookies.set(
                "resqnet_session", operator_token
            )

            preview = operator_client.post(
                "/allocation/preview",
                headers={
                    "Origin": TEST_ORIGIN,
                    "X-CSRF-Token":
                        generate_csrf_token(operator_token),
                },
                json={
                    "incident_id": incident_id,
                    "warehouse_id": warehouse_id,
                    "food": 40,
                    "water": 60,
                    "medicine": 10,
                },
            )

        assert preview.status_code == 200, preview.text

        request_id = preview.json()["allocation_id"]

        def read_state():
            with TestSession() as db:
                record = db.get(Allocation, request_id)
                inventory = db.get(Inventory, warehouse_id)

                return {
                    "status": record.status,
                    "submitted_by": record.submitted_by,
                    "decided_by": record.decided_by,
                    "decided_at": record.decided_at,
                    "rejection_reason": record.rejection_reason,
                    "requirements": record.requirements,
                    "stock": (
                        inventory.food,
                        inventory.water,
                        inventory.medicine,
                    ),
                }

        before = read_state()

        assert before["status"] == "PENDING"
        assert before["submitted_by"] == operator_id
        assert before["decided_by"] is None
        assert before["decided_at"] is None
        assert before["stock"] == (100, 200, 50)

        final_status = (
            "APPROVED" if action == "approve"
            else "REJECTED"
        )

        def fail_after_flush(session, flush_context):
            for record in session.dirty:
                if (
                    isinstance(record, Allocation)
                    and record.id == request_id
                    and record.status == final_status
                ):
                    raise RuntimeError(
                        "Simulated audit transaction failure"
                    )

        if simulate_rollback:
            event.listen(
                TestSession.class_,
                "after_flush",
                fail_after_flush,
            )

        started_at = datetime.now(timezone.utc)

        try:
            with TestClient(app) as admin_client:
                admin_client.cookies.set(
                    "resqnet_session", admin_token
                )

                def decide():
                    return admin_client.post(
                        f"/allocation/{request_id}/{action}", **({"json": {"reason": "  Duplicate test allocation request  "}} if action == "reject" else {}),
                        headers={
                            "Origin": TEST_ORIGIN,
                            "X-CSRF-Token":
                                generate_csrf_token(admin_token),
                        },
                    )

                if simulate_rollback:
                    with pytest.raises(
                        RuntimeError,
                        match="Simulated audit transaction failure",
                    ):
                        decide()

                else:
                    response = decide()

                    assert response.status_code == 200
                    assert response.json()["status"] == final_status

        finally:
            if simulate_rollback:
                event.remove(
                    TestSession.class_,
                    "after_flush",
                    fail_after_flush,
                )

        finished_at = datetime.now(timezone.utc)
        after = read_state()

        if simulate_rollback:
            # Every change must roll back together.
            assert after == before

        else:
            assert after["status"] == final_status
            assert after["submitted_by"] == operator_id
            assert after["decided_by"] == admin_id

            assert after["rejection_reason"] == (
                "Duplicate test allocation request"
                if action == "reject"
                else None
            )

            assert after["decided_at"] is not None
            assert after["decided_at"].utcoffset() is not None

            assert (
                started_at
                <= after["decided_at"]
                <= finished_at
            )

            assert (
                after["requirements"]
                == before["requirements"]
            )

            expected_stock = (
                (60, 140, 40)
                if action == "approve"
                else (100, 200, 50)
            )

            assert after["stock"] == expected_stock

        with TestClient(app) as admin_client:
            admin_client.cookies.set(
                "resqnet_session", admin_token
            )

            history = admin_client.get(
                "/allocations/history",
                params={"q": request_id},
            )

        assert history.status_code == 200

        history_data = history.json()

        assert history_data["count"] == 1

        result = history_data["allocations"][0]

        assert result["allocation_id"] == request_id
        assert result["status"] == after["status"]
        assert result["submitted_by"] == operator_id
        assert result["submitted_by_username"] == username
        assert result["decided_by"] == after["decided_by"]

        assert (
            result["rejection_reason"]
            == after["rejection_reason"]
        )

        if simulate_rollback:
            assert result["decided_by_username"] is None
            assert result["decided_at"] is None

        else:
            with TestSession() as db:
                administrator = db.get(User, admin_id)

                assert (
                    result["decided_by_username"]
                    == administrator.username
                )

            assert (
                datetime.fromisoformat(result["decided_at"])
                == after["decided_at"]
            )


    finally:
        # Remove only disposable records associated with
        # the independently created test administrator.
        if admin_id is not None:
            with TestSession.begin() as db:
                db.execute(
                    delete(Allocation).where(
                        Allocation.warehouse_id == warehouse_id,
                        Allocation.decided_by == admin_id,
                    )
                )

                db.execute(
                    delete(UserSession).where(
                        UserSession.user_id == admin_id
                    )
                )

                db.execute(
                    delete(User).where(
                        User.id == admin_id
                    )
                )
