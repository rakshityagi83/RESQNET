
import os
import json
import sqlite3
import urllib.request
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = os.path.join(os.path.dirname(__file__), "resqnet.db")

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


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db():
    with db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS warehouses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                state TEXT NOT NULL,
                district TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                verified_by TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                warehouse_id INTEGER PRIMARY KEY,
                food INTEGER NOT NULL DEFAULT 0,
                water INTEGER NOT NULL DEFAULT 0,
                medicine INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS allocations (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                warehouse_id INTEGER NOT NULL,
                requirements TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


initialize_db()


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
    with db() as connection:
        cursor = connection.execute("""
            INSERT INTO warehouses
            (name, state, district, latitude, longitude, verified_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            item.name, item.state, item.district,
            item.latitude, item.longitude, item.verified_by
        ))

        warehouse_id = cursor.lastrowid

        connection.execute("""
            INSERT INTO inventory (warehouse_id)
            VALUES (?)
        """, (warehouse_id,))

    return {
        "message": "Warehouse registered",
        "warehouse_id": warehouse_id,
        "verification": "Operator-entered; not independently verified by RESQNET"
    }


@app.get("/warehouses")
def list_warehouses():
    with db() as connection:
        rows = connection.execute("""
            SELECT w.*, i.food, i.water, i.medicine
            FROM warehouses w
            JOIN inventory i ON w.id = i.warehouse_id
        """).fetchall()

    return [dict(row) for row in rows]


@app.put("/warehouses/{warehouse_id}/inventory")
def update_inventory(warehouse_id: int, item: InventoryInput):
    with db() as connection:
        warehouse = connection.execute(
            "SELECT id FROM warehouses WHERE id = ?",
            (warehouse_id,)
        ).fetchone()

        if not warehouse:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        connection.execute("""
            UPDATE inventory
            SET food = ?, water = ?, medicine = ?
            WHERE warehouse_id = ?
        """, (item.food, item.water, item.medicine, warehouse_id))

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

    with db() as connection:
        row = connection.execute("""
            SELECT w.name, i.food, i.water, i.medicine
            FROM warehouses w
            JOIN inventory i ON w.id = i.warehouse_id
            WHERE w.id = ?
        """, (item.warehouse_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    requested = {
        "food": item.food,
        "water": item.water,
        "medicine": item.medicine
    }

    available = {
        "food": row["food"],
        "water": row["water"],
        "medicine": row["medicine"]
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

    with db() as connection:
        connection.execute("""
            INSERT INTO allocations
            (id, incident_id, warehouse_id, requirements, status)
            VALUES (?, ?, ?, ?, 'PENDING')
        """, (
            allocation_id,
            item.incident_id,
            item.warehouse_id,
            json.dumps({
                "requested": requested,
                "allocation": allocation,
                "shortages": shortages
            })
        ))

    return {
        "allocation_id": allocation_id,
        "incident": incident,
        "warehouse": row["name"],
        "requested": requested,
        "available": available,
        "proposed_allocation": allocation,
        "shortages": shortages,
        "status": "PENDING HUMAN APPROVAL",
        "note": "Preview only. Inventory has not been deducted."
    }


@app.post("/allocation/{allocation_id}/approve")
def approve_allocation(allocation_id: str):
    with db() as connection:
        connection.execute("BEGIN IMMEDIATE")

        record = connection.execute("""
            SELECT * FROM allocations
            WHERE id = ?
        """, (allocation_id,)).fetchone()

        if not record:
            raise HTTPException(status_code=404, detail="Allocation not found")

        if record["status"] != "PENDING":
            raise HTTPException(
                status_code=409,
                detail="Allocation is not pending approval"
            )

        details = json.loads(record["requirements"])
        allocation = details["allocation"]
        warehouse_id = record["warehouse_id"]

        stock = connection.execute("""
            SELECT food, water, medicine
            FROM inventory WHERE warehouse_id = ?
        """, (warehouse_id,)).fetchone()

        if not stock:
            raise HTTPException(status_code=404, detail="Inventory not found")

        for key in allocation:
            if stock[key] < allocation[key]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient {key} stock. Update the preview."
                )

        connection.execute("""
            UPDATE inventory
            SET food = food - ?,
                water = water - ?,
                medicine = medicine - ?
            WHERE warehouse_id = ?
        """, (
            allocation["food"],
            allocation["water"],
            allocation["medicine"],
            warehouse_id
        ))

        connection.execute("""
            UPDATE allocations
            SET status = 'APPROVED'
            WHERE id = ?
        """, (allocation_id,))

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
