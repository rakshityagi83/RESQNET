
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from database import Base
from models import Warehouse, Inventory, Allocation




@pytest.fixture
def authorized_app(monkeypatch, session_test_headers):
    # Fake test credentials, never production secrets.
    monkeypatch.setenv("RESQNET_ADMIN_TOKEN", "a" * 48)
    monkeypatch.setenv("RESQNET_OPERATOR_TOKEN", "b" * 48)

    # Isolated database: no local PostgreSQL or Neon access.
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

    monkeypatch.setattr(main, "SessionLocal", TestSession)

    # Mock the external disaster feed.
    monkeypatch.setattr(
        main,
        "fetch_gdacs",
        lambda: [{
            "id": "TEST-INCIDENT",
            "location": "Test Location",
            "severity": "Orange",
        }],
    )

    with TestSession.begin() as session:
        warehouse = Warehouse(
            name="Authorized Access Test Warehouse",
            state="Haryana",
            district="Faridabad",
            verified_by="Automated Test",
        )

        session.add(warehouse)
        session.flush()
        warehouse_id = warehouse.id

        session.add(Inventory(
            warehouse_id=warehouse_id,
            food=100,
            water=200,
            medicine=50,
        ))

    headers = {
        role: session_test_headers(TestSession, role)[0]
        for role in ["admin", "operator"]
    }

    yield TestSession, warehouse_id, headers

    engine.dispose()


def test_admin_can_register_warehouse(authorized_app):
    TestSession, _, headers = authorized_app

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.post(
            "/warehouses",
            json={
                "name": "New Test Warehouse",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Admin",
            },
        )

    assert response.status_code == 200

    new_id = response.json()["warehouse_id"]

    with TestSession() as session:
        warehouse = session.get(Warehouse, new_id)
        inventory = session.get(Inventory, new_id)

        assert warehouse.name == "New Test Warehouse"
        assert inventory.food == 0
        assert inventory.water == 0
        assert inventory.medicine == 0


def test_admin_can_update_inventory(authorized_app):
    TestSession, warehouse_id, headers = authorized_app

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json={
                "food": 150,
                "water": 300,
                "medicine": 75,
                "expected": {
                    "food": 100,
                    "water": 200,
                    "medicine": 50,
                },
            },
        )

    assert response.status_code == 200

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)

        assert inventory.food == 150
        assert inventory.water == 300
        assert inventory.medicine == 75


@pytest.mark.parametrize(
    "role",
    ["operator", "admin"],
    ids=["operator", "admin"],
)
def test_authorized_preview_does_not_deduct_stock(
    authorized_app, role
):
    TestSession, warehouse_id, headers = authorized_app

    with TestClient(main.app, headers=headers[role]) as client:
        response = client.post(
            "/allocation/preview",
            json={
                "incident_id": "TEST-INCIDENT",
                "warehouse_id": warehouse_id,
                "food": 40,
                "water": 60,
                "medicine": 10,
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "PENDING HUMAN APPROVAL"
    assert data["proposed_allocation"] == {
        "food": 40,
        "water": 60,
        "medicine": 10,
    }

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)
        allocation = session.get(
            Allocation, data["allocation_id"]
        )

        # A preview must never deduct warehouse stock.
        assert inventory.food == 100
        assert inventory.water == 200
        assert inventory.medicine == 50

        assert allocation.status == "PENDING"


def test_atomic_warehouse_registration(authorized_app):
    TestSession, _, headers = authorized_app

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.post(
            "/warehouses",
            json={
                "name": "Atomic Registration Test",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Admin",
                "food": 500,
                "water": 1000,
                "medicine": 100,
            },
        )

    assert response.status_code == 200

    warehouse_id = response.json()["warehouse_id"]

    with TestSession() as db:
        warehouse = db.get(Warehouse, warehouse_id)
        inventory = db.get(Inventory, warehouse_id)

        assert warehouse.name == "Atomic Registration Test"
        assert inventory.food == 500
        assert inventory.water == 1000
        assert inventory.medicine == 100


@pytest.mark.parametrize(
    "invalid_stock",
    [-1, 1.5, "10", True, 2147483648],
)
def test_atomic_registration_rejects_invalid_stock(
    authorized_app,
    invalid_stock,
):
    TestSession, _, headers = authorized_app

    with TestSession() as db:
        before = db.query(Warehouse).count()

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.post(
            "/warehouses",
            json={
                "name": "Invalid Atomic Stock",
                "state": "Haryana",
                "district": "Faridabad",
                "verified_by": "Test Admin",
                "food": invalid_stock,
                "water": 100,
                "medicine": 10,
            },
        )

    assert response.status_code == 422

    with TestSession() as db:
        assert db.query(Warehouse).count() == before


def test_atomic_registration_rolls_back_on_inventory_failure(
    authorized_app,
):
    from sqlalchemy import event

    TestSession, _, headers = authorized_app

    with TestSession() as db:
        before = db.query(Warehouse).count()

    def fail_inventory_flush(session, flush_context):
        if any(
            isinstance(item, Inventory)
            for item in session.new
        ):
            raise RuntimeError(
                "Simulated inventory persistence failure"
            )

    event.listen(
        TestSession.class_,
        "after_flush",
        fail_inventory_flush,
    )

    try:
        with TestClient(main.app, headers=headers["admin"]) as client:
            with pytest.raises(
                RuntimeError,
                match="Simulated inventory persistence failure",
            ):
                client.post(
                    "/warehouses",
                    json={
                        "name": "Rollback Registration Test",
                        "state": "Haryana",
                        "district": "Faridabad",
                        "verified_by": "Test Admin",
                        "food": 50,
                        "water": 100,
                        "medicine": 5,
                    },
                )
    finally:
        event.remove(
            TestSession.class_,
            "after_flush",
            fail_inventory_flush,
        )

    with TestSession() as db:
        assert db.query(Warehouse).count() == before

        assert db.query(Warehouse).filter(
            Warehouse.name == "Rollback Registration Test"
        ).count() == 0



def test_stale_inventory_snapshot_rejected(authorized_app):
    TestSession, warehouse_id, headers = authorized_app

    # Another operation changes the displayed stock.
    with TestSession.begin() as db:
        inventory = db.get(Inventory, warehouse_id)
        inventory.food = 60

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json={
                "food": 150,
                "water": 300,
                "medicine": 75,
                "expected": {
                    "food": 100,
                    "water": 200,
                    "medicine": 50,
                },
            },
        )

    assert response.status_code == 409

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (60, 200, 50)


