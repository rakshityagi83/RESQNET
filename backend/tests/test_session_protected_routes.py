"""Session authorization tests for actual RESQNET write routes."""

import json

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
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


@pytest.mark.parametrize(
    "role, expected",
    [
        (None, 401),
        ("operator", 403),
        ("admin", 200),
    ],
)
def test_pending_queue_permissions(
    session_protected_app, role, expected
):
    TestSession, warehouse_id, tokens = session_protected_app

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        if role is not None:
            client.cookies.set(
                "resqnet_session",
                tokens[role],
            )

        response = client.get("/allocations/pending")

    assert response.status_code == expected

    if expected == 200:
        data = response.json()

        assert data["count"] == 1
        assert data["has_more"] is False

        record = data["allocations"][0]

        assert record["allocation_id"] == "session-test-allocation"
        assert record["warehouse_id"] == warehouse_id
        assert record["status"] == "PENDING"

        assert record["proposed_allocation"] == {
            "food": 40,
            "water": 60,
            "medicine": 10,
        }

        assert response.headers["Cache-Control"] == "no-store"

    # Viewing the queue must never modify inventory
    # or allocation records.
    assert database_snapshot(TestSession) == before


def test_pending_queue_excludes_approved_allocations(
    session_protected_app,
):
    TestSession, _, tokens = session_protected_app

    with TestSession.begin() as db:
        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        record.status = "APPROVED"

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.get("/allocations/pending")

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["allocations"] == []


def test_pending_queue_pagination(session_protected_app):
    from datetime import datetime, timedelta

    TestSession, warehouse_id, tokens = session_protected_app

    with TestSession.begin() as db:
        original = db.get(
            Allocation,
            "session-test-allocation",
        )

        db.add(Allocation(
            id="second-test-allocation",
            incident_id=original.incident_id,
            warehouse_id=warehouse_id,
            requirements=original.requirements,
            status="PENDING",
            created_at=original.created_at + timedelta(seconds=1),
        ))

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        first = client.get(
            "/allocations/pending?limit=1&offset=0"
        )

        second = client.get(
            "/allocations/pending?limit=1&offset=1"
        )

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["count"] == 1
    assert first.json()["has_more"] is True

    assert second.json()["count"] == 1
    assert second.json()["has_more"] is False

    assert first.json()["allocations"][0]["allocation_id"] == (
        "second-test-allocation"
    )

    assert second.json()["allocations"][0]["allocation_id"] == (
        "session-test-allocation"
    )


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1"],
)
def test_pending_queue_rejects_invalid_pagination(
    session_protected_app, query
):
    _, _, tokens = session_protected_app

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.get(
            "/allocations/pending?" + query
        )

    assert response.status_code == 422


def test_pending_queue_rejects_corrupted_allocation(
    session_protected_app,
):
    TestSession, _, tokens = session_protected_app

    with TestSession.begin() as db:
        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        record.requirements = "invalid-json"

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.get("/allocations/pending")

    assert response.status_code == 500
    assert "invalid-json" not in response.text


@pytest.mark.parametrize(
    "role, expected",
    [
        (None, 401),
        ("operator", 403),
        ("admin", 403),
    ],
)
def test_rejection_requires_authorization_and_csrf(
    session_protected_app, role, expected
):
    TestSession, warehouse_id, tokens = session_protected_app

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        if role is not None:
            client.cookies.set(
                "resqnet_session",
                tokens[role],
            )

        response = client.post(
            "/allocation/session-test-allocation/reject", json={"reason": "  Duplicate test allocation request  "}
        )

    assert response.status_code == expected
    assert database_snapshot(TestSession) == before


