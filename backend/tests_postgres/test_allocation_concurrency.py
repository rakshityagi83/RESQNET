
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import main
from models import (
    Warehouse, Inventory, Allocation, User, UserSession,
)


@pytest.fixture
def admin_headers(postgres_session, session_test_headers):
    TestSession = postgres_session

    headers, user_id = session_test_headers(
        TestSession, "admin"
    )

    try:
        yield headers

    finally:
        with TestSession.begin() as db:
            db.query(UserSession).filter(
                UserSession.user_id == user_id
            ).delete(synchronize_session=False)

            db.query(User).filter(
                User.id == user_id
            ).delete(synchronize_session=False)


@pytest.fixture
def postgres_session(monkeypatch):
    raw_url = os.getenv("RESQNET_PG_TEST_URL")

    if not raw_url:
        pytest.fail(
            "RESQNET_PG_TEST_URL must be explicitly configured."
        )

    url = make_url(raw_url)

    # Reject production, cloud, and other local databases.
    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 5432
        and url.database == "resqnet_test_concurrency"
    ):
        pytest.fail("Unsafe database URL. Test cancelled.")

    engine = create_engine(url, pool_pre_ping=True)

    try:
        # Independently verify the actual connected server.

        with engine.connect() as connection:
            database, port = connection.execute(
                text(
                    "SELECT current_database(), "
                    "inet_server_port()"
                )
            ).one()

        if (
            database != "resqnet_test_concurrency"
            or port != 5432
        ):
            pytest.fail("Database identity mismatch.")


        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

            if revision != "8f27c4b19d62":
                pytest.fail("Unexpected test schema revision")

            for table in ("users", "user_sessions"):
                exists = connection.execute(
                    text("SELECT to_regclass(:table)"),
                    {"table": table},
                ).scalar_one()

                if exists is None:
                    pytest.fail("Required test table missing")

        TestSession = sessionmaker(
            bind=engine,
            autoflush=False
        )

        # API approvals must use our verified test database.
        monkeypatch.setattr(main, "SessionLocal", TestSession)

        yield TestSession

    finally:
        engine.dispose()


@pytest.fixture
def two_pending_allocations(
    postgres_session,
    admin_headers,
):
    TestSession = postgres_session

    allocation_ids = [
        str(uuid.uuid4()),
        str(uuid.uuid4())
    ]

    warehouse_id = None

    try:
        with TestSession.begin() as session:
            warehouse = Warehouse(
                name="Concurrency Test Warehouse",
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
                water=0,
                medicine=0
            ))

            for allocation_id in allocation_ids:
                session.add(Allocation(
                    id=allocation_id,
                    incident_id="TEST-CONCURRENT",
                    warehouse_id=warehouse_id,
                    requirements=json.dumps({
                        "requested": {
                            "food": 80,
                            "water": 0,
                            "medicine": 0
                        },
                        "allocation": {
                            "food": 80,
                            "water": 0,
                            "medicine": 0
                        },
                        "shortages": {
                            "food": 0,
                            "water": 0,
                            "medicine": 0
                        }
                    }),
                    status="PENDING"
                ))

        yield TestSession, warehouse_id, allocation_ids

    finally:
        # Delete only the records created by this test.
        if warehouse_id is not None:
            with TestSession.begin() as session:
                session.query(Allocation).filter(
                    Allocation.id.in_(allocation_ids)
                ).delete(synchronize_session=False)

                session.query(Inventory).filter(
                    Inventory.warehouse_id == warehouse_id
                ).delete(synchronize_session=False)

                session.query(Warehouse).filter(
                    Warehouse.id == warehouse_id
                ).delete(synchronize_session=False)

def test_concurrent_approvals_cannot_overdraw(
    two_pending_allocations, admin_headers
):
    TestSession, warehouse_id, allocation_ids = (
        two_pending_allocations
    )

    # Both workers begin their approval requests together.
    barrier = Barrier(2)

    def approve(allocation_id):
        with TestClient(main.app, headers=admin_headers) as client:
            barrier.wait(timeout=10)

            response = client.post(
                f"/allocation/{allocation_id}/approve"
            )

            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(approve, allocation_id)
            for allocation_id in allocation_ids
        ]

        status_codes = [
            future.result(timeout=30)
            for future in futures
        ]

    # Exactly one approval must succeed.
    assert sorted(status_codes) == [200, 409]

    with TestSession() as session:
        inventory = session.get(
            Inventory, warehouse_id
        )

        allocations = [
            session.get(Allocation, allocation_id)
            for allocation_id in allocation_ids
        ]

        assert inventory.food == 20
        assert inventory.water == 0
        assert inventory.medicine == 0

        statuses = sorted(
            allocation.status for allocation in allocations
        )

        assert statuses == ["APPROVED", "PENDING"]

