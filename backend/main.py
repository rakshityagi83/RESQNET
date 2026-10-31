import heapq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="RESQNET API",
    description="Disaster Intelligence and Relief Coordination Network",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
        }
    ]

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
def analyze_disaster():
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

    incidents.sort(
        key=lambda incident: incident["priority_score"],
        reverse=True
    )

    return {
        "total_incidents": len(incidents),
        "priority_order": incidents
    }
@app.get("/allocate-resources")
def allocate_resources():

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
            "food_allocated": food_allocated,
            "water_allocated": water_allocated,
            "medicine_allocated": medicine_allocated,
            "food_shortage": food_needed - food_allocated,
            "water_shortage": water_needed - water_allocated,
            "medicine_shortage": medicine_needed - medicine_allocated
        })

    return {
        "allocations": allocations,
        "remaining_inventory": inventory
    }

    

@app.get("/plan-route")
def plan_route():

    graph = {
        "Warehouse": {"Sector 15": 4, "Green Valley": 6},
        "Sector 15": {"Warehouse": 4, "Old Town": 5},
        "Green Valley": {"Warehouse": 6, "Old Town": 3},
        "Old Town": {"Sector 15": 5, "Green Valley": 3}
    }

    blocked_roads = [
        ("Warehouse", "Green Valley")
    ]

    for road in blocked_roads:
        start, end = road
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

    for destination in graph:
        if destination == "Warehouse":
            continue

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
            "distance_km": distances[destination]
        }

    return {
        "starting_point": "Warehouse",
        "blocked_roads": blocked_roads,
        "routes": routes
    }