def test_inventory_update_requires_snapshot(authorized_app):
    TestSession, warehouse_id, headers = authorized_app

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json={
                "food": 150,
                "water": 300,
                "medicine": 75,
            },
        )

    assert response.status_code == 422

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)


@pytest.mark.parametrize(
    "invalid", [-1, 1.5, "100", True, 2147483648]
)
def test_inventory_update_rejects_invalid_snapshot(
    authorized_app, invalid
):
    TestSession, warehouse_id, headers = authorized_app

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json={
                "food": 150,
                "water": 300,
                "medicine": 75,
                "expected": {
                    "food": invalid,
                    "water": 200,
                    "medicine": 50,
                },
            },
        )

    assert response.status_code == 422

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)


def test_allocation_retry_returns_same_record(authorized_app):
    from uuid import uuid4

    TestSession, warehouse_id, headers = authorized_app

    payload = {
        "client_request_id": str(uuid4()),
        "incident_id": "TEST-INCIDENT",
        "warehouse_id": warehouse_id,
        "food": 40,
        "water": 60,
        "medicine": 10,
    }

    with TestClient(main.app, headers=headers["operator"]) as client:
        first = client.post("/allocation/preview", json=payload)
        retry = client.post("/allocation/preview", json=payload)

    assert first.status_code == 200
    assert retry.status_code == 200

    assert (
        first.json()["allocation_id"]
        == retry.json()["allocation_id"]
    )

    with TestSession() as db:
        records = db.query(Allocation).filter(
            Allocation.incident_id == "TEST-INCIDENT"
        ).all()

        assert len(records) == 1
        assert records[0].status == "PENDING"


def test_allocation_request_id_rejects_changed_payload(
    authorized_app,
):
    from uuid import uuid4

    TestSession, warehouse_id, headers = authorized_app

    payload = {
        "client_request_id": str(uuid4()),
        "incident_id": "TEST-INCIDENT",
        "warehouse_id": warehouse_id,
        "food": 40,
        "water": 60,
        "medicine": 10,
    }

    with TestClient(main.app, headers=headers["operator"]) as client:
        first = client.post("/allocation/preview", json=payload)

        changed = client.post(
            "/allocation/preview",
            json={**payload, "food": 80},
        )

    assert first.status_code == 200
    assert changed.status_code == 409

    with TestSession() as db:
        records = db.query(Allocation).filter(
            Allocation.incident_id == "TEST-INCIDENT"
        ).all()

        assert len(records) == 1


def test_zero_resource_preview_is_rejected(authorized_app):
    TestSession, warehouse_id, headers = authorized_app

    with TestClient(main.app, headers=headers["operator"]) as client:
        response = client.post(
            "/allocation/preview",
            json={
                "incident_id": "TEST-INCIDENT",
                "warehouse_id": warehouse_id,
                "food": 0,
                "water": 0,
                "medicine": 0,
            },
        )

    assert response.status_code == 422

    with TestSession() as db:
        assert db.query(Allocation).count() == 0


def test_unavailable_resources_do_not_create_pending_allocation(
    authorized_app,
):
    TestSession, warehouse_id, headers = authorized_app

    with TestSession.begin() as db:
        inventory = db.get(Inventory, warehouse_id)
        inventory.food = 0
        inventory.water = 0
        inventory.medicine = 0

    with TestClient(main.app, headers=headers["operator"]) as client:
        response = client.post(
            "/allocation/preview",
            json={
                "incident_id": "TEST-INCIDENT",
                "warehouse_id": warehouse_id,
                "food": 10,
                "water": 20,
                "medicine": 5,
            },
        )

    assert response.status_code == 409

    with TestSession() as db:
        assert db.query(Allocation).count() == 0


def test_legacy_empty_allocation_cannot_be_approved(
    authorized_app,
):
    import json

    TestSession, warehouse_id, headers = authorized_app
    allocation_id = "test-legacy-empty-allocation"

    with TestSession.begin() as db:
        db.add(Allocation(
            id=allocation_id,
            incident_id="TEST-INCIDENT",
            warehouse_id=warehouse_id,
            requirements=json.dumps({
                "requested": {
                    "food": 0,
                    "water": 0,
                    "medicine": 0,
                },
                "allocation": {
                    "food": 0,
                    "water": 0,
                    "medicine": 0,
                },
                "shortages": {
                    "food": 0,
                    "water": 0,
                    "medicine": 0,
                },
            }),
            status="PENDING",
        ))

    with TestClient(main.app, headers=headers["admin"]) as client:
        response = client.post(
            f"/allocation/{allocation_id}/approve"
        )

    assert response.status_code == 409

    with TestSession() as db:
        allocation = db.get(Allocation, allocation_id)
        inventory = db.get(Inventory, warehouse_id)

        assert allocation.status == "PENDING"
        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == (100, 200, 50)
