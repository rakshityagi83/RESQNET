from google import genai
import os
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
import heapq
import json
import urllib.request
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="RESQNET API",
    description="Disaster Intelligence and Relief Coordination Network",
    version="1.0.0"
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
    return {
        "message": "RESQNET backend is operational",
        "status": "online"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}



@app.get("/incidents")
def get_incidents():
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "RESQNET/1.0"}
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        incidents = []

        for feature in data.get("features", []):
            properties = feature.get("properties", {})
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates", [])

            if (
                geometry.get("type") != "Point"
                or len(coordinates) < 2
            ):
                continue

            incidents.append({
                "id": f"GDACS-{properties.get('eventtype')}-{properties.get('eventid')}",
                "location": properties.get("name") or properties.get("country") or "Unknown location",
                "type": properties.get("eventtype", "Unknown"),
                "severity": properties.get("alertlevel", "Unknown"),
                "people": properties.get("population"),
                "time": properties.get("fromdate"),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
                "source": "GDACS",
                "source_url": (properties.get("url") or {}).get("report")
            })

        return incidents

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve GDACS events: {str(error)}"
        )
@app.get("/priority-incidents")
def get_priority_incidents():
    incidents = get_incidents()

    priority_levels = {"Red", "Orange"}

    priority_incidents = [
        incident
        for incident in incidents
        if incident["severity"] in priority_levels
    ]

    return {
        "source": "GDACS",
        "total_events": len(incidents),
        "priority_events": len(priority_incidents),
        "incidents": priority_incidents
    }
@app.get("/simulate-flood")
def simulate_flood():
    return [
        {
            "id": "INC-001",
            "location": "Sector 15, Riverside",
            "type": "Flood",
            "severity": "Critical",
            "people": 1250,
            "time": "2 min ago"
        },
        {
            "id": "INC-002",
            "location": "Green Valley District",
            "type": "Flood",
            "severity": "High",
            "people": 840,
            "time": "8 min ago"
        },
        {
            "id": "INC-003",
            "location": "Old Town, Block C",
            "type": "Infrastructure",
            "severity": "Medium",
            "people": 320,
            "time": "14 min ago"
        },
        {
            "id": "INC-004",
            "location": "Riverfront Colony",
            "type": "Flood",
            "severity": "Critical",
            "people": 1100,
            "time": "Just now"
        },
        {
            "id": "INC-005",
            "location": "East Industrial Area",
            "type": "Flood",
            "severity": "High",
            "people": 760,
            "time": "1 min ago"
        },
        {
            "id": "INC-006",
            "location": "Lakeview Extension",
            "type": "Flood",
            "severity": "High",
            "people": 550,
            "time": "2 min ago"
        }
    ]

@app.post("/analyze-disaster")
def analyze_disaster(simulation: bool = False):

    if simulation:
        incidents = simulate_flood()

    else:
        incidents = [
            {
                "id": "INC-001",
                "location": "Sector 15, Riverside",
                "type": "Flood",
                "severity": "Critical",
                "people": 1250,
                "time": "2 min ago"
            },
            {
                "id": "INC-002",
                "location": "Green Valley District",
                "type": "Flood",
                "severity": "High",
                "people": 840,
                "time": "8 min ago"
            },
            {
                "id": "INC-003",
                "location": "Old Town, Block C",
                "type": "Infrastructure",
                "severity": "Medium",
                "people": 320,
                "time": "14 min ago"
            }
        ]

    severity_weights = {
        "Critical": 3,
        "High": 2,
        "Medium": 1
    }

    for incident in incidents:
        score = (
            severity_weights[incident["severity"]] * 40
            + min(incident["people"] / 1250, 1) * 60
        )

        incident["priority_score"] = round(score, 2)

    incidents.sort(
        key=lambda incident: incident["priority_score"],
        reverse=True
    )

    return {
        "total_incidents": len(incidents),
        "priority_order": incidents
    }
    
