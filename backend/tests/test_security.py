
import pytest
from fastapi.testclient import TestClient

import main


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "POST",
            "/warehouses",
            {
                "name": "Security Test Warehouse",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Operator",
            },
        ),
        (
            "PUT",
            "/warehouses/1/inventory",
            {
                "food": 100,
                "water": 200,
                "medicine": 50,
            },
        ),
        (
            "POST",
            "/allocation/preview",
            {
                "incident_id": "TEST-INCIDENT",
                "warehouse_id": 1,
                "food": 10,
                "water": 20,
                "medicine": 5,
            },
        ),
        (
            "POST",
            "/allocation/test-allocation/approve",
            {},
        ),
    ],
)
def test_unauthenticated_writes_rejected(
    monkeypatch, method, path, payload
):
    # An unauthenticated request must never reach
    # the application database.
    def forbid_database_access(*args, **kwargs):
        raise AssertionError(
            "Unauthenticated request reached database"
        )

    monkeypatch.setattr(
        main, "SessionLocal", forbid_database_access
    )

    # Prevent external GDACS network requests.
    monkeypatch.setattr(
        main, "fetch_gdacs", lambda: []
    )

    with TestClient(
        main.app,
        raise_server_exceptions=False
    ) as client:
        response = client.request(
            method,
            path,
            json=payload
        )

    assert response.status_code == 401, (
        f"{method} {path} returned "
        f"{response.status_code}, expected 401"
    )

@pytest.fixture
def configured_test_tokens(monkeypatch):
    # These are disposable test credentials, not real secrets.
    monkeypatch.setenv("RESQNET_ADMIN_TOKEN", "a" * 48)
    monkeypatch.setenv("RESQNET_OPERATOR_TOKEN", "b" * 48)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        (
            "POST",
            "/warehouses",
            {
                "name": "Test Warehouse",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Operator",
            },
        ),
        (
            "PUT",
            "/warehouses/1/inventory",
            {"food": 100, "water": 200, "medicine": 50},
        ),
        (
            "POST",
            "/allocation/test-allocation/approve",
            {},
        ),
    ],
)
def test_operator_cannot_perform_admin_actions(
    monkeypatch, configured_test_tokens, method, path, payload
):
    def forbid_database_access(*args, **kwargs):
        raise AssertionError("Unauthorized database access")

    monkeypatch.setattr(main, "SessionLocal", forbid_database_access)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.request(
            method,
            path,
            headers={"Authorization": "Bearer " + "b" * 48},
            json=payload,
        )

    assert response.status_code == 403


def test_invalid_token_rejected(monkeypatch, configured_test_tokens):
    def forbid_database_access(*args, **kwargs):
        raise AssertionError("Invalid token reached database")

    monkeypatch.setattr(main, "SessionLocal", forbid_database_access)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.put(
            "/warehouses/1/inventory",
            headers={"Authorization": "Bearer invalid-token"},
            json={"food": 100, "water": 200, "medicine": 50},
        )

    assert response.status_code == 401


def test_missing_token_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("RESQNET_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("RESQNET_OPERATOR_TOKEN", raising=False)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.put(
            "/warehouses/1/inventory",
            headers={"Authorization": "Bearer example-token"},
            json={"food": 100, "water": 200, "medicine": 50},
        )

    assert response.status_code == 503
