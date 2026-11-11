from types import SimpleNamespace
from unittest.mock import MagicMock
import recommendation_api
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from recommendation_api import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as test_client:
        yield test_client


def test_zero_supply_requirements_rejected(client):
    response = client.post(
        "/recommendations/registered/ranked",
        json={
            "incident_lat": 28.4089,
            "incident_lon": 77.3178,
            "food": 0,
            "water": 0,
            "medicine": 0
        }
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Request at least one supply"


def test_negative_supply_requirements_rejected(client):
    response = client.post(
        "/recommendations/registered/ranked",
        json={
            "incident_lat": 28.4089,
            "incident_lon": 77.3178,
            "food": -100,
            "water": 500,
            "medicine": 100
        }
    )

    assert response.status_code == 422


def test_invalid_incident_coordinates_rejected(client):
    response = client.post(
        "/recommendations/registered/ranked",
        json={
            "incident_lat": 95,
            "incident_lon": 77.3178,
            "food": 500,
            "water": 1000,
            "medicine": 100
        }
    )

    assert response.status_code == 422

@pytest.fixture
def fake_registered_db(monkeypatch):
    records = [
        (
            SimpleNamespace(
                id=1,
                name="Full Stock Warehouse",
                state="Haryana",
                district="Faridabad",
                latitude=28.41,
                longitude=77.32
            ),
            SimpleNamespace(
                food=1300,
                water=2600,
                medicine=450
            )
        ),
        (
            SimpleNamespace(
                id=2,
                name="Partial Stock Warehouse",
                state="Haryana",
                district="Faridabad",
                latitude=28.42,
                longitude=77.33
            ),
            SimpleNamespace(
                food=100,
                water=100,
                medicine=50
            )
        )
    ]

    session = MagicMock()
    session.__enter__.return_value = session
    session.query.return_value.join.return_value.all.return_value = records

    monkeypatch.setattr(
        recommendation_api,
        "SessionLocal",
        lambda: session
    )

    return session


def test_registered_ranking_prioritizes_stock_coverage(
    client, monkeypatch, fake_registered_db
):
    def fake_routing(incident_lat, incident_lon, candidates):
        results = []

        for warehouse in candidates:
            is_full = warehouse["id"] == 1

            results.append({
                **warehouse,
                "road_reachable": True,
                "road_distance_km": 50.0 if is_full else 5.0,
                "estimated_drive_minutes": 45.0 if is_full else 8.0
            })

        return results

    monkeypatch.setattr(
        recommendation_api,
        "rank_candidates_by_driving_time",
        fake_routing
    )

    response = client.post(
        "/recommendations/registered/ranked",
        json={
            "incident_lat": 28.4089,
            "incident_lon": 77.3178,
            "food": 500,
            "water": 1000,
            "medicine": 100
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["warehouse_count"] == 2
    assert data["status"] == "registered_warehouse_assessment"

    full, partial = data["warehouses"]

    # Full coverage ranks first, even with a longer drive.
    assert full["id"] == 1
    assert full["stock_status"] == "full"
    assert full["coverage_percent"] == 100.0
    assert full["estimated_drive_minutes"] == 45.0

    assert partial["id"] == 2
    assert partial["stock_status"] == "partial"
    assert partial["shortages"] == {
        "food": 400,
        "water": 900,
        "medicine": 50
    }

    # This endpoint must not modify inventory.
    fake_registered_db.add.assert_not_called()
    fake_registered_db.commit.assert_not_called()


def test_registered_ranking_handles_osrm_outage(
    client, monkeypatch, fake_registered_db
):
    def failing_routing(incident_lat, incident_lon, candidates):
        raise RuntimeError("Simulated OSRM outage")

    monkeypatch.setattr(
        recommendation_api,
        "rank_candidates_by_driving_time",
        failing_routing
    )

    response = client.post(
        "/recommendations/registered/ranked",
        json={
            "incident_lat": 28.4089,
            "incident_lon": 77.3178,
            "food": 500,
            "water": 1000,
            "medicine": 100
        }
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Road-routing service unavailable"
    )
