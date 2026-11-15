
"""Tests for trusted login client IP extraction."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from auth_api import get_login_client_ip


def make_request(host, headers=None):
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "query_string": b"",
        "headers": headers or [],
        "client": (host, 12345) if host is not None else None,
    })


def test_valid_client_ip():
    request = make_request("127.0.0.1")

    assert get_login_client_ip(request) == "127.0.0.1"


def test_spoofed_forwarded_header_is_ignored():
    request = make_request(
        "127.0.0.1",
        headers=[
            (b"x-forwarded-for", b"203.0.113.99"),
        ],
    )

    assert get_login_client_ip(request) == "127.0.0.1"


@pytest.mark.parametrize("host", [None, "testclient"])
def test_missing_or_invalid_client_ip_rejected(host):
    request = make_request(host)

    with pytest.raises(HTTPException) as error:
        get_login_client_ip(request)

    assert error.value.status_code == 503
