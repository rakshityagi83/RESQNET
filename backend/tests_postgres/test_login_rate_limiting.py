
"""PostgreSQL integration tests for RESQNET login rate limiting."""

import ipaddress
import os
import uuid
import time
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import LoginRateLimit

from login_rate_limiter import (
    RATE_LIMIT_WINDOW,
    fingerprint_username,
    fingerprint_ip,
)

from rate_limit_service import (
    utc_now,
    record_failed_login,
    login_block_remaining_seconds,
)
from rate_limit_service import acquire_login_attempt_locks

@pytest.fixture
def rate_limit_db(monkeypatch):
    raw_url = os.getenv("RESQNET_PG_TEST_URL")

    if not raw_url:
        pytest.fail("Local PostgreSQL test URL is not configured")

    url = make_url(raw_url)

    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 5432
        and url.database == "resqnet_test_concurrency"
    ):
        pytest.fail("Unsafe database URL. Tests cancelled.")

    # Disposable HMAC key, never a production secret.
    monkeypatch.setenv(
        "RESQNET_RATE_LIMIT_HMAC_KEY",
        "test-only-" + "x" * 48,
    )

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    tracked_keys = set()

    try:
        # Verify the actual connected database before any writes.
        with engine.connect() as conn:
            database, port = conn.execute(
                text(
                    "SELECT current_database(), inet_server_port()"
                )
            ).one()

            revision = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

            table_exists = conn.execute(
                text(
                    "SELECT to_regclass("
                    "'public.login_rate_limits') IS NOT NULL"
                )
            ).scalar_one()

            if (
                database != "resqnet_test_concurrency"
                or port != 5432
                or revision != "8f27c4b19d62"
                or not table_exists
            ):
                pytest.fail("Unexpected PostgreSQL test database state")

        TestSession = sessionmaker(bind=engine)

        def new_identity():
            username = "ratetest_" + uuid.uuid4().hex

            # Unique documentation-only IPv6 address for testing.
            address = (
                (0x20010DB8 << 96)
                | (uuid.uuid4().int & ((1 << 96) - 1))
            )
            ip = str(ipaddress.IPv6Address(address))

            tracked_keys.add(fingerprint_username(username))
            tracked_keys.add(fingerprint_ip(ip))

            return username, ip

        yield TestSession, new_identity

    finally:
        # Remove only the disposable records created by this fixture.
        if tracked_keys:
            with sessionmaker(bind=engine).begin() as db:
                db.execute(
                    delete(LoginRateLimit).where(
                        LoginRateLimit.key_hash.in_(tracked_keys)
                    )
                )

        engine.dispose()


