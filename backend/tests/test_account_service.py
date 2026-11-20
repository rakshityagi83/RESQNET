
"""Tests for RESQNET individual user account operations."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from account_service import create_user, authenticate_user
from database import Base
from models import User


@pytest.fixture
def db_session():
    """Create an isolated in-memory database for each test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()


def test_admin_created_with_hashed_password(db_session):
    user = create_user(
        db_session,
        username="TestAdmin",
        password="secure-test-password-123",
        role="admin",
    )

    assert user.id is not None
    assert user.username == "testadmin"
    assert user.role == "admin"
    assert user.is_active is True
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != "secure-test-password-123"


def test_operator_is_default_role(db_session):
    user = create_user(
        db_session,
        username="operator1",
        password="secure-test-password-123",
    )

    assert user.role == "operator"


def test_correct_credentials_accepted(db_session):
    create_user(
        db_session,
        username="operator1",
        password="correct-test-password-123",
    )

    user = authenticate_user(
        db_session,
        "operator1",
        "correct-test-password-123",
    )

    assert user is not None
    assert user.username == "operator1"


def test_incorrect_password_rejected(db_session):
    create_user(
        db_session,
        username="operator1",
        password="correct-test-password-123",
    )

    user = authenticate_user(
        db_session,
        "operator1",
        "incorrect-password",
    )

    assert user is None


def test_unknown_user_rejected(db_session):
    user = authenticate_user(
        db_session,
        "unknownuser",
        "example-password",
    )

    assert user is None


def test_disabled_user_cannot_authenticate(db_session):
    user = create_user(
        db_session,
        username="operator1",
        password="correct-test-password-123",
    )

    user.is_active = False
    db_session.flush()

    result = authenticate_user(
        db_session,
        "operator1",
        "correct-test-password-123",
    )

    assert result is None


def test_username_is_case_insensitive(db_session):
    create_user(
        db_session,
        username="  TestOperator  ",
        password="correct-test-password-123",
    )

    user = authenticate_user(
        db_session,
        "TESTOPERATOR",
        "correct-test-password-123",
    )

    assert user is not None
    assert user.username == "testoperator"


def test_duplicate_username_rejected(db_session):
    create_user(
        db_session,
        username="operator1",
        password="first-test-password-123",
    )

    with pytest.raises(ValueError, match="already exists"):
        create_user(
            db_session,
            username="OPERATOR1",
            password="second-test-password-123",
        )

    users = db_session.scalars(select(User)).all()
    assert len(users) == 1


def test_invalid_role_rejected(db_session):
    with pytest.raises(ValueError, match="Invalid account role"):
        create_user(
            db_session,
            username="operator1",
            password="secure-test-password-123",
            role="superadmin",
        )


def test_invalid_username_rejected(db_session):
    with pytest.raises(ValueError, match="Username"):
        create_user(
            db_session,
            username="bad username!",
            password="secure-test-password-123",
        )


def test_short_password_rejected(db_session):
    with pytest.raises(ValueError, match="Password length"):
        create_user(
            db_session,
            username="operator1",
            password="short",
        )


def test_account_creation_can_be_rolled_back(db_session):
    create_user(
        db_session,
        username="operator1",
        password="secure-test-password-123",
    )

    db_session.rollback()

    user = db_session.scalar(
        select(User).where(User.username == "operator1")
    )

    assert user is None


@pytest.mark.parametrize(
    "condition",
    [
        "unknown",
        "wrong_password",
        "disabled",
        "invalid_role",
        "valid",
    ],
)
def test_password_verification_on_authentication_paths(
    db_session, monkeypatch, condition
):
    import account_service

    password = "correct-test-password-123"

    user = create_user(
        db_session,
        username="operator1",
        password=password,
    )

    username = user.username

    if condition == "unknown":
        username = "unknownoperator"

    elif condition == "wrong_password":
        password = "incorrect-password"

    elif condition == "disabled":
        user.is_active = False

    elif condition == "invalid_role":
        user.role = "unknown"

    db_session.flush()

    observed = []

    original_verify = account_service.verify_password

    def track_verification(candidate, stored_hash):
        observed.append(stored_hash)

        return original_verify(
            candidate,
            stored_hash,
        )

    monkeypatch.setattr(
        account_service,
        "verify_password",
        track_verification,
    )

    result = authenticate_user(
        db_session,
        username,
        password,
    )

    # Every well-formed authentication path must perform
    # one password verification.
    assert len(observed) == 1

    if condition == "unknown":
        assert observed[0] == (
            account_service._DUMMY_PASSWORD_HASH
        )

        assert observed[0].startswith("$argon2id$")

    else:
        assert observed[0] == user.password_hash

    if condition == "valid":
        assert result is not None
        assert result.id == user.id
    else:
        assert result is None


def test_dummy_verification_cannot_authenticate_unknown_user(
    db_session, monkeypatch
):
    import account_service

    # Even if dummy password verification returns True,
    # an unknown account must never authenticate.
    monkeypatch.setattr(
        account_service,
        "verify_password",
        lambda password, stored_hash: True,
    )

    result = authenticate_user(
        db_session,
        "unknownoperator",
        "example-password",
    )

    assert result is None
