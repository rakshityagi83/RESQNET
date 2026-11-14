
"""Secure login session management for RESQNET."""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User, UserSession
from session_tokens import (
    SESSION_LIFETIME,
    generate_session_token,
    hash_session_token,
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize timestamps, including SQLite's naive timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def valid_token_format(token: str) -> bool:
    """Accept only the format produced by token_urlsafe(32)."""
    return (
        isinstance(token, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None
    )


def create_session(session: Session, user_id: int) -> str:
    """Create a session for an active user.

    Returns the raw token once. The database stores only its hash.
    The caller must commit the transaction before issuing the token.
    """
    user = session.get(User, user_id)

    if user is None or not user.is_active:
        raise ValueError("Cannot create session for inactive user")

    token = generate_session_token()
    now = utc_now()

    record = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=now + SESSION_LIFETIME,
    )

    session.add(record)
    session.flush()

    return token


def get_authenticated_user(
    session: Session,
    token: str,
) -> User | None:
    """Return the active user only for a valid session."""
    if not valid_token_format(token):
        return None

    record = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token)
        )
    )

    if record is None:
        return None

    if record.revoked_at is not None:
        return None

    if as_utc(record.expires_at) <= utc_now():
        return None

    user = session.get(User, record.user_id)

    if user is None or not user.is_active:
        return None

    return user


def revoke_session(session: Session, token: str) -> bool:
    """Revoke a session. Caller manages the database transaction."""
    if not valid_token_format(token):
        return False

    record = session.scalar(
        select(UserSession)
        .where(UserSession.token_hash == hash_session_token(token))
        .with_for_update()
    )

    if record is None or record.revoked_at is not None:
        return False

    record.revoked_at = utc_now()
    session.flush()

    return True
