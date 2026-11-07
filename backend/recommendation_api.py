
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from recommendation_engine import (
    load_discovered_warehouses,
    shortlist_warehouses,
    rank_candidates_by_driving_time
)


router = APIRouter(
    prefix="/recommendations",
    tags=["Warehouse Recommendations"]
)


class RecommendationRequest(BaseModel):
    incident_lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    incident_lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    limit: int = Field(default=20, ge=1, le=20)


@router.post("/shortlist")
def recommend_warehouse_candidates(item: RecommendationRequest):
    warehouses = load_discovered_warehouses()

    candidates = shortlist_warehouses(
        incident_lat=item.incident_lat,
        incident_lon=item.incident_lon,
        warehouses=warehouses,
        limit=item.limit
    )

    return {
        "status": "candidate_locations_only",
        "total_warehouse_locations": len(warehouses),
        "candidate_count": len(candidates),
        "distance_type": "straight_line",
        "inventory_verified": False,
        "warning": (
            "These are unverified OpenStreetMap warehouse locations. "
            "Inventory and road accessibility are unknown. "
            "Do not treat them as confirmed operational relief facilities."
        ),
        "candidates": candidates
    }

@router.post("/ranked")
def rank_warehouse_candidates(item: RecommendationRequest):
    warehouses = load_discovered_warehouses()

    candidates = shortlist_warehouses(
        incident_lat=item.incident_lat,
        incident_lon=item.incident_lon,
        warehouses=warehouses,
        limit=item.limit
    )

    try:
        ranked = rank_candidates_by_driving_time(
            incident_lat=item.incident_lat,
            incident_lon=item.incident_lon,
            candidates=candidates
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Road-routing service is currently unavailable"
        ) from exc

    return {
        "status": "road_ranked_potential_locations",
        "total_warehouse_locations": len(warehouses),
        "candidate_count": len(ranked),
        "ranking_basis": "estimated_driving_time",
        "route_direction": "warehouse_to_incident",
        "warehouse_verification": "unverified",
        "inventory_status": "unknown",
        "warning": (
            "These are potential warehouse locations only. "
            "Road travel times are estimates. "
            "Inventory, operational availability, and road safety "
            "have not been verified."
        ),
        "candidates": ranked
    }
