
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/routing", tags=["Routing"])


class RouteRequest(BaseModel):
    warehouse_lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    warehouse_lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    incident_lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    incident_lon: float = Field(ge=-180, le=180, allow_inf_nan=False)


@router.post("/calculate")
def calculate_route(item: RouteRequest):

    # OSRM expects longitude,latitude coordinates.
    start = f"{item.warehouse_lon},{item.warehouse_lat}"
    end = f"{item.incident_lon},{item.incident_lat}"

    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{start};{end}"
        "?overview=full&geometries=geojson&steps=false"
    )

    try:
        request = Request(
            url,
            headers={"User-Agent": "RESQNET-Development/1.0"}
        )

        with urlopen(request, timeout=20) as response:
            data = json.load(response)

    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Road routing service is unavailable"
        ) from exc

    if data.get("code") in ("NoRoute", "NoSegment"):
        raise HTTPException(
            status_code=422,
            detail="No drivable route found"
        )

    if data.get("code") != "Ok" or not data.get("routes"):
        raise HTTPException(
            status_code=502,
            detail="Invalid routing provider response"
        )

    route = data["routes"][0]

    return {
        "status": "success",
        "distance_km": round(route["distance"] / 1000, 2),
        "duration_minutes": round(route["duration"] / 60, 1),
        "geometry": route["geometry"],
        "provider": "OSRM demo",
        "warning": (
            "Estimated driving route only. "
            "Traffic, disaster-related road closures, "
            "and route safety are not verified."
        )
    }
