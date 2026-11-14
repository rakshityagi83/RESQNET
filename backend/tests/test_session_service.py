
"""Tests for RESQNET session creation, validation and revocation."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import Base
from models import User, UserSession
from session_tokens import (
    SESSION_LIFETIME,
    generate_session_token,
    hash_session_token,
)
from session_service import (
    as_utc,
    create_session,
    get_authenticated_user,
    revoke_session,
)


@pytest.fixture
def account_db():
    """Create an isolated database with one active test user."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    try:
        with Session(engine, expire_on_commit=False) as db:
            user = User(
                username="sessiontester",
                password_hash="unused-test-hash",
                role="operator",
                is_active=True,
            )

            db.add(user)
            db.commit()

            yield db, user
    finally:
        engine.dispose()


def find_session(db, token):
    return db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
    )


def test_session_stores_only_token_hash(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    db.commit()

    record = find_session(db, token)

    assert record is not None
    assert record.user_id == user.id
    assert record.token_hash == hash_session_token(token)
    assert record.token_hash != token
    assert len(record.token_hash) == 64
    assert record.revoked_at is None


def test_valid_session_authenticates_user(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    db.commit()

    authenticated = get_authenticated_user(db, token)

    assert authenticated is not None
    assert authenticated.id == user.id


def test_session_expires_after_twelve_hours(account_db):
    db, user = account_db

    before = datetime.now(timezone.utc)

    token = create_session(db, user.id)
    db.commit()

    after = datetime.now(timezone.utc)
    record = find_session(db, token)

    expires = as_utc(record.expires_at)

    assert before + SESSION_LIFETIME <= expires
    assert expires <= after + SESSION_LIFETIME


def test_unknown_session_token_rejected(account_db):
    db, user = account_db

    create_session(db, user.id)
    db.commit()

    unknown_token = generate_session_token()

    assert get_authenticated_user(db, unknown_token) is None


@pytest.mark.parametrize(
    "invalid_token",
    [
        None,
        "short",
        "A" * 43 + "!",
    ],
)
def test_malformed_token_rejected(account_db, invalid_token):
    db, _ = account_db

    assert get_authenticated_user(db, invalid_token) is None


def test_expired_session_rejected(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    record = find_session(db, token)

    record.expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    db.commit()

    assert get_authenticated_user(db, token) is None


def test_revoked_session_rejected(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    db.commit()

    assert revoke_session(db, token) is True
    db.commit()

    record = find_session(db, token)

    assert record.revoked_at is not None
    assert get_authenticated_user(db, token) is None


def test_repeated_revocation_rejected(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    db.commit()

    assert revoke_session(db, token) is True
    db.commit()

    assert revoke_session(db, token) is False


def test_disabled_user_session_rejected(account_db):
    db, user = account_db

    token = create_session(db, user.id)
    db.commit()

    user.is_active = False
    db.commit()

    assert get_authenticated_user(db, token) is None


def test_cannot_create_session_for_disabled_user(account_db):
    db, user = account_db

    user.is_active = False
    db.commit()

    with pytest.raises(ValueError):
        create_session(db, user.id)


def test_cannot_create_session_for_unknown_user(account_db):
    db, _ = account_db

    with pytest.raises(ValueError):
        create_session(db, 999999)


def test_session_creation_can_be_rolled_back(account_db):
    db, user = account_db

    token = create_session(db, user.id)

    db.rollback()

    assert find_session(db, token) is None
    assert get_authenticated_user(db, token) is None
