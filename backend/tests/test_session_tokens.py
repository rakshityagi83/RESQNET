
"""Security tests for RESQNET session tokens."""

import base64
import hashlib
import re
from datetime import timedelta

from session_tokens import (
    SESSION_LIFETIME,
    generate_session_token,
    hash_session_token,
)


def test_session_token_has_256_bits_of_randomness():
    token = generate_session_token()

    padded = token + "=" * (-len(token) % 4)
    raw_bytes = base64.urlsafe_b64decode(padded)

    assert len(raw_bytes) == 32


def test_session_tokens_are_unique():
    tokens = {
        generate_session_token()
        for _ in range(100)
    }

    assert len(tokens) == 100


def test_token_hash_is_sha256():
    token = generate_session_token()
    stored_hash = hash_session_token(token)

    expected = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    assert stored_hash == expected


def test_hash_does_not_store_raw_token():
    token = generate_session_token()
    stored_hash = hash_session_token(token)

    assert stored_hash != token
    assert len(stored_hash) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", stored_hash)


def test_hashing_same_token_is_deterministic():
    token = generate_session_token()

    first_hash = hash_session_token(token)
    second_hash = hash_session_token(token)

    assert first_hash == second_hash


def test_different_tokens_produce_different_hashes():
    first_token = generate_session_token()
    second_token = generate_session_token()

    assert first_token != second_token
    assert (
        hash_session_token(first_token)
        != hash_session_token(second_token)
    )


def test_session_lifetime_is_12_hours():
    assert SESSION_LIFETIME == timedelta(hours=12)
