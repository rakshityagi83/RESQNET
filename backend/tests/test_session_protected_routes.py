"""Session authorization tests for actual RESQNET write routes."""

import json

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import security
import session_authorization

from database import Base
from models import User, Warehouse, Inventory, Allocation
from session_service import create_session
from csrf_protection import generate_csrf_token


ORIGIN = "http://localhost:5173"


@pytest.fixture
def session_protected_app(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(
        bind=engine,
        autoflush=False,
    )

    monkeypatch.setenv("RESQNET_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", ORIGIN)

    monkeypatch.setenv(
        "RESQNET_CSRF_HMAC_KEY",
        "test-only-" + "x" * 48,
    )

    monkeypatch.setenv(
        "RESQNET_ADMIN_TOKEN",
        "a" * 48,
    )

    monkeypatch.setenv(
        "RESQNET_OPERATOR_TOKEN",
        "b" * 48,
    )

    monkeypatch.setattr(
        main,
        "SessionLocal",
        TestSession,
    )

    monkeypatch.setattr(
        session_authorization,
        "SessionLocal",
        TestSession,
    )

    # Test-only replacement of the existing authorization
    # dependencies. Production route configuration is unchanged.
    monkeypatch.setitem(
        main.app.dependency_overrides,
        security.require_admin,
        session_authorization.require_admin_write,
    )

    monkeypatch.setitem(
        main.app.dependency_overrides,
        security.require_operator,
        session_authorization.require_operator_write,
    )

    # Deterministic external feed for isolated testing.
    monkeypatch.setattr(
        main,
        "fetch_gdacs",
        lambda: [{
            "id": "TEST-INCIDENT",
            "location": "Test Location",
            "severity": "Orange",
        }],
    )

    tokens = {}

    try:
        with TestSession.begin() as db:
            for role in ["admin", "operator"]:
                user = User(
                    username="integration_" + role,
                    password_hash="unused-test-hash",
                    role=role,
                    is_active=True,
                )

                db.add(user)
                db.flush()

                tokens[role] = create_session(db, user.id)

            warehouse = Warehouse(
                name="Session Integration Warehouse",
                state="Haryana",
                district="Faridabad",
                verified_by="Automated Test",
            )

            db.add(warehouse)
            db.flush()

            warehouse_id = warehouse.id

            db.add(Inventory(
                warehouse_id=warehouse_id,
                food=100,
                water=200,
                medicine=50,
            ))

            db.add(Allocation(
                id="session-test-allocation",
                incident_id="TEST-INCIDENT",
                warehouse_id=warehouse_id,
                requirements=json.dumps({
                    "requested": {
                        "food": 40,
                        "water": 60,
                        "medicine": 10,
                    },
                    "allocation": {
                        "food": 40,
                        "water": 60,
                        "medicine": 10,
                    },
                    "shortages": {
                        "food": 0,
                        "water": 0,
                        "medicine": 0,
                    },
                }),
                status="PENDING",
            ))

        yield TestSession, warehouse_id, tokens

    finally:
        engine.dispose()


def database_snapshot(TestSession):
    """Capture application records to detect unauthorized writes."""

    with TestSession() as db:
        warehouses = db.scalars(
            select(Warehouse).order_by(Warehouse.id)
        ).all()

        inventories = db.scalars(
            select(Inventory).order_by(Inventory.warehouse_id)
        ).all()

        allocations = db.scalars(
            select(Allocation).order_by(Allocation.id)
        ).all()

        return {
            "warehouses": [
                (w.id, w.name, w.state, w.district)
                for w in warehouses
            ],
            "inventory": [
                (i.warehouse_id, i.food, i.water, i.medicine)
                for i in inventories
            ],
            "allocations": [
                (a.id, a.status, a.requirements)
                for a in allocations
            ],
        }


def send_write(client, operation, warehouse_id, headers):
    stock = {
        "food": 40,
        "water": 60,
        "medicine": 10,
    }

    if operation == "register":
        return client.post(
            "/warehouses",
            headers=headers,
            json={
                "name": "New Session Warehouse",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Admin",
            },
        )

    if operation == "inventory":
        return client.put(
            f"/warehouses/{warehouse_id}/inventory",
            headers=headers,
            json=stock,
        )

    if operation == "preview":
        return client.post(
            "/allocation/preview",
            headers=headers,
            json={
                "incident_id": "TEST-INCIDENT",
                "warehouse_id": warehouse_id,
                **stock,
            },
        )

    if operation == "approve":
        return client.post(
            "/allocation/session-test-allocation/approve",
            headers=headers,
        )

    raise AssertionError("Unknown operation")


@pytest.mark.parametrize(
    "operation",
    ["register", "inventory", "preview", "approve"],
)
@pytest.mark.parametrize(
    "condition",
    [
        "anonymous",
        "legacy_bearer",
        "missing_csrf",
        "invalid_csrf",
        "untrusted_origin",
        "operator",
        "admin",
    ],
)
def test_actual_write_route_security(
    session_protected_app, operation, condition
):
    TestSession, warehouse_id, tokens = session_protected_app

    before = database_snapshot(TestSession)

    headers = {"Origin": ORIGIN}

    with TestClient(main.app) as client:
        if condition == "anonymous":
            expected = 401

        elif condition == "legacy_bearer":
            headers["Authorization"] = "Bearer " + "a" * 48
            expected = 401

        else:
            role = (
                "operator"
                if condition == "operator"
                else "admin"
            )

            token = tokens[role]

            client.cookies.set(
                "resqnet_session",
                token,
            )

            headers["X-CSRF-Token"] = (
                generate_csrf_token(token)
            )

            if condition == "missing_csrf":
                headers.pop("X-CSRF-Token")
                expected = 403

            elif condition == "invalid_csrf":
                headers["X-CSRF-Token"] = "0" * 64
                expected = 403

            elif condition == "untrusted_origin":
                headers["Origin"] = "https://untrusted.example"
                expected = 403

            elif condition == "operator":
                expected = 200 if operation == "preview" else 403

            else:
                expected = 200

        response = send_write(
            client,
            operation,
            warehouse_id,
            headers,
        )

    assert response.status_code == expected

    after = database_snapshot(TestSession)

    if expected != 200:
        # Rejected requests must not modify application data.
        assert after == before
        return

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        if operation == "register":
            new_id = response.json()["warehouse_id"]

            assert db.get(Warehouse, new_id) is not None

            new_inventory = db.get(Inventory, new_id)
            assert new_inventory.food == 0

        elif operation == "inventory":
            assert inventory.food == 40
            assert inventory.water == 60
            assert inventory.medicine == 10

        elif operation == "preview":
            allocation = db.get(
                Allocation,
                response.json()["allocation_id"],
            )

            assert allocation.status == "PENDING"

            # Preview must not deduct stock.
            assert inventory.food == 100
            assert inventory.water == 200
            assert inventory.medicine == 50

        elif operation == "approve":
            allocation = db.get(
                Allocation,
                "session-test-allocation",
            )

            assert allocation.status == "APPROVED"
            assert inventory.food == 60
            assert inventory.water == 140
            assert inventory.medicine == 40
