"""Shared authentication helpers for isolated test databases."""

import uuid

import pytest

import session_authorization

from models import User
from session_service import create_session
from csrf_protection import generate_csrf_token


@pytest.fixture
def session_test_headers(monkeypatch):
    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv(
        "FRONTEND_URL", "http://localhost:5173"
    )
    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "test-only-" + "x" * 48,
    )

    def issue(TestSession, role):
        monkeypatch.setattr(
            session_authorization,
            "SessionLocal",
            TestSession,
        )

        with TestSession.begin() as db:
            user = User(
                username="test_" + uuid.uuid4().hex[:20],
                password_hash="unused-test-hash",
                role=role,
                is_active=True,
            )

            db.add(user)
            db.flush()

            user_id = user.id
            token = create_session(db, user_id)

        return {
            "Cookie": "resqnet_session=" + token,
            "Origin": "http://localhost:5173",
            "X-CSRF-Token": generate_csrf_token(token),
        }, user_id

    return issue
