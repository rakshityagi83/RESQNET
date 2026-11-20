"""Tests for shared browser origin and CORS security."""

import pytest

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from browser_security import (
    get_trusted_origins,
    check_trusted_origin,
    configure_browser_cors,
)


@pytest.mark.parametrize(
    "environment, frontend, expected",
    [
        (
            "production",
            "https://resqnet.example/",
            {"https://resqnet.example"},
        ),
        (
            "production",
            "http://localhost:5173",
            set(),
        ),
        (
            None,
            None,
            set(),
        ),
        (
            "development",
            None,
            {
                "http://localhost:5173",
                "http://localhost:5174",
            },
        ),
        (
            "development",
            "http://127.0.0.1:5173",
            {
                "http://localhost:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5173",
            },
        ),
        (
            "production",
            "*",
            set(),
        ),
        (
            "production",
            "https://resqnet.example/dashboard",
            set(),
        ),
        (
            "production",
            "https://user:password@resqnet.example",
            set(),
        ),
    ],
)
def test_trusted_origin_configuration(
    monkeypatch, environment, frontend, expected
):
    monkeypatch.delenv("RESQNET_ENV", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)

    if environment is not None:
        monkeypatch.setenv("RESQNET_ENV", environment)

    if frontend is not None:
        monkeypatch.setenv("FRONTEND_URL", frontend)

    assert set(get_trusted_origins()) == expected


@pytest.mark.parametrize(
    "environment, origin, allowed",
    [
        (
            "development",
            "http://localhost:5173",
            True,
        ),
        (
            "production",
            "https://resqnet.example",
            True,
        ),
        (
            "production",
            "http://localhost:5173",
            False,
        ),
        (
            "production",
            "https://untrusted.example",
            False,
        ),
    ],
)
def test_cors_and_origin_validation_agree(
    monkeypatch, environment, origin, allowed
):
    monkeypatch.setenv("RESQNET_ENV", environment)

    monkeypatch.setenv(
        "FRONTEND_URL",
        "https://resqnet.example",
    )

    app = FastAPI()

    configure_browser_cors(app)

    @app.post(
        "/protected",
        dependencies=[Depends(check_trusted_origin)],
    )
    def protected():
        return {"status": "permitted"}

    with TestClient(app) as client:
        preflight = client.options(
            "/protected",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers":
                    "content-type,x-csrf-token",
            },
        )

        actual = client.post(
            "/protected",
            headers={"Origin": origin},
        )

    if allowed:
        assert preflight.status_code == 200

        assert preflight.headers[
            "access-control-allow-origin"
        ] == origin

        assert preflight.headers[
            "access-control-allow-credentials"
        ] == "true"

        assert actual.status_code == 200

        assert actual.headers[
            "access-control-allow-origin"
        ] == origin

    else:
        assert preflight.status_code == 400
        assert actual.status_code == 403

        assert (
            "access-control-allow-origin"
            not in preflight.headers
        )

        assert (
            "access-control-allow-origin"
            not in actual.headers
        )
