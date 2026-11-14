
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from database import Base
from models import Warehouse, Inventory, Allocation


ADMIN_HEADERS = {"Authorization": "Bearer " + "a" * 48}
OPERATOR_HEADERS = {"Authorization": "Bearer " + "b" * 48}


@pytest.fixture
def authorized_app(monkeypatch):
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

    yield TestSession, warehouse_id

    engine.dispose()


def test_admin_can_register_warehouse(authorized_app):
    TestSession, _ = authorized_app

    with TestClient(main.app, headers=ADMIN_HEADERS) as client:
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
    TestSession, warehouse_id = authorized_app

    with TestClient(main.app, headers=ADMIN_HEADERS) as client:
        response = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json={
                "food": 150,
                "water": 300,
                "medicine": 75,
            },
        )

    assert response.status_code == 200

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)

        assert inventory.food == 150
        assert inventory.water == 300
        assert inventory.medicine == 75


@pytest.mark.parametrize(
    "headers",
    [OPERATOR_HEADERS, ADMIN_HEADERS],
    ids=["operator", "admin"],
)
def test_authorized_preview_does_not_deduct_stock(
    authorized_app, headers
):
    TestSession, warehouse_id = authorized_app

    with TestClient(main.app, headers=headers) as client:
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
