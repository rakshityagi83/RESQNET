
"""PostgreSQL-backed login rate limiting for RESQNET."""

import math
from datetime import datetime, timezone

from sqlalchemy import and_, case, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import LoginRateLimit
from login_rate_limiter import (
    USERNAME_MAX_FAILURES,
    IP_MAX_FAILURES,
    RATE_LIMIT_WINDOW,
    BLOCK_DURATION,
    fingerprint_username,
    fingerprint_ip,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_one_failure(
    db: Session,
    key_hash: str,
    failure_limit: int,
    now: datetime,
) -> None:
    """Atomically record one failed attempt for one identity."""

    table = LoginRateLimit.__table__

    currently_blocked = table.c.blocked_until > now

    window_expired = and_(
        table.c.window_started_at <= now - RATE_LIMIT_WINDOW,
        or_(
            table.c.blocked_until.is_(None),
            table.c.blocked_until <= now,
        ),
    )

    next_count = case(
        (
            currently_blocked,
            table.c.failed_attempts,
        ),
        (
            window_expired,
            1,
        ),
        else_=table.c.failed_attempts + 1,
    )

    next_window_start = case(
        (
            window_expired,
            now,
        ),
        else_=table.c.window_started_at,
    )

    next_blocked_until = case(
        (
            currently_blocked,
            table.c.blocked_until,
        ),
        (
            next_count >= failure_limit,
            now + BLOCK_DURATION,
        ),
        else_=None,
    )

    statement = insert(table).values(
        key_hash=key_hash,
        failed_attempts=1,
        window_started_at=now,
        blocked_until=None,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key_hash],
        set_={
            "failed_attempts": next_count,
            "window_started_at": next_window_start,
            "blocked_until": next_blocked_until,
        },
    )

    db.execute(statement)


def record_failed_login(
    db: Session,
    username: str,
    client_ip: str,
) -> None:
    """Record a failed login against username and IP buckets.

    Caller must commit the transaction.
    """

    now = utc_now()

    record_one_failure(
        db,
        fingerprint_username(username),
        USERNAME_MAX_FAILURES,
        now,
    )

    record_one_failure(
        db,
        fingerprint_ip(client_ip),
        IP_MAX_FAILURES,
        now,
    )


def login_block_remaining_seconds(
    db: Session,
    username: str,
    client_ip: str,
) -> int:
    """Return remaining block time, or zero if login is allowed."""

    now = utc_now()

    identities = [
        fingerprint_username(username),
        fingerprint_ip(client_ip),
    ]

    blocked_times = db.scalars(
        select(LoginRateLimit.blocked_until).where(
            LoginRateLimit.key_hash.in_(identities),
            LoginRateLimit.blocked_until > now,
        )
    ).all()

    if not blocked_times:
        return 0

    remaining = max(
        (blocked_until - now).total_seconds()
        for blocked_until in blocked_times
    )

    return max(1, math.ceil(remaining))

def acquire_login_attempt_locks(
    db: Session,
    username: str,
    client_ip: str,
) -> None:
    """Serialize login attempts sharing a username or client IP.

    Must run inside the same PostgreSQL transaction as:
    1. Checking whether login is blocked.
    2. Authenticating the credentials.
    3. Recording a failed login, when applicable.

    PostgreSQL releases these locks when the transaction ends.
    """
    if db.get_bind().dialect.name != "postgresql":
        raise RuntimeError(
            "Login admission locking requires PostgreSQL"
        )

    identities = {
        fingerprint_username(username),
        fingerprint_ip(client_ip),
    }

    # Convert HMAC fingerprints into signed 64-bit lock IDs.
    lock_ids = sorted({
        int.from_bytes(
            bytes.fromhex(identity[:16]),
            byteorder="big",
            signed=True,
        )
        for identity in identities
    })

    # Deterministic ordering helps prevent deadlocks.
    for lock_id in lock_ids:
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
