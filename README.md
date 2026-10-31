# RESQNET 🌊

### Disaster Intelligence & Autonomous Relief Coordination Network

**An intelligent disaster-response coordination platform designed to simulate emergency resource allocation and autonomous relief route planning.**

---

## 🚨 Problem Statement

During natural disasters such as floods, emergency response teams face challenges involving resource shortages, delayed coordination, affected population prioritisation and blocked transportation routes.

RESQNET explores how intelligent algorithms can help coordinate relief operations and improve resource distribution.

## 💡 Our Solution

RESQNET is a disaster-management dashboard that simulates emergency scenarios and helps coordinate relief resources.

It analyses affected locations, calculates priority scores, allocates available supplies and plans routes while avoiding blocked roads.

## ✨ Key Features

- **Disaster Monitoring:** View affected locations and incident details.
- **Flood Simulation:** Activate a simulated flood scenario involving multiple locations.
- **Priority Analysis:** Calculate incident priority scores using severity and affected population.
- **Smart Resource Allocation:** Distribute food, drinking water and medical supplies according to requirements and available inventory.
- **Shortage Detection:** Identify resource shortages at affected locations.
- **Autonomous Route Planning:** Calculate shortest routes using Dijkstra's algorithm.
- **Blocked Road Avoidance:** Exclude blocked roads from route calculations.
- **Operations Dashboard:** Monitor incidents, inventory, allocations and planned routes.

## 🛠️ Technology Stack

| Component       | Technology               |
| --------------- | ------------------------ |
| Frontend        | React, Vite              |
| Styling         | Tailwind CSS             |
| Backend         | Python, FastAPI          |
| Mapping         | Leaflet, OpenStreetMap   |
| Route Algorithm | Dijkstra's Shortest Path |
| Version Control | Git, GitHub              |

## 🏗️ System Architecture

```
        RESQNET Dashboard
          React + Vite
               |
               | API Requests
               |
        FastAPI Backend
               |
      +--------+---------+
      |        |         |
   Priority  Resource   Route
   Analysis  Allocation Planning
      |        |         |
      +--------+---------+
               |
        Response Data
               |
       Dashboard + Map
```

## ⚙️ How It Works

1. The system displays disaster incidents.
2. A flood simulation introduces additional affected locations.
3. Each incident receives a priority score based on severity and population.
4. Available inventory is allocated according to calculated requirements.
5. Resource shortages are identified.
6. Dijkstra's algorithm calculates routes from the warehouse while avoiding blocked roads.
7. The dashboard displays the resulting response plan.

## 🧮 Algorithms

### Priority Scoring

Incidents are prioritised using severity weights and affected population.

### Resource Allocation

Available food, water and medicine are distributed according to incident requirements and remaining inventory.

### Dijkstra's Shortest Path

The route planner calculates shortest paths through a simulated road network while excluding blocked connections.

## 🚀 Getting Started

### Prerequisites

- Python
- Node.js and npm
- Git

### 1. Clone the repository

```
git clone https://github.com/rakshityagi83/RESQNET.git
cd RESQNET
```

### 2. Start the backend

```
cd backend
python -m venv venv
```

Activate the environment on Windows:

```
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```
pip install fastapi uvicorn
```

Start the API:

```
uvicorn main:app --reload
```

Backend API: `http://127.0.0.1:8000`

API documentation: `http://127.0.0.1:8000/docs`

### 3. Start the frontend

Open another terminal:

```
cd frontend
npm install
npm run dev
```

Open the frontend at:

`http://localhost:5173`

## 🌍 Expected Impact

- Improve coordination during simulated disaster scenarios.
- Support prioritisation of affected populations.
- Help identify shortages in emergency supplies.
- Demonstrate safer route planning around blocked roads.
- Explore algorithm-assisted emergency logistics.

## 🔮 Future Scope

- Integration with real-time weather and disaster information.
- AI-assisted emergency report analysis.
- Dynamic vehicle and delivery assignment.
- Real-world road network integration.
- Live inventory and warehouse synchronisation.
- Multi-agent coordination for large-scale relief operations.

## ⚠️ Limitations

RESQNET currently uses simulated disaster incidents, inventory values and road-network data. Its route calculations are based on a simulated graph, not live GPS or real-world road conditions.

The platform is a prototype for demonstrating disaster-response coordination concepts. It does not dispatch actual emergency services or vehicles.

## 👥 Team

**Project:** RESQNET  
**Theme:** Climate, Resource Infrastructure & Global Supply Resilience  
**Problem Statement:** Autonomous Emergency Response & Supply Chain Logistics Swarm

**Team Members:**

- [Add team member 1]
- [Add team member 2]

---

*Built as a hackathon prototype exploring intelligent disaster-response and relief coordination.*