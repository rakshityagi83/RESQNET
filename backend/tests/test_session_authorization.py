"""Tests for individual session-based authorization."""

from datetime import datetime, timedelta, timezone

import pytest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import session_authorization

from database import Base
from models import User, UserSession
from session_service import create_session
from session_tokens import (
    generate_session_token,
    hash_session_token,
)

from session_authorization import (
    SessionPrincipal,
    get_current_principal,
    require_session_admin,
    require_session_operator,
)


@pytest.fixture
def isolated_authorization(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    tokens = {}

    with TestSession.begin() as db:
        for role in ["admin", "operator"]:
            user = User(
                username="test_" + role,
                password_hash="unused-test-hash",
                role=role,
                is_active=True,
            )

            db.add(user)
            db.flush()

            tokens[role] = create_session(db, user.id)

    monkeypatch.setattr(
        session_authorization,
        "SessionLocal",
        TestSession,
    )

    app = FastAPI()

    @app.get("/identity")
    def identity(
        principal: SessionPrincipal = Depends(
            get_current_principal
        ),
    ):
        return {
            "user_id": principal.user_id,
            "username": principal.username,
            "role": principal.role,
        }

    @app.get("/admin")
    def admin_endpoint(
        principal: SessionPrincipal = Depends(
            require_session_admin
        ),
    ):
        return {"role": principal.role}

    @app.get("/operator")
    def operator_endpoint(
        principal: SessionPrincipal = Depends(
            require_session_operator
        ),
    ):
        return {"role": principal.role}

    try:
        yield app, TestSession, tokens
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "token",
    [None, "invalid-token", generate_session_token()],
)
def test_invalid_session_rejected(
    isolated_authorization, token
):
    app, _, _ = isolated_authorization

    with TestClient(app) as client:
        if token is not None:
            client.cookies.set("resqnet_session", token)

        response = client.get("/identity")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "role",
    ["admin", "operator"],
)
def test_session_resolves_individual_identity(
    isolated_authorization, role
):
    app, _, tokens = isolated_authorization

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", tokens[role])
        response = client.get("/identity")

    assert response.status_code == 200
    assert response.json()["username"] == "test_" + role
    assert response.json()["role"] == role
    assert response.json()["user_id"] > 0


@pytest.mark.parametrize(
    "role, endpoint, expected_status",
    [
        ("admin", "/admin", 200),
        ("admin", "/operator", 200),
        ("operator", "/operator", 200),
        ("operator", "/admin", 403),
    ],
)
def test_role_permission_matrix(
    isolated_authorization, role, endpoint, expected_status
):
    app, _, tokens = isolated_authorization

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", tokens[role])
        response = client.get(endpoint)

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "condition",
    ["expired", "revoked", "disabled", "invalid_role"],
)
def test_unusable_accounts_and_sessions_rejected(
    isolated_authorization, condition
):
    app, TestSession, tokens = isolated_authorization
    token = tokens["operator"]

    with TestSession.begin() as db:
        record = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )

        user = db.get(User, record.user_id)

        if condition == "expired":
            record.expires_at = (
                datetime.now(timezone.utc)
                - timedelta(seconds=1)
            )

        elif condition == "revoked":
            record.revoked_at = datetime.now(timezone.utc)

        elif condition == "disabled":
            user.is_active = False

        elif condition == "invalid_role":
            user.role = "unknown"

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", token)
        response = client.get("/operator")

    expected = 403 if condition == "invalid_role" else 401

    assert response.status_code == expected


def test_bearer_token_cannot_replace_session(
    isolated_authorization,
):
    app, _, tokens = isolated_authorization

    with TestClient(app) as client:
        response = client.get(
            "/admin",
            headers={
                "Authorization": "Bearer " + tokens["admin"],
            },
        )

    assert response.status_code == 401


@pytest.fixture
def protected_write_app(isolated_authorization, monkeypatch):
    from csrf_protection import generate_csrf_token

    app, TestSession, tokens = isolated_authorization

    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "test-only-" + "x" * 48,
    )

    csrf_tokens = {
        role: generate_csrf_token(token)
        for role, token in tokens.items()
    }

    executed = []

    @app.post("/admin-write")
    def admin_write(
        principal: SessionPrincipal = Depends(
            session_authorization.require_admin_write
        ),
    ):
        executed.append("admin-write")
        return {"role": principal.role}

    @app.post("/operator-write")
    def operator_write(
        principal: SessionPrincipal = Depends(
            session_authorization.require_operator_write
        ),
    ):
        executed.append("operator-write")
        return {"role": principal.role}

    return app, tokens, csrf_tokens, executed


@pytest.mark.parametrize(
    "role, endpoint, expected_status",
    [
        ("admin", "/admin-write", 200),
        ("admin", "/operator-write", 200),
        ("operator", "/operator-write", 200),
        ("operator", "/admin-write", 403),
    ],
)
def test_protected_write_permission_matrix(
    protected_write_app, role, endpoint, expected_status
):
    app, tokens, csrf_tokens, executed = protected_write_app

    with TestClient(app) as client:
        client.cookies.set("resqnet_session", tokens[role])

        response = client.post(
            endpoint,
            headers={
                "Origin": "http://localhost:5173",
                "X-CSRF-Token": csrf_tokens[role],
            },
        )

    assert response.status_code == expected_status

    if expected_status == 200:
        assert executed == [endpoint.lstrip("/")]
    else:
        assert executed == []


@pytest.mark.parametrize(
    "origin, csrf_kind",
    [
        (None, "valid"),
        ("https://untrusted.example", "valid"),
        ("http://localhost:5173", "missing"),
        ("http://localhost:5173", "invalid"),
        ("http://localhost:5173", "other_session"),
    ],
)
def test_unsafe_write_requests_rejected(
    protected_write_app, origin, csrf_kind
):
    app, tokens, csrf_tokens, executed = protected_write_app

    headers = {}

    if origin is not None:
        headers["Origin"] = origin

    if csrf_kind == "valid":
        headers["X-CSRF-Token"] = csrf_tokens["admin"]

    elif csrf_kind == "invalid":
        headers["X-CSRF-Token"] = "0" * 64

    elif csrf_kind == "other_session":
        headers["X-CSRF-Token"] = csrf_tokens["operator"]

    with TestClient(app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.post(
            "/admin-write",
            headers=headers,
        )

    assert response.status_code == 403

    # The protected endpoint must never execute.
    assert executed == []


def test_csrf_token_alone_cannot_authorize_write(
    protected_write_app,
):
    app, _, csrf_tokens, executed = protected_write_app

    with TestClient(app) as client:
        response = client.post(
            "/admin-write",
            headers={
                "Origin": "http://localhost:5173",
                "X-CSRF-Token": csrf_tokens["admin"],
            },
        )

    assert response.status_code == 401
    assert executed == []
