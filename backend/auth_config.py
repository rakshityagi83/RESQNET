"""Authentication configuration safeguards for RESQNET."""

import os
import secrets

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from browser_security import configured_frontend_origin
from csrf_protection import get_csrf_secret
from login_rate_limiter import get_rate_limit_key


def validate_local_auth_configuration(database_url):
    """Validate isolated local authentication configuration."""

    if os.getenv("RESQNET_ENV") != "development":
        raise RuntimeError(
            "Local authentication requires development mode"
        )

    frontend = configured_frontend_origin()

    if frontend not in {
        "http://localhost:5173",
        "http://localhost:5174",
    }:
        raise RuntimeError(
            "Invalid local authentication frontend origin"
        )

    try:
        url = make_url(database_url)

    except (ValueError, SQLAlchemyError):
        raise RuntimeError(
            "Invalid authentication database configuration"
        ) from None

    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 5432
        and url.database == "resqnet_test_concurrency"
        and not url.query
    ):
        raise RuntimeError(
            "Unsafe local authentication database"
        )

    try:
        csrf_key = get_csrf_secret()
        rate_limit_key = get_rate_limit_key()

    except (RuntimeError, UnicodeEncodeError):
        raise RuntimeError(
            "Authentication security secrets are missing or invalid"
        ) from None

    if (
        len(csrf_key.strip()) < 32
        or len(rate_limit_key.strip()) < 32
    ):
        raise RuntimeError(
            "Authentication security secrets are invalid"
        )

    if secrets.compare_digest(csrf_key, rate_limit_key):
        raise RuntimeError(
            "Authentication security secrets must be independent"
        )
