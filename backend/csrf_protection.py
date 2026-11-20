
"""Session-bound CSRF protection utilities for RESQNET."""

import hashlib
import hmac
import os
import re

from browser_security import check_trusted_origin

from session_service import valid_token_format


CSRF_CONTEXT = b"resqnet:csrf:v1:"


def get_csrf_secret() -> bytes:
    """Load the dedicated CSRF HMAC secret."""
    secret = os.getenv("RESQNET_CSRF_HMAC_KEY", "")
    key = secret.encode("utf-8")

    if len(key) < 32:
        raise RuntimeError(
            "RESQNET CSRF HMAC key is not configured"
        )

    return key


def generate_csrf_token(session_token: str) -> str:
    """Generate a CSRF token bound to one valid session token."""

    if not valid_token_format(session_token):
        raise ValueError("Invalid session token")

    message = CSRF_CONTEXT + session_token.encode("ascii")

    return hmac.new(
        get_csrf_secret(),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(
    session_token: str,
    submitted_token: str | None,
) -> bool:
    """Check a submitted CSRF token using constant-time comparison.

    The caller must also verify that the session is authenticated.
    """

    if not valid_token_format(session_token):
        return False

    if not isinstance(submitted_token, str):
        return False

    if re.fullmatch(r"[0-9a-f]{64}", submitted_token) is None:
        return False

    expected_token = generate_csrf_token(session_token)

    return hmac.compare_digest(
        expected_token,
        submitted_token,
    )
