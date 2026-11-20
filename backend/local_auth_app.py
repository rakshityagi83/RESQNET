"""Guarded local RESQNET application with authentication enabled."""

import os
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url


def create_app():
    """Activate authentication exclusively in a fresh local process."""

    if "database" in sys.modules or "main" in sys.modules:
        raise RuntimeError(
            "Local authentication requires a fresh Python process"
        )

    raw_url = os.getenv("RESQNET_PG_TEST_URL")

    if not raw_url:
        raise RuntimeError("Local PostgreSQL URL is missing")

    try:
        url = make_url(raw_url)
    except Exception:
        raise RuntimeError(
            "Invalid local PostgreSQL configuration"
        ) from None

    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 5432
        and url.database == "resqnet_test_concurrency"
        and not url.query
    ):
        raise RuntimeError("Unsafe authentication database")

    # Configure only this local Python process.
    os.environ["DATABASE_URL"] = raw_url
    os.environ["RESQNET_ENV"] = "development"
    os.environ["FRONTEND_URL"] = "http://localhost:5173"

    os.environ["RESQNET_CSRF_HMAC_KEY"] = os.getenv(
        "RESQNET_LOCAL_CSRF_KEY", ""
    )

    os.environ["RESQNET_RATE_LIMIT_HMAC_KEY"] = os.getenv(
        "RESQNET_LOCAL_RATE_LIMIT_KEY", ""
    )

    os.environ["PGHOSTADDR"] = "127.0.0.1"
    os.environ["PGCONNECT_TIMEOUT"] = "5"
    os.environ["PGOPTIONS"] = "-c search_path=public"

    from auth_config import validate_local_auth_configuration
    from database import engine
    from provision_user import verify_database

    validate_local_auth_configuration(raw_url)

    if engine.url != url:
        raise RuntimeError("Database configuration mismatch")

    # Verify the actual engine that RESQNET will use.
    with engine.connect() as db:
        verify_database(db)

        server_address = db.execute(
            text("SELECT host(inet_server_addr())")
        ).scalar_one()

        if server_address != "127.0.0.1":
            raise RuntimeError("Unexpected PostgreSQL server")

        rate_limits_exist = db.execute(
            text(
                "SELECT to_regclass('public.login_rate_limits')"
            )
        ).scalar_one()

        if rate_limits_exist is None:
            raise RuntimeError("Login rate-limit table missing")

        isolation = db.execute(
            text("SHOW transaction_isolation")
        ).scalar_one()

        if isolation.lower() != "read committed":
            raise RuntimeError("Unexpected transaction isolation")

    from main import app
    from auth_api import router

    app.include_router(router)

    return app