def test_same_allocation_approved_only_once(
    two_pending_allocations, admin_headers
):
    TestSession, warehouse_id, allocation_ids = (
        two_pending_allocations
    )

    allocation_id = allocation_ids[0]
    barrier = Barrier(2)

    def approve_same_allocation():
        with TestClient(main.app, headers=admin_headers) as client:
            barrier.wait(timeout=10)

            response = client.post(
                f"/allocation/{allocation_id}/approve"
            )

            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(approve_same_allocation)
            for _ in range(2)
        ]

        status_codes = [
            future.result(timeout=30)
            for future in futures
        ]

    # Only one request can approve the allocation.
    assert sorted(status_codes) == [200, 409]

    with TestSession() as session:
        inventory = session.get(
            Inventory, warehouse_id
        )

        allocation = session.get(
            Allocation, allocation_id
        )

        other_allocation = session.get(
            Allocation, allocation_ids[1]
        )

        # Exactly one deduction of 80 food units.
        assert inventory.food == 20
        assert inventory.water == 0
        assert inventory.medicine == 0

        assert allocation.status == "APPROVED"
        assert other_allocation.status == "PENDING"

def test_approval_rolls_back_after_database_write(
    two_pending_allocations, admin_headers
):
    from sqlalchemy import event

    TestSession, warehouse_id, allocation_ids = (
        two_pending_allocations
    )

    allocation_id = allocation_ids[0]

    # Simulate a failure after SQL UPDATE statements
    # have executed but before the transaction commits.
    def simulate_failure(session, flush_context):
        for obj in session.dirty:
            if (
                isinstance(obj, Allocation)
                and obj.id == allocation_id
                and obj.status == "APPROVED"
            ):
                raise RuntimeError(
                    "Simulated failure after database write"
                )

    event.listen(
        TestSession.class_,
        "after_flush",
        simulate_failure
    )

    try:
        with TestClient(main.app, headers=admin_headers) as client:
            with pytest.raises(
                RuntimeError,
                match="Simulated failure after database write"
            ):
                client.post(
                    f"/allocation/{allocation_id}/approve"
                )
    finally:
        event.remove(
            TestSession.class_,
            "after_flush",
            simulate_failure
        )

    # Check persisted state using a fresh session.
    with TestSession() as session:
        inventory = session.get(Inventory, warehouse_id)

        allocation = session.get(
            Allocation, allocation_id
        )

        assert inventory.food == 100
        assert inventory.water == 0
        assert inventory.medicine == 0

        assert allocation.status == "PENDING"


def inventory_update_request(food):
    return {
        "food": food,
        "water": 0,
        "medicine": 0,
        "expected": {
            "food": 100,
            "water": 0,
            "medicine": 0,
        },
    }


def test_concurrent_inventory_writes_prevent_lost_update(
    two_pending_allocations, admin_headers
):
    TestSession, warehouse_id, _ = two_pending_allocations
    barrier = Barrier(2)

    def update_stock(food):
        with TestClient(main.app, headers=admin_headers) as client:
            barrier.wait(timeout=10)

            response = client.put(
                f"/warehouses/{warehouse_id}/inventory",
                json=inventory_update_request(food),
            )

            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(update_stock, 120)
        second = executor.submit(update_stock, 130)

        statuses = [
            first.result(timeout=30),
            second.result(timeout=30),
        ]

    assert sorted(statuses) == [200, 409]

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert inventory.food in (120, 130)
        assert inventory.water == 0
        assert inventory.medicine == 0


def test_inventory_update_rejects_stock_after_approval(
    two_pending_allocations, admin_headers
):
    TestSession, warehouse_id, allocation_ids = (
        two_pending_allocations
    )

    with TestClient(main.app, headers=admin_headers) as client:
        approved = client.post(
            f"/allocation/{allocation_ids[0]}/approve"
        )

        assert approved.status_code == 200

        stale_update = client.put(
            f"/warehouses/{warehouse_id}/inventory",
            json=inventory_update_request(120),
        )

        assert stale_update.status_code == 409

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        allocation = db.get(Allocation, allocation_ids[0])

        assert inventory.food == 20
        assert allocation.status == "APPROVED"


def test_concurrent_approval_and_inventory_write_preserve_stock(
    two_pending_allocations, admin_headers
):
    TestSession, warehouse_id, allocation_ids = (
        two_pending_allocations
    )

    barrier = Barrier(2)

    def approve():
        with TestClient(main.app, headers=admin_headers) as client:
            barrier.wait(timeout=10)

            response = client.post(
                f"/allocation/{allocation_ids[0]}/approve"
            )

            return response.status_code

    def update_stock():
        with TestClient(main.app, headers=admin_headers) as client:
            barrier.wait(timeout=10)

            response = client.put(
                f"/warehouses/{warehouse_id}/inventory",
                json=inventory_update_request(120),
            )

            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        approval_future = executor.submit(approve)
        update_future = executor.submit(update_stock)

        approval_status = approval_future.result(timeout=30)
        update_status = update_future.result(timeout=30)

    assert approval_status == 200
    assert update_status in (200, 409)

    # If stock updates first: 120 - 80 = 40.
    # If approval happens first: 100 - 80 = 20,
    # and the stale stock update must fail with 409.
    expected_food = 40 if update_status == 200 else 20

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)
        allocation = db.get(Allocation, allocation_ids[0])

        assert inventory.food == expected_food
        assert inventory.water == 0
        assert inventory.medicine == 0
        assert allocation.status == "APPROVED"
