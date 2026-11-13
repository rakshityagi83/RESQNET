
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from database import Base
from models import Warehouse, Inventory, Allocation


@pytest.fixture
def admin_headers(monkeypatch):
    # Disposable test credentials only.
    monkeypatch.setenv("RESQNET_ADMIN_TOKEN", "a" * 48)
    monkeypatch.setenv("RESQNET_OPERATOR_TOKEN", "b" * 48)

    return {
        "Authorization": "Bearer " + "a" * 48
    }


@pytest.fixture
def isolated_db(monkeypatch):
    # Use an isolated SQLite database, NOT real PostgreSQL.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    Base.metadata.create_all(engine)

    TestSession = sessionmaker(
        bind=engine,
        autoflush=False
    )

    monkeypatch.setattr(main, "SessionLocal", TestSession)

    with TestSession.begin() as session:
        warehouse = Warehouse(
            name="Test Warehouse",
            state="Haryana",
            district="Faridabad",
            verified_by="Automated Test"
        )

        session.add(warehouse)
        session.flush()

        warehouse_id = warehouse.id

        session.add(Inventory(
            warehouse_id=warehouse_id,
            food=100,
            water=200,
            medicine=50
        ))

        session.add(Allocation(
            id="test-allocation-001",
            incident_id="TEST-INCIDENT",
            warehouse_id=warehouse_id,
            requirements=json.dumps({
                "requested": {
                    "food": 40,
                    "water": 60,
                    "medicine": 10
                },
                "allocation": {
                    "food": 40,
                    "water": 60,
                    "medicine": 10
                },
                "shortages": {
                    "food": 0,
                    "water": 0,
                    "medicine": 0
                }
            }),
            status="PENDING"
        ))

    yield TestSession, warehouse_id

    engine.dispose()


def test_approval_deducts_inventory(isolated_db, admin_headers):
    TestSession, warehouse_id = isolated_db

    with TestClient(main.app, headers=admin_headers) as client:
        response = client.post(
            "/allocation/test-allocation-001/approve"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)
        allocation = session.get(
            Allocation, "test-allocation-001"
        )

        assert inventory.food == 60
        assert inventory.water == 140
        assert inventory.medicine == 40
        assert allocation.status == "APPROVED"


def test_duplicate_approval_rejected(isolated_db, admin_headers):
    TestSession, warehouse_id = isolated_db

    with TestClient(main.app, headers=admin_headers) as client:
        first = client.post(
            "/allocation/test-allocation-001/approve"
        )
        second = client.post(
            "/allocation/test-allocation-001/approve"
        )

    assert first.status_code == 200
    assert second.status_code == 409

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)

        assert inventory.food == 60
        assert inventory.water == 140
        assert inventory.medicine == 40


def test_insufficient_stock_rejected(isolated_db, admin_headers):
    TestSession, warehouse_id = isolated_db

    # Simulate inventory decreasing after preview.
    with TestSession.begin() as session:
        inventory = session.get(Inventory, warehouse_id)
        inventory.food = 20

    with TestClient(main.app, headers=admin_headers) as client:
        response = client.post(
            "/allocation/test-allocation-001/approve"
        )

    assert response.status_code == 409

    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)
        allocation = session.get(
            Allocation, "test-allocation-001"
        )

        assert inventory.food == 20
        assert inventory.water == 200
        assert inventory.medicine == 50
        assert allocation.status == "PENDING"
