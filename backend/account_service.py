
"""Internal user account operations for RESQNET."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from passwords import hash_password, verify_password


USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")
ALLOWED_ROLES = {"admin", "operator"}

# Generate once per process using the same Argon2id parameters
# as real user passwords. This is not an account credential.
_DUMMY_PASSWORD_HASH = hash_password(
    secrets.token_urlsafe(32)
)


def normalize_username(username: str) -> str:
    """Validate and normalize a username."""
    if not isinstance(username, str):
        raise ValueError("Invalid username")

    username = username.strip().lower()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must contain 3-32 valid characters"
        )

    return username


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str = "operator",
) -> User:
    """Create a user within a caller-managed transaction.

    Only trusted administrative code should call this function.
    """
    username = normalize_username(username)

    if role not in ALLOWED_ROLES:
        raise ValueError("Invalid account role")

    if (
        not isinstance(password, str)
        or not 12 <= len(password) <= 128
    ):
        raise ValueError("Password length must be 12-128 characters")

    existing = session.scalar(
        select(User.id).where(User.username == username)
    )

    if existing is not None:
        raise ValueError("Username already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )

    session.add(user)
    session.flush()

    return user


def authenticate_user(
    session: Session,
    username: str,
    password: str,
) -> User | None:
    """Verify credentials for an active account."""
    if not isinstance(password, str):
        return None

    try:
        username = normalize_username(username)
    except ValueError:
        return None

    user = session.scalar(
        select(User).where(User.username == username)
    )

    if user is None:
        # Reduce timing differences between unknown users
        # and accounts with incorrect passwords.
        verify_password(
            password,
            _DUMMY_PASSWORD_HASH,
        )
        return None

    password_valid = verify_password(
        password,
        user.password_hash,
    )

    if (
        not password_valid
        or not user.is_active
        or user.role not in ALLOWED_ROLES
    ):
        return None

    return user
