
import os
import json

import urllib.request
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Warehouse, Inventory, Allocation

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


app = FastAPI(
    title="RESQNET India API",
    description="India-focused Disaster Intelligence and Relief Coordination",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "RESQNET India backend operational", "status": "online"}


@app.get("/health")
def health():
    return {"status": "healthy"}


def fetch_gdacs():
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RESQNET/2.0"}
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))

    incidents = []

    for feature in data.get("features", []):
        p = feature.get("properties", {})
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates", [])

        country = str(p.get("country") or "").strip().lower()

        if country not in {"india", "ind"}:
            continue

        if geometry.get("type") != "Point" or len(coordinates) < 2:
            continue

        incidents.append({
            "id": f"GDACS-{p.get('eventtype')}-{p.get('eventid')}",
            "location": p.get("name") or p.get("country"),
            "country": p.get("country"),
            "type": p.get("eventtype", "Unknown"),
            "severity": p.get("alertlevel", "Unknown"),
            "people": p.get("population"),
            "time": p.get("fromdate"),
            "latitude": coordinates[1],
            "longitude": coordinates[0],
            "source": "GDACS",
            "source_url": (p.get("url") or {}).get("report")
        })

    return incidents


@app.get("/incidents")
def get_incidents():
    try:
        return fetch_gdacs()
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.get("/india-incidents")
def india_incidents():
    try:
        incidents = fetch_gdacs()
        return {
            "source": "GDACS",
            "country": "India",
            "total_events": len(incidents),
            "incidents": incidents
        }
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.get("/priority-incidents")
def priority_incidents():
    try:
        incidents = fetch_gdacs()
        priority = [
            item for item in incidents
            if item["severity"] in {"Red", "Orange"}
        ]

        return {
            "source": "GDACS",
            "country": "India",
            "total_events": len(incidents),
            "priority_events": len(priority),
            "incidents": priority
        }
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


class WarehouseInput(BaseModel):
    name: str = Field(min_length=2)
    state: str
    district: str
    latitude: float | None = None
    longitude: float | None = None
    verified_by: str = Field(min_length=2)


class InventoryInput(BaseModel):
    food: int = Field(ge=0)
    water: int = Field(ge=0)
    medicine: int = Field(ge=0)


class AllocationInput(BaseModel):
    incident_id: str
    warehouse_id: int
    food: int = Field(ge=0)
    water: int = Field(ge=0)
    medicine: int = Field(ge=0)


@app.post("/warehouses")
def register_warehouse(item: WarehouseInput):
    with SessionLocal.begin() as session:
        warehouse = Warehouse(
            name=item.name,
            state=item.state,
            district=item.district,
            latitude=item.latitude,
            longitude=item.longitude,
            verified_by=item.verified_by,
        )

        session.add(warehouse)
        session.flush()

        warehouse_id = warehouse.id

        inventory = Inventory(warehouse_id=warehouse_id)
        session.add(inventory)

    return {
        "message": "Warehouse registered",
        "warehouse_id": warehouse_id,
        "verification": "Operator-entered; not independently verified by RESQNET"
    }
@app.get("/warehouses")
def list_warehouses():
    with SessionLocal() as session:
        results = (
            session.query(Warehouse, Inventory)
            .join(
                Inventory,
                Warehouse.id == Inventory.warehouse_id
            )
            .all()
        )

        return [
            {
                "id": warehouse.id,
                "name": warehouse.name,
                "state": warehouse.state,
                "district": warehouse.district,
                "latitude": warehouse.latitude,
                "longitude": warehouse.longitude,
                "verified_by": warehouse.verified_by,
                "food": inventory.food,
                "water": inventory.water,
                "medicine": inventory.medicine,
            }
            for warehouse, inventory in results
        ]

@app.put("/warehouses/{warehouse_id}/inventory")
def update_inventory(warehouse_id: int, item: InventoryInput):
    with SessionLocal.begin() as session:
        warehouse = session.get(Warehouse, warehouse_id)

        if warehouse is None:
            raise HTTPException(
                status_code=404,
                detail="Warehouse not found"
            )

        inventory = session.get(Inventory, warehouse_id)

        if inventory is None:
            inventory = Inventory(warehouse_id=warehouse_id)
            session.add(inventory)

        inventory.food = item.food
        inventory.water = item.water
        inventory.medicine = item.medicine

    return {
        "message": "Inventory updated",
        "warehouse_id": warehouse_id,
        "inventory": item.model_dump()
    }
