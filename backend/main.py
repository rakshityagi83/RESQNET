from models import User as AuditUser
from session_service import as_utc as normalize_audit_time
from typing import Annotated
from pydantic import ConfigDict, StringConstraints, field_validator
from datetime import datetime as audit_datetime, timezone as audit_timezone
from fastapi import Response
from typing import Literal
from sqlalchemy import or_, update
from session_authorization import (
    SessionPrincipal,
    require_session_admin,
)
from datetime import date, timedelta, datetime
import requests
import os
import json
from warehouse_discovery import router as warehouse_discovery_router
from recommendation_api import router as recommendation_router
from routing import router as routing_router
import urllib.request
import uuid
import threading
import time
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends
from browser_security import configure_browser_cors
from pydantic import BaseModel, Field
from google import genai
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Warehouse, Inventory, Allocation
from session_authorization import (
    require_admin_write,
    require_operator_write,
)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


app = FastAPI(
    title="RESQNET India API",
    description="India-focused Disaster Intelligence and Relief Coordination",
    version="2.0.0"
)
app.include_router(warehouse_discovery_router)
app.include_router(recommendation_router)
app.include_router(routing_router)
configure_browser_cors(app)

@app.get("/")
def home():
    return {"message": "RESQNET India backend operational", "status": "online"}


@app.get("/health")
def health():
    return {"status": "healthy"}


_GDACS_CACHE = {
    "incidents": None,
    "fresh_until": 0.0,
    "retry_after": 0.0
}

_GDACS_LOCK = threading.Lock()


def fetch_gdacs():
    with _GDACS_LOCK:
        now = time.monotonic()

        # Reuse only recently fetched live data.
        if (
            _GDACS_CACHE["incidents"] is not None
            and now < _GDACS_CACHE["fresh_until"]
        ):
            return _GDACS_CACHE["incidents"]

        # Avoid repeatedly contacting a failing service.
        if now < _GDACS_CACHE["retry_after"]:
            raise RuntimeError(
                "GDACS live feed temporarily unavailable. Retry shortly."
            )

        url = (
            "https://www.gdacs.org/gdacsapi/api/"
            "events/geteventlist/EVENTS4APP"
        )

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "RESQNET/2.0"}
        )

        try:
            with urllib.request.urlopen(
                request, timeout=12
            ) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )

        except (OSError, ValueError) as error:
            _GDACS_CACHE["retry_after"] = time.monotonic() + 60

            raise RuntimeError(
                "GDACS live feed temporarily unavailable."
            ) from error

        incidents = []

        for feature in data.get("features", []):
            p = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []

            country = str(
                p.get("country") or ""
            ).strip().lower()

            if country not in {"india", "ind"}:
                continue

            if (
                geometry.get("type") != "Point"
                or len(coordinates) < 2
            ):
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

        _GDACS_CACHE["incidents"] = incidents
        _GDACS_CACHE["fresh_until"] = time.monotonic() + 120
        _GDACS_CACHE["retry_after"] = 0.0

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

