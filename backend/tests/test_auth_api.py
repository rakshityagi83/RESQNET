
"""Isolated security tests for the RESQNET login API."""

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

    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", VALID_ORIGIN)

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