def test_first_failure_creates_counters(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    with TestSession.begin() as db:
        record_failed_login(db, username, ip)

    with TestSession() as db:
        username_record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        ip_record = db.get(
            LoginRateLimit,
            fingerprint_ip(ip),
        )

        assert username_record.failed_attempts == 1
        assert ip_record.failed_attempts == 1
        assert login_block_remaining_seconds(
            db, username, ip
        ) == 0


def test_username_blocked_after_five_failures(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    for _ in range(5):
        with TestSession.begin() as db:
            record_failed_login(db, username, ip)

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )

        assert record.failed_attempts == 5
        assert record.blocked_until is not None
        assert login_block_remaining_seconds(
            db, username, ip
        ) > 0


def test_ip_blocked_after_twenty_failures(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    _, shared_ip = new_identity()

    # Different usernames, but the same IP address.
    for _ in range(20):
        username, _ = new_identity()

        with TestSession.begin() as db:
            record_failed_login(
                db, username, shared_ip
            )

    with TestSession() as db:
        ip_record = db.get(
            LoginRateLimit,
            fingerprint_ip(shared_ip),
        )

        assert ip_record.failed_attempts == 20
        assert ip_record.blocked_until is not None


def test_expired_window_resets_counter(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    with TestSession.begin() as db:
        record_failed_login(db, username, ip)

    with TestSession.begin() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        record.window_started_at = (
            utc_now() - RATE_LIMIT_WINDOW - timedelta(seconds=5)
        )

    with TestSession.begin() as db:
        record_failed_login(db, username, ip)

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        assert record.failed_attempts == 1


def test_active_block_does_not_increase_counter(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    for _ in range(5):
        with TestSession.begin() as db:
            record_failed_login(db, username, ip)

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        original_block = record.blocked_until

    with TestSession.begin() as db:
        record_failed_login(db, username, ip)

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )

        assert record.failed_attempts == 5
        assert record.blocked_until == original_block


def test_expired_block_allows_new_window(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    for _ in range(5):
        with TestSession.begin() as db:
            record_failed_login(db, username, ip)

    with TestSession.begin() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )
        record.window_started_at = utc_now() - timedelta(minutes=20)
        record.blocked_until = utc_now() - timedelta(seconds=1)

    with TestSession.begin() as db:
        record_failed_login(db, username, ip)

    with TestSession() as db:
        record = db.get(
            LoginRateLimit,
            fingerprint_username(username),
        )

        assert record.failed_attempts == 1
        assert record.blocked_until is None


def test_failed_transaction_does_not_save_counters(rate_limit_db):
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    with pytest.raises(RuntimeError):
        with TestSession.begin() as db:
            record_failed_login(db, username, ip)
            raise RuntimeError("Simulated transaction failure")

    with TestSession() as db:
        assert db.get(
            LoginRateLimit,
            fingerprint_username(username),
        ) is None

        assert db.get(
            LoginRateLimit,
            fingerprint_ip(ip),
        ) is None


def test_concurrent_failures_are_counted_atomically(rate_limit_db):
    TestSession, new_identity = rate_limit_db

    _, shared_ip = new_identity()
    usernames = [
        new_identity()[0]
        for _ in range(8)
    ]

    barrier = Barrier(8)

    def record_one(username):
        barrier.wait(timeout=15)

        with TestSession.begin() as db:
            record_failed_login(db, username, shared_ip)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(record_one, username)
            for username in usernames
        ]

        for future in futures:
            future.result(timeout=40)

    with TestSession() as db:
        ip_record = db.get(
            LoginRateLimit,
            fingerprint_ip(shared_ip),
        )

        # No increments may be lost under concurrency.
        assert ip_record.failed_attempts == 8
        assert ip_record.blocked_until is None

def test_concurrent_login_attempts_are_serialized(rate_limit_db):
    """A second login for the same identity must wait for the first."""
    TestSession, new_identity = rate_limit_db
    username, ip = new_identity()

    waiting_pid = Queue(maxsize=1)

    def second_login_attempt():
        with TestSession.begin() as db:
            pid = db.scalar(text("SELECT pg_backend_pid()"))
            waiting_pid.put(pid)

            acquire_login_attempt_locks(db, username, ip)

        return True

    with ThreadPoolExecutor(max_workers=1) as executor:
        with TestSession.begin() as first_session:
            acquire_login_attempt_locks(
                first_session,
                username,
                ip,
            )

            # The first transaction now holds both identity locks.
            future = executor.submit(second_login_attempt)
            second_pid = waiting_pid.get(timeout=10)

            # Observe PostgreSQL's actual lock-wait state.
            deadline = time.monotonic() + 8
            observed_wait = False

            while time.monotonic() < deadline:
                with first_session.get_bind().connect() as observer:
                    observed_wait = observer.scalar(
                        text("""
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_locks
                                WHERE pid = :pid
                                  AND locktype = 'advisory'
                                  AND NOT granted
                            )
                        """),
                        {"pid": second_pid},
                    )

                if observed_wait:
                    break

                time.sleep(0.05)

            assert observed_wait, (
                "Second login did not wait for the identity lock"
            )
            assert not future.done()

        # First transaction ended, releasing its advisory locks.
        # Second login must now be able to continue.
        assert future.result(timeout=15) is True
