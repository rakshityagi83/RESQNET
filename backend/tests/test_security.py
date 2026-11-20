
import pytest
from fastapi.testclient import TestClient

import main
import session_authorization
from database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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
def test_session_factory(session_test_headers):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(bind=engine)

    try:
        yield lambda role: session_test_headers(
            TestSession, role
        )[0]
    finally:
        engine.dispose()


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
    monkeypatch, test_session_factory, method, path, payload
):
    def forbid_database_access(*args, **kwargs):
        raise AssertionError("Unauthorized database access")

    monkeypatch.setattr(main, "SessionLocal", forbid_database_access)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.request(
            method,
            path,
            headers=test_session_factory("operator"),
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
            headers={"Cookie": "resqnet_session=invalid-token"},
            json={"food": 100, "water": 200, "medicine": 50},
        )

    assert response.status_code == 401


def test_legacy_bearer_without_configuration_rejected(monkeypatch):
    monkeypatch.delenv("RESQNET_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("RESQNET_OPERATOR_TOKEN", raising=False)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.put(
            "/warehouses/1/inventory",
            headers={"Authorization": "Bearer example-token"},
            json={"food": 100, "water": 200, "medicine": 50},
        )

    assert response.status_code == 401



def test_missing_csrf_secret_fails_closed(
    monkeypatch, test_session_factory
):
    headers = test_session_factory("admin")

    monkeypatch.delenv(
        "RESQNET_CSRF_HMAC_KEY",
        raising=False,
    )

    accesses = []

    def forbid_database_access(*args, **kwargs):
        accesses.append(True)
        raise AssertionError("Unsafe application write")

    monkeypatch.setattr(
        main, "SessionLocal", forbid_database_access
    )

    with TestClient(
        main.app,
        raise_server_exceptions=False,
    ) as client:
        response = client.put(
            "/warehouses/1/inventory",
            headers=headers,
            json={
                "food": 100,
                "water": 200,
                "medicine": 50,
            },
        )

    assert response.status_code == 500
    assert accesses == []