@app.get("/historical-incidents")
def historical_incidents(
    days: int = Query(60, ge=1, le=365)
):
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    url = (
        "https://www.gdacs.org/gdacsapi/api/"
        "events/geteventlist/SEARCH"
    )

    try:
        response = requests.get(
            url,
            params={
                "country": "India",
                "fromdate": start_date.isoformat(),
                "todate": end_date.isoformat()
            },
            headers={"User-Agent": "RESQNET/2.0"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Historical GDACS feed unavailable"
        )

    incidents = []

    for feature in data.get("features", []):
        p = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []

        if geometry.get("type") != "Point" or len(coords) < 2:
            continue

        country = str(p.get("country") or "").lower()
        if "india" not in country:
            continue

        # Include only events that started within the requested period.
        raw_date = p.get("fromdate")

        try:
            event_date = datetime.fromisoformat(
                str(raw_date).replace("Z", "+00:00")
            ).date()
        except (ValueError, TypeError):
            continue

        if not (start_date <= event_date <= end_date):
            continue


        report = p.get("url") or {}
        report_url = (
            report.get("report")
            if isinstance(report, dict)
            else None
        )

        incidents.append({
            "id": f"GDACS-{p.get('eventtype')}-{p.get('eventid')}",
            "location": p.get("name") or "India",
            "country": p.get("country"),
            "type": p.get("eventtype"),
            "severity": p.get("alertlevel", "Unknown"),
            "people": p.get("population"),
            "time": p.get("fromdate"),
            "latitude": coords[1],
            "longitude": coords[0],
            "source": "GDACS",
            "source_url": report_url,
            "historical": True
        })

    return {
        "source": "GDACS",
        "mode": "historical",
        "country": "India",
        "from_date": start_date.isoformat(),
        "to_date": end_date.isoformat(),
        "total_events": len(incidents),
        "incidents": incidents
    }



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
    food: int = Field(default=0, ge=0, le=2147483647, strict=True)
    water: int = Field(default=0, ge=0, le=2147483647, strict=True)
    medicine: int = Field(default=0, ge=0, le=2147483647, strict=True)


class InventoryQuantities(BaseModel):
    food: int = Field(ge=0, le=2147483647, strict=True)
    water: int = Field(ge=0, le=2147483647, strict=True)
    medicine: int = Field(ge=0, le=2147483647, strict=True)


class InventoryInput(InventoryQuantities):
    expected: InventoryQuantities


class AllocationInput(BaseModel):
    incident_id: str
    warehouse_id: int
    food: int = Field(ge=0)
    water: int = Field(ge=0)
    medicine: int = Field(ge=0)


@app.post("/warehouses", dependencies=[Depends(require_admin_write)])
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

        inventory = Inventory(
            warehouse_id=warehouse_id,
            food=item.food,
            water=item.water,
            medicine=item.medicine,
        )
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

@app.put(
    "/warehouses/{warehouse_id}/inventory",
    dependencies=[Depends(require_admin_write)]
)
def update_inventory(warehouse_id: int, item: InventoryInput):
    with SessionLocal.begin() as session:
        result = session.execute(
            update(Inventory)
            .where(
                Inventory.warehouse_id == warehouse_id,
                Inventory.food == item.expected.food,
                Inventory.water == item.expected.water,
                Inventory.medicine == item.expected.medicine,
            )
            .values(
                food=item.food,
                water=item.water,
                medicine=item.medicine,
            )
        )

        if result.rowcount != 1:
            if session.get(Warehouse, warehouse_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail="Warehouse not found",
                )

            if session.get(Inventory, warehouse_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail="Warehouse inventory not initialized",
                )

            raise HTTPException(
                status_code=409,
                detail=(
                    "Inventory has changed since it was loaded. "
                    "Refresh and retry."
                ),
            )

    return {
        "message": "Inventory updated",
        "warehouse_id": warehouse_id,
        "inventory": item.model_dump(exclude={"expected"})
    }
@app.post(
    "/allocation/preview",
    dependencies=[Depends(require_operator_write)]
)
def allocation_preview(
    item: AllocationInput,
    principal: SessionPrincipal = Depends(require_operator_write),
):
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
            status="PENDING",
            submitted_by=principal.user_id
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


@app.post(
    "/allocation/{allocation_id}/approve",
    dependencies=[Depends(require_admin_write)]
)
def approve_allocation(
    allocation_id: str,
    principal: SessionPrincipal = Depends(require_admin_write),
):
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
        record.decided_by = principal.user_id
        record.decided_at = audit_datetime.now(audit_timezone.utc)

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

        is_historical = False

        # Search historical GDACS records if not in the live feed.
        if incident is None:
            history = historical_incidents(days=60)

            incident = next(
                (
                    x for x in history["incidents"]
                    if x["id"] == incident_id
                ),
                None
            )

            is_historical = incident is not None



        if not incident:
            raise HTTPException(
                status_code=404,
                detail="Incident not found in live or historical GDACS feeds"
            )

        client = genai.Client(api_key=GEMINI_API_KEY)


        prompt = f"""
You are RESQNET India's disaster intelligence analyst.

Analyze this {"historical" if is_historical else "current"} GDACS incident:
If this is a historical incident, provide a retrospective
analysis only. Do not describe it as an active emergency.
Do not imply that response teams or resources were deployed.
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
            "human_verification_required": True,
            "mode": "historical" if is_historical else "live"
        }


    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.get("/allocations/pending")
def list_pending_allocations(
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: SessionPrincipal = Depends(require_session_admin),
):
    """Retrieve pending allocations for administrative review."""

    return read_allocation_records(
        response,
        limit,
        offset,
        statuses=("PENDING",),
    )


@app.get("/allocations/history")
def list_allocation_history(
    response: Response,
    status: Literal[
        "ALL", "PENDING", "APPROVED", "REJECTED"
    ] = "ALL",
    q: str = Query(default="", max_length=150),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: SessionPrincipal = Depends(require_session_admin),
):
    """Retrieve persistent allocation history."""

    statuses = (
        ("PENDING", "APPROVED", "REJECTED")
        if status == "ALL"
        else (status,)
    )

    return read_allocation_records(
        response,
        limit,
        offset,
        statuses=statuses,
        search=q.strip(),
    )


def read_allocation_records(
    response,
    limit,
    offset,
    *,
    statuses,
    search="",
):
    """Shared read-only allocation retrieval."""

    response.headers["Cache-Control"] = "no-store"

    with SessionLocal() as session:
        query = (
            session.query(
                Allocation,
                Warehouse.name,
            )
            .outerjoin(
                Warehouse,
                Warehouse.id == Allocation.warehouse_id,
            )
            .filter(Allocation.status.in_(statuses))
        )

        if search:
            # Treat SQL wildcard characters as literal text.
            escaped = (
                search.replace("/", "//")
                .replace("%", "/%")
                .replace("_", "/_")
            )

            pattern = "%" + escaped + "%"

            query = query.filter(
                or_(
                    Allocation.id.ilike(pattern, escape="/"),
                    Allocation.incident_id.ilike(
                        pattern, escape="/"
                    ),
                    Warehouse.name.ilike(
                        pattern, escape="/"
                    ),
                )
            )

        rows = (
            query.order_by(
                Allocation.created_at.desc(),
                Allocation.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
            .all()
        )

        has_more = len(rows) > limit

        # Resolve account identities in one batched query.
        actor_ids = {
            actor_id
            for record, _ in rows[:limit]
            for actor_id in (
                record.submitted_by,
                record.decided_by,
            )
            if actor_id is not None
        }

        usernames = {}

        if actor_ids:
            usernames = dict(
                session.query(
                    AuditUser.id,
                    AuditUser.username,
                )
                .filter(AuditUser.id.in_(actor_ids))
                .all()
            )

        results = []

        for record, warehouse_name in rows[:limit]:
            try:
                requirements = json.loads(record.requirements)

                for section in (
                    "requested",
                    "allocation",
                    "shortages",
                ):
                    quantities = requirements[section]

                    if not isinstance(quantities, dict):
                        raise ValueError("Invalid quantities")

                    for resource in ("food", "water", "medicine"):
                        value = quantities[resource]

                        if type(value) is not int or value < 0:
                            raise ValueError("Invalid quantity")

                for resource in ("food", "water", "medicine"):
                    if (
                        requirements["requested"][resource]
                        != requirements["allocation"][resource]
                        + requirements["shortages"][resource]
                    ):
                        raise ValueError("Inconsistent allocation")

            except (ValueError, TypeError, KeyError):
                raise HTTPException(
                    status_code=500,
                    detail="Stored allocation could not be read safely",
                ) from None

            results.append({
                "allocation_id": record.id,
                "incident_id": record.incident_id,
                "warehouse_id": record.warehouse_id,
                "warehouse": warehouse_name,
                "status": record.status,
                "created_at": record.created_at,
                "submitted_by": record.submitted_by,
                "submitted_by_username": usernames.get(
                    record.submitted_by
                ),
                "decided_by": record.decided_by,
                "decided_by_username": usernames.get(
                    record.decided_by
                ),
                "decided_at": (
                    normalize_audit_time(record.decided_at)
                    if record.decided_at is not None
                    else None
                ),
                "rejection_reason": record.rejection_reason,
                "requested": {
                    key: requirements["requested"][key]
                    for key in ("food", "water", "medicine")
                },
                "proposed_allocation": {
                    key: requirements["allocation"][key]
                    for key in ("food", "water", "medicine")
                },
                "shortages": {
                    key: requirements["shortages"][key]
                    for key in ("food", "water", "medicine")
                },
            })

    return {
        "allocations": results,
        "count": len(results),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


class AllocationRejectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=10,
            max_length=500,
            strict=True,
        ),
    ]

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value):
        if any(
            ord(character) < 32 or
            127 <= ord(character) <= 159
            for character in value
        ):
            raise ValueError(
                "Rejection reason contains control characters"
            )

        return value


@app.post(
    "/allocation/{allocation_id}/reject",
    dependencies=[Depends(require_admin_write)],
)
def reject_allocation(
    allocation_id: str,
    payload: AllocationRejectionInput,
    principal: SessionPrincipal = Depends(require_admin_write),
):
    """Reject a pending allocation without deducting inventory."""

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
                detail="Allocation not found",
            )

        if record.status != "PENDING":
            raise HTTPException(
                status_code=409,
                detail="Allocation is not pending approval",
            )

        record.status = "REJECTED"
        record.rejection_reason = payload.reason
        record.decided_by = principal.user_id
        record.decided_at = audit_datetime.now(audit_timezone.utc)

    return {
        "allocation_id": allocation_id,
        "status": "REJECTED",
        "message": "Allocation rejected. Inventory unchanged.",
    }
