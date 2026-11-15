
"""Login rate-limiting utilities for RESQNET."""

import hashlib
import hmac
import ipaddress
import os

from datetime import timedelta


USERNAME_MAX_FAILURES = 5
IP_MAX_FAILURES = 20

RATE_LIMIT_WINDOW = timedelta(minutes=15)
BLOCK_DURATION = timedelta(minutes=15)


def get_rate_limit_key() -> bytes:
    """Load the secret used to protect identity fingerprints."""
    secret = os.getenv("RESQNET_RATE_LIMIT_HMAC_KEY", "")

    key = secret.encode("utf-8")

    if len(key) < 32:
        raise RuntimeError(
            "RESQNET rate-limit HMAC key is not configured"
        )

    return key


def fingerprint_identity(
    identity_type: str,
    identity_value: str,
) -> str:
    """Create a keyed SHA-256 fingerprint of an identity."""

    if identity_type not in {"username", "ip"}:
        raise ValueError("Invalid identity type")

    if not isinstance(identity_value, str):
        raise ValueError("Invalid identity value")

    if identity_type == "username":
        normalized = identity_value.strip().lower()

        if not normalized or len(normalized) > 80:
            raise ValueError("Invalid username")

    else:
        # Canonicalize IPv4 and IPv6 addresses.
        normalized = str(
            ipaddress.ip_address(identity_value)
        )

    message = (
        f"{identity_type}:{normalized}"
    ).encode("utf-8")

    return hmac.new(
        get_rate_limit_key(),
        message,
        hashlib.sha256,
    ).hexdigest()


def fingerprint_username(username: str) -> str:
    """Fingerprint a username without storing it in plaintext."""
    return fingerprint_identity("username", username)


def fingerprint_ip(ip_address: str) -> str:
    """Fingerprint a client IP without storing it in plaintext."""
    return fingerprint_identity("ip", ip_address)
