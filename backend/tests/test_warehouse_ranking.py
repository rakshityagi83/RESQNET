
import json
from io import BytesIO
from urllib.error import URLError

import pytest
import recommendation_engine

from recommendation_engine import (
    shortlist_warehouses,
    rank_candidates_by_driving_time
)


@pytest.fixture
def warehouses():
    return [
        {
            "id": 1,
            "name": "Nearby Warehouse",
            "latitude": 28.41,
            "longitude": 77.32
        },
        {
            "id": 2,
            "name": "Distant Warehouse",
            "latitude": 29.0,
            "longitude": 78.0
        },
        {
            "id": 3,
            "name": "Invalid Warehouse",
            "latitude": "invalid",
            "longitude": 77.30
        }
    ]


def mock_osrm(monkeypatch, response_data):
    def fake_urlopen(request, timeout):
        return BytesIO(
            json.dumps(response_data).encode("utf-8")
        )

    monkeypatch.setattr(
        recommendation_engine,
        "urlopen",
        fake_urlopen
    )


def test_nearest_warehouse_first(warehouses):
    result = shortlist_warehouses(
        incident_lat=28.4089,
        incident_lon=77.3178,
        warehouses=warehouses,
        limit=10
    )

    assert result[0]["name"] == "Nearby Warehouse"
    assert result[1]["name"] == "Distant Warehouse"


def test_invalid_warehouses_are_skipped(warehouses):
    result = shortlist_warehouses(
        28.4089,
        77.3178,
        warehouses,
        limit=10
    )

    assert len(result) == 2
    assert all(
        item["name"] != "Invalid Warehouse"
        for item in result
    )


def test_fastest_driving_route_first(monkeypatch, warehouses):
    mock_osrm(monkeypatch, {
        "code": "Ok",
        "durations": [[1200], [600]],
        "distances": [[20000], [10000]]
    })

    result = rank_candidates_by_driving_time(
        28.4089,
        77.3178,
        warehouses[:2]
    )

    assert result[0]["name"] == "Distant Warehouse"
    assert result[0]["estimated_drive_minutes"] == 10.0
    assert result[0]["road_distance_km"] == 10.0
    assert result[0]["road_reachable"] is True


def test_unreachable_warehouse_ranked_last(monkeypatch, warehouses):
    mock_osrm(monkeypatch, {
        "code": "Ok",
        "durations": [[None], [300]],
        "distances": [[None], [2000]]
    })

    result = rank_candidates_by_driving_time(
        28.4089,
        77.3178,
        warehouses[:2]
    )

    assert result[0]["road_reachable"] is True
    assert result[1]["road_reachable"] is False
    assert result[1]["estimated_drive_minutes"] is None


def test_osrm_failure_handled(monkeypatch, warehouses):
    def failing_urlopen(request, timeout):
        raise URLError("Simulated OSRM outage")

    monkeypatch.setattr(
        recommendation_engine,
        "urlopen",
        failing_urlopen
    )

    with pytest.raises(RuntimeError):
        rank_candidates_by_driving_time(
            28.4089,
            77.3178,
            warehouses[:2]
        )


def test_empty_candidates():
    result = rank_candidates_by_driving_time(
        28.4089,
        77.3178,
        []
    )

    assert result == []
