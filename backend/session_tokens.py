
"""Secure session token utilities for RESQNET."""

import hashlib
import secrets
from datetime import timedelta


SESSION_LIFETIME = timedelta(hours=12)


def generate_session_token() -> str:
    """Create an unpredictable 256-bit session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token before storing it in the database."""
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()
