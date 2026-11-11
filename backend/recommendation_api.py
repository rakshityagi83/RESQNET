from database import SessionLocal
from models import Warehouse, Inventory
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


from recommendation_engine import (
    load_discovered_warehouses,
    shortlist_warehouses,
    rank_candidates_by_driving_time,
    evaluate_warehouse_inventory
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

class SupplyRequirements(BaseModel):
    food: int = Field(default=0, ge=0)
    water: int = Field(default=0, ge=0)
    medicine: int = Field(default=0, ge=0)


class StockAwareRouteRequest(SupplyRequirements):
    incident_lat: float = Field(
        ge=-90,
        le=90,
        allow_inf_nan=False
    )
    incident_lon: float = Field(
        ge=-180,
        le=180,
        allow_inf_nan=False
    )
    limit: int = Field(default=20, ge=1, le=20)


@router.post("/registered/stock-check")
def check_registered_warehouse_stock(item: SupplyRequirements):
    requirements = {
        "food": item.food,
        "water": item.water,
        "medicine": item.medicine
    }

    if not any(requirements.values()):
        raise HTTPException(
            status_code=422,
            detail="Request at least one supply"
        )

    with SessionLocal() as session:
        records = (
            session.query(Warehouse, Inventory)
            .join(
                Inventory,
                Warehouse.id == Inventory.warehouse_id
            )
            .all()
        )

        results = []

        for warehouse, inventory in records:
            warehouse_data = {
                "id": warehouse.id,
                "name": warehouse.name,
                "state": warehouse.state,
                "district": warehouse.district,
                "latitude": warehouse.latitude,
                "longitude": warehouse.longitude,
                "food": inventory.food,
                "water": inventory.water,
                "medicine": inventory.medicine
            }

            evaluated = evaluate_warehouse_inventory(
                warehouse_data,
                requirements
            )

            results.append(evaluated)

    results.sort(
        key=lambda w: w["coverage_percent"],
        reverse=True
    )

    return {
        "status": "operator_recorded_stock_assessment",
        "warehouse_count": len(results),
        "requirements": requirements,
        "warehouses": results,
        "warning": (
            "Inventory is operator-recorded and not independently verified. "
            "Pending allocations do not reserve stock. "
            "No inventory was modified."
        )
    }

@router.post("/registered/ranked")
def rank_registered_warehouses(item: StockAwareRouteRequest):
    """Rank registered warehouses by stock coverage and driving time."""

    requirements = {
        "food": item.food,
        "water": item.water,
        "medicine": item.medicine
    }

    if not any(requirements.values()):
        raise HTTPException(
            status_code=422,
            detail="Request at least one supply"
        )

    # Read registered warehouses and their recorded inventory.
    with SessionLocal() as session:
        records = (
            session.query(Warehouse, Inventory)
            .join(
                Inventory,
                Warehouse.id == Inventory.warehouse_id
            )
            .all()
        )

        warehouses = [
            {
                "id": warehouse.id,
                "name": warehouse.name,
                "state": warehouse.state,
                "district": warehouse.district,
                "latitude": warehouse.latitude,
                "longitude": warehouse.longitude,
                "food": inventory.food,
                "water": inventory.water,
                "medicine": inventory.medicine,
                "inventory_basis": "operator_recorded"
            }
            for warehouse, inventory in records
        ]

    # Shortlist geographically nearby registered warehouses.
    candidates = shortlist_warehouses(
        incident_lat=item.incident_lat,
        incident_lon=item.incident_lon,
        warehouses=warehouses,
        limit=item.limit
    )

    # Evaluate stock coverage and shortages.
    evaluated = [
        evaluate_warehouse_inventory(warehouse, requirements)
        for warehouse in candidates
    ]

    # Calculate road travel times using OSRM.
    try:
        routed = rank_candidates_by_driving_time(
            incident_lat=item.incident_lat,
            incident_lon=item.incident_lon,
            candidates=evaluated
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Road-routing service unavailable"
        ) from exc

    # Rank reachable warehouses first, then by stock coverage
    # and estimated driving time.
    ranked = sorted(
        routed,
        key=lambda warehouse: (
            not warehouse["road_reachable"],
            -warehouse["coverage_percent"],
            warehouse["estimated_drive_minutes"]
            if warehouse["road_reachable"]
            else float("inf")
        )
    )

    return {
        "status": "registered_warehouse_assessment",
        "requirements": requirements,
        "warehouse_count": len(ranked),
        "ranking_basis": "reachability_stock_coverage_driving_time",
        "warehouses": ranked,
        "warning": (
            "Warehouse and inventory data are operator-recorded, "
            "not independently verified. Route estimates do not "
            "confirm road safety. Pending allocations do not "
            "reserve stock. No inventory was modified."
        )
    }
