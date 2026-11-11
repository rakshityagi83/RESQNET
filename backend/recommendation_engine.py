
from math import radians, sin, cos, asin, sqrt, isfinite
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
def valid_coordinates(lat, lon):
    return (
        isfinite(lat)
        and isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate straight-line distance between two GPS locations."""
    earth_radius = 6371.0

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))
    return 2 * earth_radius * asin(sqrt(a))


def shortlist_warehouses(
    incident_lat,
    incident_lon,
    warehouses,
    limit=20
):
    """Return nearby warehouse candidates sorted by geographic distance."""

    incident_lat = float(incident_lat)
    incident_lon = float(incident_lon)

    if not valid_coordinates(incident_lat, incident_lon):
        raise ValueError("Invalid incident coordinates")

    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")

    candidates = []

    for warehouse in warehouses:
        try:
            lat = float(warehouse["latitude"])
            lon = float(warehouse["longitude"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

        if not valid_coordinates(lat, lon):
            continue

        distance = haversine_km(
            incident_lat,
            incident_lon,
            lat,
            lon
        )

        candidates.append({
            **warehouse,
            "straight_line_km": round(distance, 2)
        })

    candidates.sort(key=lambda item: item["straight_line_km"])

    return candidates[:limit]

def load_discovered_warehouses():
    """Load warehouse candidates from our local OSM GeoJSON snapshot."""

    data_file = (
        Path(__file__).resolve().parent
        / "data"
        / "faridabad_warehouses.geojson"
    )

    with data_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    warehouses = []

    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        coordinates = geometry.get("coordinates")

        if (
            geometry.get("type") != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            continue

        longitude, latitude = coordinates[:2]

        warehouses.append({
            "id": feature.get("id") or properties.get("@id"),
            "name": properties.get("name") or "Unnamed warehouse",
            "latitude": latitude,
            "longitude": longitude,
            "source": "OpenStreetMap",
            "verification_status": "unverified",
            "inventory_status": "unknown"
        })

    return warehouses


def rank_candidates_by_driving_time(
    incident_lat,
    incident_lon,
    candidates
):


    """Rank warehouse locations using OSRM driving estimates."""

    if not candidates:
        return []

    if len(candidates) > 20:
        raise ValueError("Maximum 20 candidates per request")

    incident_lat = float(incident_lat)
    incident_lon = float(incident_lon)

    if not valid_coordinates(incident_lat, incident_lon):
        raise ValueError("Invalid incident coordinates")

    # OSRM expects longitude,latitude.
    coordinates = []

    for warehouse in candidates:
        lat = float(warehouse["latitude"])
        lon = float(warehouse["longitude"])

        if not valid_coordinates(lat, lon):
            raise ValueError("Invalid warehouse coordinates")

        coordinates.append(f"{lon},{lat}")

    coordinates.append(f"{incident_lon},{incident_lat}")

    coordinate_string = ";".join(coordinates)
    source_indices = ";".join(str(i) for i in range(len(candidates)))
    destination_index = len(candidates)

    url = (
        "https://router.project-osrm.org/table/v1/driving/"
        f"{coordinate_string}"
        f"?sources={source_indices}"
        f"&destinations={destination_index}"
        "&annotations=duration,distance"
    )

    try:
        request = Request(
            url,
            headers={"User-Agent": "RESQNET-Development/1.0"}
        )

        with urlopen(request, timeout=20) as response:
            data = json.load(response)

    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("OSRM routing service unavailable") from exc

    if data.get("code") != "Ok":
        raise RuntimeError("OSRM could not calculate the route matrix")

    durations = data["durations"]
    distances = data["distances"]

    ranked = []

    for i, warehouse in enumerate(candidates):
        duration = durations[i][0]
        distance = distances[i][0]

        reachable = duration is not None and distance is not None

        ranked.append({
            **warehouse,
            "road_reachable": reachable,
            "road_distance_km": (
                round(distance / 1000, 2) if reachable else None
            ),
            "estimated_drive_minutes": (
                round(duration / 60, 1) if reachable else None
            )
        })

    ranked.sort(
        key=lambda item: (
            not item["road_reachable"],
            item["estimated_drive_minutes"]
            if item["road_reachable"] else float("inf")
        )
    )

    return ranked



def evaluate_warehouse_inventory(warehouse, requirements):
    """
    Evaluate recorded warehouse stock against requested supplies.
    Does not reserve or modify inventory.
    """

    supply_types = ("food", "water", "medicine")

    requested = {
        key: int(requirements.get(key, 0))
        for key in supply_types
    }

    if any(value < 0 for value in requested.values()):
        raise ValueError("Supply requirements cannot be negative")

    if not any(requested.values()):
        raise ValueError("At least one supply must be requested")

    available = {
        key: max(0, int(warehouse.get(key, 0) or 0))
        for key in supply_types
    }

    shortages = {
        key: max(0, requested[key] - available[key])
        for key in supply_types
    }

    coverage = {
        key: min(1.0, available[key] / requested[key])
        for key in supply_types
        if requested[key] > 0
    }

    coverage_percent = round(
        100 * sum(coverage.values()) / len(coverage),
        1
    )

    if all(value == 0 for value in shortages.values()):
        stock_status = "full"
    elif any(
        available[key] > 0 and requested[key] > 0
        for key in supply_types
    ):
        stock_status = "partial"
    else:
        stock_status = "insufficient"

    return {
        **warehouse,
        "requested_supplies": requested,
        "recorded_available": available,
        "shortages": shortages,
        "coverage_percent": coverage_percent,
        "stock_status": stock_status,
        "inventory_basis": "operator_recorded"
    }