def test_reject_allocation_preserves_inventory(
    session_protected_app,
):
    import os
    from models import Inventory
    from csrf_protection import generate_csrf_token
    from session_service import get_authenticated_user

    TestSession, warehouse_id, tokens = session_protected_app

    token = tokens["admin"]

    with TestSession() as db:
        admin = get_authenticated_user(db, token)

        assert admin is not None
        assert admin.role == "admin"

        admin_id = admin.id

        inventory = db.get(Inventory, warehouse_id)

        before = (
            inventory.food,
            inventory.water,
            inventory.medicine,
        )

        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        original_requirements = record.requirements
        original_submitter = record.submitted_by

        assert record.decided_by is None
        assert record.decided_at is None

    # Use genuine session authentication and CSRF protection.
    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", token
        )

        response = client.post(
            "/allocation/session-test-allocation/reject", json={"reason": "  Duplicate test allocation request  "},
            headers={
                "Origin": os.getenv(
                    "FRONTEND_URL",
                    "http://localhost:5173",
                ).rstrip("/"),
                "X-CSRF-Token": generate_csrf_token(token),
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"

    with TestSession() as db:
        inventory = db.get(Inventory, warehouse_id)

        assert (
            inventory.food,
            inventory.water,
            inventory.medicine,
        ) == before

        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        assert record.status == "REJECTED"
        assert record.requirements == original_requirements

        # Verify authenticated administrator attribution.
        assert record.decided_by == admin_id
        assert record.rejection_reason == "Duplicate test allocation request"
        assert record.decided_at is not None

        # Rejection must not overwrite submitter identity.
        assert record.submitted_by == original_submitter



@pytest.mark.parametrize(
    "status",
    ["APPROVED", "REJECTED"],
)
def test_rejection_rejects_finalized_allocations(
    session_protected_app, status
):
    TestSession, _, tokens = session_protected_app

    with TestSession.begin() as db:
        db.get(
            Allocation,
            "session-test-allocation",
        ).status = status

    before = database_snapshot(TestSession)

    previous = main.app.dependency_overrides.copy()

    main.app.dependency_overrides[
        main.require_admin_write
    ] = lambda: None

    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/allocation/session-test-allocation/reject", json={"reason": "  Duplicate test allocation request  "}
            )

        assert response.status_code == 409
        assert database_snapshot(TestSession) == before

    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)


def test_rejection_unknown_allocation(
    session_protected_app,
):
    TestSession, _, tokens = session_protected_app

    before = database_snapshot(TestSession)

    previous = main.app.dependency_overrides.copy()

    main.app.dependency_overrides[
        main.require_admin_write
    ] = lambda: None

    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/allocation/nonexistent-allocation/reject", json={"reason": "  Duplicate test allocation request  "}
            )

        assert response.status_code == 404
        assert database_snapshot(TestSession) == before

    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)


@pytest.mark.parametrize(
    "role, expected",
    [
        (None, 401),
        ("operator", 403),
        ("admin", 200),
    ],
)
def test_history_permissions(
    session_protected_app, role, expected
):
    TestSession, _, tokens = session_protected_app

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        if role is not None:
            client.cookies.set(
                "resqnet_session", tokens[role]
            )

        response = client.get("/allocations/history")

        assert response.status_code == expected

        if expected == 200:
            assert response.json()["count"] == 1
            assert response.headers["Cache-Control"] == "no-store"
        else:
            assert "allocations" not in response.json()

    assert database_snapshot(TestSession) == before


def test_history_status_filters(session_protected_app):
    TestSession, warehouse_id, tokens = session_protected_app

    with TestSession.begin() as db:
        original = db.get(
            Allocation, "session-test-allocation"
        )

        for status in ("APPROVED", "REJECTED"):
            db.add(Allocation(
                id="history-" + status.lower(),
                incident_id=original.incident_id,
                warehouse_id=warehouse_id,
                requirements=original.requirements,
                status=status,
            ))

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", tokens["admin"]
        )

        response = client.get("/allocations/history")

        assert response.status_code == 200
        assert response.json()["count"] == 3

        for status in (
            "PENDING", "APPROVED", "REJECTED"
        ):
            response = client.get(
                "/allocations/history",
                params={"status": status},
            )

            assert response.status_code == 200

            data = response.json()

            assert data["count"] == 1

            assert (
                data["allocations"][0]["status"]
                == status
            )

        pending = client.get("/allocations/pending")

        assert pending.status_code == 200
        assert pending.json()["count"] == 1
        assert (
            pending.json()["allocations"][0]["status"]
            == "PENDING"
        )

    assert database_snapshot(TestSession) == before


@pytest.mark.parametrize(
    "field",
    ["allocation_id", "incident_id", "warehouse"],
)
def test_history_search(
    session_protected_app, field
):
    from models import Warehouse

    TestSession, warehouse_id, tokens = session_protected_app

    with TestSession() as db:
        record = db.get(
            Allocation, "session-test-allocation"
        )

        warehouse = db.get(Warehouse, warehouse_id)

        values = {
            "allocation_id": record.id,
            "incident_id": record.incident_id,
            "warehouse": warehouse.name,
        }

        search = values[field].swapcase()

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", tokens["admin"]
        )

        response = client.get(
            "/allocations/history",
            params={"q": search},
        )

        assert response.status_code == 200
        assert response.json()["count"] == 1

        assert (
            response.json()["allocations"][0]["allocation_id"]
            == "session-test-allocation"
        )


def test_history_literal_wildcard_search(
    session_protected_app,
):
    _, _, tokens = session_protected_app

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", tokens["admin"]
        )

        response = client.get(
            "/allocations/history",
            params={"q": "%"},
        )

        assert response.status_code == 200
        assert response.json()["count"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"status": "UNKNOWN"},
        {"limit": 0},
        {"offset": -1},
        {"q": "x" * 151},
    ],
)
def test_history_invalid_filters(
    session_protected_app, params
):
    _, _, tokens = session_protected_app

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", tokens["admin"]
        )

        response = client.get(
            "/allocations/history",
            params=params,
        )

        assert response.status_code == 422


