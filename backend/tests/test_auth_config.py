"""Authentication configuration safety tests."""

import pytest

from auth_config import validate_local_auth_configuration


SAFE_URL = (
    "postgresql+psycopg://postgres:test-only"
    "@127.0.0.1:5432/resqnet_test_concurrency"
)

CSRF_KEY = "test-csrf-" + "a" * 48
RATE_LIMIT_KEY = "test-rate-limit-" + "b" * 48


@pytest.fixture
def valid_configuration(monkeypatch):
    monkeypatch.setenv("RESQNET_ENV", "development")

    monkeypatch.setenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    )

    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        CSRF_KEY,
    )

    monkeypatch.setenv(
        "RESQNET_RATE_LIMIT_HMAC_KEY",
        RATE_LIMIT_KEY,
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://localhost:5174",
    ],
)
def test_valid_local_auth_configuration(
    valid_configuration, monkeypatch, origin
):
    monkeypatch.setenv("FRONTEND_URL", origin)

    validate_local_auth_configuration(SAFE_URL)


@pytest.mark.parametrize(
    "setting, value",
    [
        ("RESQNET_ENV", None),
        ("RESQNET_ENV", "production"),
        ("FRONTEND_URL", None),
        ("FRONTEND_URL", "https://untrusted.example"),
        ("FRONTEND_URL", "http://127.0.0.1:5173"),
        ("RESQNET_CSRF_HMAC_KEY", None),
        ("RESQNET_CSRF_HMAC_KEY", "short"),
        ("RESQNET_RATE_LIMIT_HMAC_KEY", None),
        ("RESQNET_RATE_LIMIT_HMAC_KEY", "short"),
        ("RESQNET_RATE_LIMIT_HMAC_KEY", CSRF_KEY),
        ("RESQNET_CSRF_HMAC_KEY", " " * 48),
        (
            "DATABASE_URL",
            SAFE_URL.replace("127.0.0.1", "remote.example"),
        ),
        (
            "DATABASE_URL",
            SAFE_URL.replace(
                "resqnet_test_concurrency", "resqnet_db"
            ),
        ),
        ("DATABASE_URL", "sqlite://"),
        ("DATABASE_URL", SAFE_URL + "?host=remote.example"),
        (
            "DATABASE_URL",
            SAFE_URL.replace(":5432/", ":5433/"),
        ),
    ],
)
def test_unsafe_auth_configuration_rejected(
    valid_configuration, monkeypatch, setting, value
):
    database_url = SAFE_URL

    if setting == "DATABASE_URL":
        database_url = value

    elif value is None:
        monkeypatch.delenv(setting, raising=False)

    else:
        monkeypatch.setenv(setting, value)

    with pytest.raises(RuntimeError) as error:
        validate_local_auth_configuration(database_url)

    message = str(error.value)

    # Configuration errors must never expose secrets.
    assert CSRF_KEY not in message
    assert RATE_LIMIT_KEY not in message
    assert "postgres:test-only" not in message
