"""Restricted administrative account provisioning utility."""

import argparse
import os
import warnings

from getpass import getpass, GetPassWarning

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


EXPECTED_DATABASE = "resqnet_test_concurrency"
EXPECTED_REVISION = "8f27c4b19d62"


def validate_database_url(raw_url):
    """Allow only the explicitly configured local test database."""

    if not raw_url:
        raise ValueError("Local database URL is missing")

    url = make_url(raw_url)

    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 5432
        and url.database == EXPECTED_DATABASE
        and not url.query
    ):
        raise ValueError("Unsafe provisioning database")

    return url


def verify_database(db):
    """Verify the connected database before creating accounts."""

    identity = db.execute(
        text("SELECT current_database(), inet_server_port()")
    ).one()

    if tuple(identity) != (EXPECTED_DATABASE, 5432):
        raise ValueError("Database identity mismatch")

    revision = db.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()

    if revision != EXPECTED_REVISION:
        raise ValueError("Unexpected schema revision")

    for table in ("public.users", "public.user_sessions"):
        exists = db.execute(
            text("SELECT to_regclass(:table)"),
            {"table": table},
        ).scalar_one()

        if exists is None:
            raise ValueError("Required authentication table missing")


class SafeArgumentParser(argparse.ArgumentParser):
    """Avoid echoing potentially sensitive rejected arguments."""

    def error(self, message):
        self.print_usage()

        self.exit(
            2,
            "STOP: Invalid command-line arguments. "
            "Use --help for supported options.\n",
        )


def main(argv=None):
    parser = SafeArgumentParser(
        description="Create an individual RESQNET test account",
        allow_abbrev=False,
    )

    parser.add_argument("--username", required=True)

    parser.add_argument(
        "--role",
        required=True,
        choices=["admin", "operator"],
    )

    args = parser.parse_args(argv)

    try:
        url = validate_database_url(
            os.getenv("RESQNET_PG_TEST_URL")
        )

    except (ValueError, SQLAlchemyError):
        print("STOP: Unsafe or missing local database configuration")
        return 1

    from account_service import create_user, normalize_username

    try:
        username = normalize_username(args.username)
    except ValueError:
        print("STOP: Invalid username")
        return 1

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)

            password = getpass("Enter account password: ")
            confirmation = getpass("Confirm account password: ")

    except (GetPassWarning, EOFError, KeyboardInterrupt):
        print("STOP: Secure password entry cancelled")
        return 1

    if password != confirmation:
        print("STOP: Passwords do not match")
        return 1

    if not 12 <= len(password) <= 128:
        print("STOP: Password must contain 12-128 characters")
        return 1

    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        print("STOP: Invalid password encoding")
        return 1

    engine = None

    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "connect_timeout": 5,
                "hostaddr": "127.0.0.1",
                "options": "-c search_path=public",
            },
        )

        with Session(engine) as db:
            with db.begin():
                verify_database(db)

                user = create_user(
                    db,
                    username=username,
                    password=password,
                    role=args.role,
                )

                user_id = user.id

        # Report success only after the transaction commits.
        print("Account created successfully")
        print("User ID:", user_id)
        print("Username:", username)
        print("Role:", args.role)

        return 0

    except (ValueError, SQLAlchemyError):
        print("STOP: Account creation failed")
        print("Check database state and username availability")
        return 1

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