@app.post("/allocation/preview")
def allocation_preview(item: AllocationInput):
    try:
        incidents = fetch_gdacs()
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))

    incident = next(
        (x for x in incidents if x["id"] == item.incident_id),
        None
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident not found in current India GDACS feed"
        )

    requested = {
        "food": item.food,
        "water": item.water,
        "medicine": item.medicine
    }

    with SessionLocal.begin() as session:
        warehouse = session.get(Warehouse, item.warehouse_id)

        if warehouse is None:
            raise HTTPException(
                status_code=404,
                detail="Warehouse not found"
            )

        inventory = session.get(Inventory, item.warehouse_id)

        if inventory is None:
            raise HTTPException(
                status_code=404,
                detail="Inventory not found"
            )

        available = {
            "food": inventory.food,
            "water": inventory.water,
            "medicine": inventory.medicine
        }

        allocation = {
            key: min(requested[key], available[key])
            for key in requested
        }

        shortages = {
            key: requested[key] - allocation[key]
            for key in requested
        }

        allocation_id = str(uuid.uuid4())
        warehouse_name = warehouse.name

        record = Allocation(
            id=allocation_id,
            incident_id=item.incident_id,
            warehouse_id=item.warehouse_id,
            requirements=json.dumps({
                "requested": requested,
                "allocation": allocation,
                "shortages": shortages
            }),
            status="PENDING"
        )

        session.add(record)

    return {
        "allocation_id": allocation_id,
        "incident": incident,
        "warehouse": warehouse_name,
        "requested": requested,
        "available": available,
        "proposed_allocation": allocation,
        "shortages": shortages,
        "status": "PENDING HUMAN APPROVAL",
        "note": "Preview only. Inventory has not been deducted."
    }


@app.post("/allocation/{allocation_id}/approve")
def approve_allocation(allocation_id: str):
    with SessionLocal.begin() as session:
        record = (
            session.query(Allocation)
            .filter(Allocation.id == allocation_id)
            .with_for_update()
            .first()
        )

        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Allocation not found"
            )

        if record.status != "PENDING":
            raise HTTPException(
                status_code=409,
                detail="Allocation is not pending approval"
            )

        details = json.loads(record.requirements)
        allocation = details["allocation"]

        inventory = (
            session.query(Inventory)
            .filter(Inventory.warehouse_id == record.warehouse_id)
            .with_for_update()
            .first()
        )

        if inventory is None:
            raise HTTPException(
                status_code=404,
                detail="Inventory not found"
            )

        for key in ("food", "water", "medicine"):
            if getattr(inventory, key) < allocation[key]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient {key} stock. Update the preview."
                )

        inventory.food -= allocation["food"]
        inventory.water -= allocation["water"]
        inventory.medicine -= allocation["medicine"]

        record.status = "APPROVED"

    return {
        "allocation_id": allocation_id,
        "status": "APPROVED",
        "deducted_stock": allocation,
        "message": "Inventory updated after human approval"
    }
@app.get("/analyze-incident/{incident_id}")
def analyze_incident(incident_id: str):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Gemini API key is not configured"
        )

    try:
        incidents = fetch_gdacs()
        incident = next(
            (x for x in incidents if x["id"] == incident_id),
            None
        )

        if not incident:
            raise HTTPException(
                status_code=404,
                detail="Incident not found in current India GDACS feed"
            )

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are RESQNET India's disaster intelligence analyst.

Analyze this live GDACS incident:
{json.dumps(incident, indent=2)}

Provide:
1. Incident overview.
2. Potential risks in the Indian context.
3. Recommended emergency response priorities.
4. Information gaps and uncertainties.

Do not invent casualties, affected population, available stock,
road conditions, or dispatch information.
Distinguish verified data from assumptions.
All recommendations require human verification.
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        return {
            "incident_id": incident_id,
            "source": "GDACS",
            "model": "Gemini 3.6 Flash",
            "analysis": response.text,
            "human_verification_required": True
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
