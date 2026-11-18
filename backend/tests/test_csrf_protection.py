
"""Security tests for RESQNET CSRF token utilities."""

import re

import pytest

from csrf_protection import (
    generate_csrf_token,
    verify_csrf_token,
)
from session_tokens import generate_session_token


@pytest.fixture(autouse=True)
def disposable_csrf_key(monkeypatch):
    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "test-only-" + "x" * 48,
    )


def test_csrf_token_is_deterministic():
    session = generate_session_token()

    first = generate_csrf_token(session)
    second = generate_csrf_token(session)

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert first != session


def test_different_sessions_have_different_csrf_tokens():
    first_session = generate_session_token()
    second_session = generate_session_token()

    assert generate_csrf_token(
        first_session
    ) != generate_csrf_token(second_session)


def test_valid_csrf_token_is_accepted():
    session = generate_session_token()
    csrf = generate_csrf_token(session)

    assert verify_csrf_token(session, csrf) is True


def test_missing_or_modified_csrf_token_is_rejected():
    session = generate_session_token()
    csrf = generate_csrf_token(session)

    assert verify_csrf_token(session, None) is False
    assert verify_csrf_token(session, "") is False
    assert verify_csrf_token(session, csrf[:-1]) is False

    modified = (
        ("0" if csrf[0] != "0" else "1") + csrf[1:]
    )

    assert verify_csrf_token(session, modified) is False


def test_token_cannot_be_used_with_another_session():
    first_session = generate_session_token()
    second_session = generate_session_token()

    csrf = generate_csrf_token(first_session)

    assert verify_csrf_token(second_session, csrf) is False


def test_malformed_session_is_rejected():
    assert verify_csrf_token("invalid", "0" * 64) is False

    with pytest.raises(ValueError):
        generate_csrf_token("invalid")


def test_missing_or_short_secret_is_rejected(monkeypatch):
    session = generate_session_token()

    monkeypatch.delenv(
        "RESQNET_CSRF_HMAC_KEY",
        raising=False,
    )

    with pytest.raises(RuntimeError):
        generate_csrf_token(session)

    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "too-short",
    )

    with pytest.raises(RuntimeError):
        generate_csrf_token(session)