@app.get("/allocate-resources")
def allocate_resources(simulation: bool = False):

    if simulation:
       incidents = analyze_disaster(simulation=True)["priority_order"]

    else:
        incidents = [
            {
                "id": "INC-001",
                "location": "Sector 15, Riverside",
                "severity": "Critical",
                "people": 1250  
            },
            {
                "id": "INC-002",
                "location": "Green Valley District",
                "severity": "High",
                "people": 840
            },
            {
                "id": "INC-003",
                "location": "Old Town, Block C",
                "severity": "Medium",
                "people": 320
            }
        ]
        severity_weights = {
            "Critical": 3,
            "High": 2,
            "Medium": 1
        }

        for incident in incidents:
            score = (
                severity_weights[incident["severity"]] * 40
                + min(incident["people"] / 1250, 1) * 60
            )
            incident["priority_score"] = round(score, 2)

    inventory = {
        "food": 2000,
        "water": 3000,
        "medicine": 800
    }

    allocations = []

    for incident in incidents:
        people = incident["people"]

        food_needed = people
        water_needed = people * 2
        medicine_needed = max(1, people // 10)

        food_allocated = min(food_needed, inventory["food"])
        water_allocated = min(water_needed, inventory["water"])
        medicine_allocated = min(medicine_needed, inventory["medicine"])

        inventory["food"] -= food_allocated
        inventory["water"] -= water_allocated
        inventory["medicine"] -= medicine_allocated

        allocations.append({
            "incident_id": incident["id"],
            "location": incident["location"],
           "priority_score": incident.get("priority_score", 0),

            "food_allocated": food_allocated,
            "water_allocated": water_allocated,
            "medicine_allocated": medicine_allocated,

            "food_shortage": food_needed - food_allocated,
            "water_shortage": water_needed - water_allocated,
            "medicine_shortage": medicine_needed - medicine_allocated
        })

    return {
        "total_incidents": len(incidents),
        "allocations": allocations,
        "remaining_inventory": inventory
    }
@app.get("/plan-route")
def plan_route(simulation: bool = False):

    graph = {
        "Warehouse": {
            "Sector 15": 4,
            "Green Valley": 6,
            "Riverfront Colony": 5,
            "East Industrial Area": 7,
            "Lakeview Extension": 8
        },
        "Sector 15": {
            "Warehouse": 4,
            "Old Town": 5,
            "Riverfront Colony": 3
        },
        "Green Valley": {
            "Warehouse": 6,
            "Old Town": 3,
            "East Industrial Area": 4
        },
        "Old Town": {
            "Sector 15": 5,
            "Green Valley": 3,
            "Lakeview Extension": 4
        },
        "Riverfront Colony": {
            "Warehouse": 5,
            "Sector 15": 3,
            "Lakeview Extension": 3
        },
        "East Industrial Area": {
            "Warehouse": 7,
            "Green Valley": 4,
            "Lakeview Extension": 5
        },
        "Lakeview Extension": {
            "Warehouse": 8,
            "Old Town": 4,
            "Riverfront Colony": 3,
            "East Industrial Area": 5
        }
    }

    if simulation:
        blocked_roads = [
            ("Warehouse", "Green Valley"),
            ("Sector 15", "Riverfront Colony")
        ]
    else:
        blocked_roads = [
            ("Warehouse", "Green Valley")
        ]

    for start, end in blocked_roads:
        graph[start].pop(end, None)
        graph[end].pop(start, None)

    distances = {node: float("inf") for node in graph}
    previous = {node: None for node in graph}

    distances["Warehouse"] = 0
    queue = [(0, "Warehouse")]

    while queue:
        current_distance, current_node = heapq.heappop(queue)

        if current_distance > distances[current_node]:
            continue

        for neighbor, weight in graph[current_node].items():
            distance = current_distance + weight

            if distance < distances[neighbor]:
                distances[neighbor] = distance
                previous[neighbor] = current_node
                heapq.heappush(queue, (distance, neighbor))

    routes = {}

    destinations = [
        "Sector 15",
        "Green Valley",
        "Old Town"
    ]

    if simulation:
        destinations += [
            "Riverfront Colony",
            "East Industrial Area",
            "Lakeview Extension"
        ]

    for destination in destinations:

        if distances[destination] == float("inf"):
            routes[destination] = {
                "status": "No safe route available"
            }
            continue

        path = []
        current = destination

        while current is not None:
            path.append(current)
            current = previous[current]

        path.reverse()
        routes[destination] = {
            "status": "Route found",
            "path": path,
            "distance_km": distances[destination],
            "route_type": (
                "Alternative"
                if destination == "Green Valley"
                else "Standard"
            )
        }

    return {
        "starting_point": "Warehouse",
        "blocked_roads": blocked_roads,
        "routes": routes
    }
vehicles = [
    {"id": "VEH-01", "type": "Medical Van", "capacity": 500},
    {"id": "VEH-02", "type": "Relief Truck", "capacity": 1000},
    {"id": "VEH-03", "type": "Rescue Van", "capacity": 400},
    {"id": "VEH-04", "type": "Relief Truck", "capacity": 1000},
    {"id": "VEH-05", "type": "Medical Van", "capacity": 500},
    {"id": "VEH-06", "type": "Rescue Van", "capacity": 400}
]



@app.get("/assign-vehicles")
def assign_vehicles(simulation: bool = False):
    if not simulation:
        return {
            "message": "Turn on flood simulation to assign vehicles.",
            "assignments": []
        }

    routes = plan_route(simulation=True)["routes"]

    priority_order = analyze_disaster(simulation=True)["priority_order"]

    available_vehicles = vehicles.copy()
    assignments = []
    for incident in priority_order:
        location_mapping = {
            "Sector 15, Riverside": "Sector 15",
            "Green Valley District": "Green Valley",
            "Old Town, Block C": "Old Town",
            "Riverfront Colony": "Riverfront Colony",
            "East Industrial Area": "East Industrial Area",
            "Lakeview Extension": "Lakeview Extension"
        }

        destination = location_mapping.get(incident["location"])
        route = routes.get(destination)

        if not route or route["status"] != "Route found":
            continue

        if not available_vehicles:
            break

        vehicle = available_vehicles.pop(0)

        assignments.append({
            "incident_id": incident["id"],
            "location": incident["location"],
            "priority_score": incident["priority_score"],
            "vehicle_id": vehicle["id"],
            "vehicle_type": vehicle["type"],
            "vehicle_capacity": vehicle["capacity"],
            "route": route["path"],
            "distance_km": route["distance_km"],
            "status": "Assigned (Simulation)"
        })
    return {
        "total_vehicles": len(vehicles),
        "assigned_vehicles": len(assignments),
        "unassigned_incidents": len(priority_order) - len(assignments),
        "assignments": assignments
    }
@app.get("/analyze-incident/{incident_id}")
def analyze_incident(incident_id: str):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Gemini API key is not configured."
        )

    incidents = get_incidents()

    incident = next(
        (item for item in incidents if item["id"] == incident_id),
        None
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident not found in the live GDACS feed."
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are RESQNET's disaster intelligence analyst.

Analyze this verified GDACS incident:

Location: {incident['location']}
Disaster type: {incident['type']}
Alert level: {incident['severity']}
Reported population: {incident['people']}
Event time: {incident['time']}
Coordinates: {incident['latitude']}, {incident['longitude']}
Source: GDACS
Source report: {incident['source_url']}

Provide:
1. Incident overview
2. Potential risks
3. Recommended emergency response priorities
4. Information gaps and uncertainties

IMPORTANT:
- Do not invent casualty counts or affected population.
- Distinguish verified information from potential risks.
- Do not claim roads are blocked or routes are safe.
- Do not claim resources are available.
- Clearly state that recommendations require human verification.
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

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini analysis failed: {str(error)}"
        )