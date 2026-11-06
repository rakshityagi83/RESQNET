import json
from pathlib import Path
import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["Warehouse Discovery"])

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@router.get("/warehouses/discover")
def discover_warehouses(
    south: float = Query(28.30, ge=-90, le=90),
    west: float = Query(77.25, ge=-180, le=180),
    north: float = Query(28.50, ge=-90, le=90),
    east: float = Query(77.45, ge=-180, le=180),
):
    # Default bounding box covers part of Faridabad.
    if north <= south or east <= west:
        raise HTTPException(
            status_code=400,
            detail="Invalid bounding box"
        )

    # Limit query size to protect the Overpass service.
    if north - south > 0.5 or east - west > 0.5:
        raise HTTPException(
            status_code=400,
            detail="Search area too large"
        )

    bbox = f"({south},{west},{north},{east})"

    query = f"""
    [out:json][timeout:25];
    (
      nwr["building"="warehouse"]{bbox};
      nwr["industrial"="warehouse"]{bbox};
    );
    out center;
    """

    try:
        response = requests.post(
    OVERPASS_URL,
    data={"data": query},
    headers={
        "User-Agent": "RESQNET/2.0 (+https://github.com/rakshityagi83/RESQNET)"
    },
    timeout=(8, 35)
)
        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError):
        raise HTTPException(
            status_code=503,
            detail="OpenStreetMap discovery service unavailable"
        )

    if data.get("remark"):
        raise HTTPException(
            status_code=503,
            detail="OpenStreetMap query could not be completed"
        )

    warehouses = []

    for element in data.get("elements", []):
        coordinates = element.get("center") or element
        latitude = coordinates.get("lat")
        longitude = coordinates.get("lon")

        if latitude is None or longitude is None:
            continue

        tags = element.get("tags", {})
        osm_type = element["type"]
        osm_id = element["id"]

        warehouses.append({
            "id": f"osm-{osm_type}-{osm_id}",
            "name": tags.get("name") or "Unnamed warehouse",
            "latitude": latitude,
            "longitude": longitude,
            "source": "OpenStreetMap",
            "source_url": (
                f"https://www.openstreetmap.org/"
                f"{osm_type}/{osm_id}"
            ),
            "verification_status": "unverified",
            "inventory_status": "unknown"
        })

    return {
        "source": "OpenStreetMap",
        "attribution": "© OpenStreetMap contributors",
        "total": len(warehouses),
        "warehouses": warehouses
    }

SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "faridabad_warehouses.geojson"
)


@router.get("/warehouses/discover/snapshot")
def discover_snapshot():
    try:
        with SNAPSHOT_PATH.open(
            "r", encoding="utf-8-sig"
        ) as file:
            data = json.load(file)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Warehouse snapshot unavailable"
        )

    if data.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=500,
            detail="Invalid GeoJSON format"
        )

    warehouses = []
    seen = set()

    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}

        if geometry.get("type") != "Point":
            continue

        coordinates = geometry.get("coordinates") or []

        if len(coordinates) < 2:
            continue

        longitude, latitude = coordinates[:2]

        if not (
            isinstance(latitude, (int, float))
            and isinstance(longitude, (int, float))
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            continue

        properties = feature.get("properties") or {}
        osm_id = properties.get("@id")

        if not osm_id or osm_id in seen:
            continue

        seen.add(osm_id)

        warehouses.append({
            "id": f"osm-{osm_id.replace('/', '-')}",
            "name": properties.get("name") or "Unnamed warehouse",
            "latitude": latitude,
            "longitude": longitude,
            "source": "OpenStreetMap",
            "source_url": f"https://www.openstreetmap.org/{osm_id}",
            "verification_status": "unverified",
            "inventory_status": "unknown"
        })

    return {
        "source": "OpenStreetMap",
        "dataset": "Faridabad warehouse snapshot",
        "attribution": "© OpenStreetMap contributors",
        "total": len(warehouses),
        "warehouses": warehouses
    }
