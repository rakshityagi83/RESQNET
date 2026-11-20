"""Security tests for administrative account provisioning."""

import pytest

import provision_user


SAFE_URL = (
    "postgresql+psycopg://postgres:test-only"
    "@127.0.0.1:5432/resqnet_test_concurrency"
)


def test_local_database_url_accepted():
    url = provision_user.validate_database_url(SAFE_URL)

    assert url.database == "resqnet_test_concurrency"
    assert url.host == "127.0.0.1"
    assert url.port == 5432


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "sqlite://",
        SAFE_URL.replace("127.0.0.1", "remote.example"),
        SAFE_URL.replace(":5432/", ":5433/"),
        SAFE_URL.replace(
            "resqnet_test_concurrency", "resqnet_db"
        ),
        SAFE_URL + "?host=remote.example",
    ],
)
def test_unsafe_database_urls_rejected(url):
    with pytest.raises(ValueError):
        provision_user.validate_database_url(url)


@pytest.mark.parametrize(
    "password, confirmation",
    [
        ("secure-test-password-123", "different-password"),
        ("short", "short"),
        ("a" * 129, "a" * 129),
    ],
)
def test_invalid_password_never_reaches_database(
    monkeypatch, password, confirmation, capsys
):
    monkeypatch.setenv(
        "RESQNET_PG_TEST_URL",
        SAFE_URL,
    )

    values = iter([password, confirmation])

    monkeypatch.setattr(
        provision_user,
        "getpass",
        lambda prompt: next(values),
    )

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("Unexpected database access")

    monkeypatch.setattr(
        provision_user,
        "create_engine",
        forbidden_connection,
    )

    result = provision_user.main([
        "--username", "testoperator",
        "--role", "operator",
    ])

    assert result == 1

    output = capsys.readouterr().out

    assert password not in output
    assert confirmation not in output


def test_unsafe_database_stops_before_password_prompt(
    monkeypatch,
):
    monkeypatch.setenv(
        "RESQNET_PG_TEST_URL",
        SAFE_URL.replace("127.0.0.1", "remote.example"),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Unsafe provisioning continued")

    monkeypatch.setattr(provision_user, "getpass", forbidden)
    monkeypatch.setattr(provision_user, "create_engine", forbidden)

    result = provision_user.main([
        "--username", "testadmin",
        "--role", "admin",
    ])

    assert result == 1


def test_password_cannot_be_passed_as_command_argument():
    with pytest.raises(SystemExit) as error:
        provision_user.main([
            "--username", "testadmin",
            "--role", "admin",
            "--password", "test-password-123",
        ])

    assert error.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "--username", "testadmin",
            "--role", "admin",
            "--password", "sensitive-test-marker-123",
        ],
        [
            "--username", "testadmin",
            "--role", "sensitive-test-marker-123",
        ],
        [
            "--username", "testadmin",
            "--role", "admin",
            "sensitive-test-marker-123",
        ],
        [
            "--username", "testadmin",
            "--role", "admin",
            "--password=sensitive-test-marker-123",
        ],
    ],
)
def test_cli_errors_do_not_echo_sensitive_arguments(
    monkeypatch, capsys, arguments
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid CLI command continued")

    monkeypatch.setattr(
        provision_user, "getpass", forbidden
    )

    monkeypatch.setattr(
        provision_user, "create_engine", forbidden
    )

    with pytest.raises(SystemExit) as error:
        provision_user.main(arguments)

    assert error.value.code == 2

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert "sensitive-test-marker-123" not in output
    assert "Invalid command-line arguments" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--user", "testadmin", "--role", "admin"],
        ["--username", "testadmin", "--rol", "admin"],
    ],
)
def test_abbreviated_cli_arguments_rejected(arguments):
    with pytest.raises(SystemExit) as error:
        provision_user.main(arguments)

    assert error.value.code == 2


def test_cli_help_remains_available(capsys):
    with pytest.raises(SystemExit) as error:
        provision_user.main(["--help"])

    assert error.value.code == 0

    output = capsys.readouterr().out

    assert "--username" in output
    assert "--role" in output
    assert "--password" not in output