def test_history_pagination(session_protected_app):
    TestSession, _, tokens = session_protected_app

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", tokens["admin"]
        )

        response = client.get(
            "/allocations/history",
            params={"limit": 1, "offset": 1},
        )

        assert response.status_code == 200
        assert response.json()["count"] == 0
        assert response.json()["has_more"] is False

    assert database_snapshot(TestSession) == before


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"reason": "    "},
        {"reason": "Duplicate"},
        {"reason": "x" * 501},
        {"reason": 1234567890},
        {"reason": "Invalid\x00allocation reason"},
        {
            "reason": "Duplicate allocation request",
            "decided_by": 999,
        },
    ],
)
def test_rejection_invalid_reason(
    session_protected_app, payload
):
    import os
    from models import Inventory
    from csrf_protection import generate_csrf_token

    TestSession, warehouse_id, tokens = session_protected_app

    def read_state():
        with TestSession() as db:
            record = db.get(
                Allocation,
                "session-test-allocation",
            )

            inventory = db.get(Inventory, warehouse_id)

            return (
                record.status,
                record.requirements,
                record.submitted_by,
                record.decided_by,
                record.decided_at,
                record.rejection_reason,
                inventory.food,
                inventory.water,
                inventory.medicine,
            )

    before = read_state()

    token = tokens["admin"]

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session", token
        )

        response = client.post(
            "/allocation/session-test-allocation/reject",
            headers={
                "Origin": os.getenv(
                    "FRONTEND_URL",
                    "http://localhost:5173",
                ).rstrip("/"),
                "X-CSRF-Token": generate_csrf_token(token),
            },
            json=payload,
        )

    assert response.status_code == 422
    assert read_state() == before


@pytest.mark.parametrize(
    "status",
    ["PENDING", "APPROVED", "REJECTED"],
)
def test_history_audit_fields(
    session_protected_app, status
):
    from datetime import datetime, timezone
    from session_service import get_authenticated_user

    TestSession, _, tokens = session_protected_app

    decided_at = datetime.now(timezone.utc)

    with TestSession.begin() as db:
        operator = get_authenticated_user(
            db, tokens["operator"]
        )

        admin = get_authenticated_user(
            db, tokens["admin"]
        )

        assert operator is not None
        assert admin is not None
        assert operator.id != admin.id

        operator_id = operator.id
        operator_username = operator.username

        admin_id = admin.id
        admin_username = admin.username

        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        record.status = status
        record.submitted_by = operator_id

        if status != "PENDING":
            record.decided_by = admin_id
            record.decided_at = decided_at

        if status == "REJECTED":
            record.rejection_reason = (
                "Duplicate allocation request"
            )

    before = database_snapshot(TestSession)

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.get(
            "/allocations/history",
            params={"status": status},
        )

        assert response.status_code == 200

        data = response.json()["allocations"][0]

        assert data["submitted_by"] == operator_id

        assert (
            data["submitted_by_username"]
            == operator_username
        )

        if status == "PENDING":
            assert data["decided_by"] is None
            assert data["decided_by_username"] is None
            assert data["decided_at"] is None

            pending = client.get(
                "/allocations/pending"
            )

            assert pending.status_code == 200
            assert pending.json()["allocations"][0] == data

        else:
            assert data["decided_by"] == admin_id

            assert (
                data["decided_by_username"]
                == admin_username
            )

            timestamp = datetime.fromisoformat(
                data["decided_at"]
            )

            assert timestamp == decided_at
            assert timestamp.utcoffset().total_seconds() == 0

        assert data["rejection_reason"] == (
            "Duplicate allocation request"
            if status == "REJECTED"
            else None
        )

        for forbidden in (
            "password",
            "password_hash",
            "token_hash",
            "csrf_token",
            "session_token",
        ):
            assert forbidden not in data

    assert database_snapshot(TestSession) == before


def test_history_preserves_unknown_legacy_audit_fields(
    session_protected_app,
):
    TestSession, _, tokens = session_protected_app

    with TestSession.begin() as db:
        record = db.get(
            Allocation,
            "session-test-allocation",
        )

        record.status = "REJECTED"

    with TestClient(main.app) as client:
        client.cookies.set(
            "resqnet_session",
            tokens["admin"],
        )

        response = client.get("/allocations/history")

    assert response.status_code == 200

    data = response.json()["allocations"][0]

    for field in (
        "submitted_by",
        "submitted_by_username",
        "decided_by",
        "decided_by_username",
        "decided_at",
        "rejection_reason",
    ):
        assert field in data
        assert data[field] is None
