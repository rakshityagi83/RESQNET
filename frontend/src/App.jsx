
import { useState, useEffect } from 'react'
import DisasterMap from './components/DisasterMap'
import {
  Activity, AlertTriangle, Ambulance, ArrowUpRight,
  BrainCircuit, CheckCircle2, Clock, Droplets,
  HeartPulse, MapPin, Package, Radio, Shield,
  Truck, Users, Waves, Zap
} from 'lucide-react'


const normalIncidents = [
  { id: 'INC-001', location: 'Sector 15, Riverside', type: 'Flood', severity: 'Critical', people: 1250, time: '2 min ago' },
  { id: 'INC-002', location: 'Green Valley District', type: 'Flood', severity: 'High', people: 840, time: '8 min ago' },
  { id: 'INC-003', location: 'Old Town, Block C', type: 'Infrastructure', severity: 'Medium', people: 320, time: '14 min ago' },
]

const floodIncidents = [
  ...normalIncidents,
  { id: 'INC-004', location: 'Riverfront Colony', type: 'Flood', severity: 'Critical', people: 1100, time: 'Just now' },
  { id: 'INC-005', location: 'East Industrial Area', type: 'Flood', severity: 'High', people: 760, time: '1 min ago' },
  { id: 'INC-006', location: 'Lakeview Extension', type: 'Flood', severity: 'High', people: 550, time: '2 min ago' },
]



const normalInventory = [
  { name: 'Drinking Water', stock: 840, unit: 'litres', percent: 84, icon: Droplets },
  { name: 'Food Packages', stock: 420, unit: 'units', percent: 42, icon: Package },
  { name: 'Medical Kits', stock: 85, unit: 'kits', percent: 17, icon: HeartPulse },
]

const floodInventory = [
  { name: 'Drinking Water', stock: 520, unit: 'litres', percent: 52, icon: Droplets },
  { name: 'Food Packages', stock: 180, unit: 'units', percent: 18, icon: Package },
  { name: 'Medical Kits', stock: 35, unit: 'kits', percent: 7, icon: HeartPulse },
]



const normalActivities = [
  { title: 'Incident Intelligence Agent', detail: 'Monitoring incoming disaster reports', time: 'Just now', status: 'Completed' },
  { title: 'Resource Management Agent', detail: 'Warehouse inventory checked', time: '1 min ago', status: 'Completed' },
  { title: 'Route Planning Agent', detail: 'Available routes verified', time: '2 min ago', status: 'Completed' },
  { title: 'Emergency Coordinator', detail: 'System awaiting emergency input', time: '3 min ago', status: 'Pending' },
]

const floodActivities = [
  { title: 'Incident Intelligence Agent', detail: 'Six flood incidents identified', time: 'Just now', status: 'Completed' },
  { title: 'Resource Management Agent', detail: 'Critical medical stock shortage detected', time: '1 min ago', status: 'Warning' },
  { title: 'Route Planning Agent', detail: 'Blocked roads detected; alternatives required', time: '2 min ago', status: 'Warning' },
  { title: 'Emergency Coordinator', detail: 'Relief dispatch awaiting human approval', time: '3 min ago', status: 'Pending' },
]


function App() {
  const [plannedRoutes, setPlannedRoutes] = useState({})
  const [activeTab, setActiveTab] = useState('Overview')
  const [simulation, setSimulation] = useState(false)
  const [apiIncidents, setApiIncidents] = useState([])
const [apiStatus, setApiStatus] = useState('Connecting...')
const [priorityScores, setPriorityScores] = useState({})
const [resourceAllocations, setResourceAllocations] = useState([])
const [remainingInventory, setRemainingInventory] = useState({})
useEffect(() => {
  const endpoint = simulation
    ? 'http://127.0.0.1:8000/simulate-flood'
    : 'http://127.0.0.1:8000/incidents'

  // Fetch incidents
  fetch(endpoint)
    .then((response) => {
      if (!response.ok) {
        throw new Error('Backend request failed')
      }
      return response.json()
    })
    .then((data) => {
      setApiIncidents(data)
      setApiStatus('Connected')
    })
    .catch(() => {
      setApiStatus('Disconnected')
    })

  // Fetch priority scores
  fetch('http://127.0.0.1:8000/analyze-disaster', {
    method: 'POST'
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error('Priority analysis failed')
      }
      return response.json()
    })
    .then((data) => {
      const scores = {}

      data.priority_order.forEach((incident) => {
        scores[incident.id] = incident.priority_score
      })

      setPriorityScores(scores)
    })
    .catch((error) => {
      console.error('Priority analysis failed:', error)
    })

  // Fetch resource allocations
  fetch('http://127.0.0.1:8000/allocate-resources')
    .then((response) => {
      if (!response.ok) {
        throw new Error('Resource allocation failed')
      }
      return response.json()
    })
    .then((data) => {
      setResourceAllocations(data.allocations)
      setRemainingInventory(data.remaining_inventory)
    })
    .catch((error) => {
      console.error('Resource allocation failed:', error)
    })// Fetch planned routes
    fetch('http://127.0.0.1:8000/plan-route')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Route planning failed')
        }
        return response.json()
      })
      .then((data) => {
        setPlannedRoutes(data.routes)
      })
      .catch((error) => {
        console.error('Route planning failed:', error)
      })
}, [simulation])
const incidents = simulation
  ? floodIncidents
  : apiIncidents.length > 0
    ? apiIncidents
    : normalIncidents
    const inventory = simulation ? floodInventory : normalInventory

    const liveInventory = inventory.map((item) => {
    const stockMap = {
      'Drinking Water': remainingInventory.water,
      'Food Packages': remainingInventory.food,
      'Medical Kits': remainingInventory.medicine
    }
  
    const stock = stockMap[item.name] ?? item.stock
  
    return {
      ...item,
      stock,
      percent: Math.round((stock / (item.stock || 1)) * 100)
    }
  })
  const activities = simulation ? floodActivities : normalActivities

  return (
    <div className="min-h-screen bg-[#080d18] text-slate-100">
      <div className="flex min-h-screen">

        {/* Sidebar */}
        <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-[#0c1422] p-5 lg:flex lg:flex-col">
          <div className="mb-10 flex items-center gap-3">
            <div className="rounded-xl bg-cyan-500/15 p-2.5 text-cyan-400">
              <Shield size={25} />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-wide">RESQNET</h1>
              <p className="text-[10px] tracking-[3px] text-slate-500">RESPONSE NETWORK</p>
            </div>
          </div>

          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Workspace</p>
          <nav className="space-y-2">
            {[
              ['Overview', Activity],
              ['Incidents', AlertTriangle],
              ['Relief Inventory', Package],
              ['Fleet & Routes', Truck],
              ['AI Coordination', BrainCircuit],
            ].map(([name, Icon]) => (
              <button
                key={name}
                onClick={() => setActiveTab(name)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm transition ${
                  activeTab === name
                    ? 'bg-cyan-500/10 text-cyan-400'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Icon size={18} />
                {name}
              </button>
            ))}
          </nav>

          <div className="mt-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="mb-2 flex items-center gap-2 text-xs text-emerald-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              SYSTEM OPERATIONAL
            </div>
            <p className="text-xs text-slate-500">RESQNET Simulation v1.0</p>
            <p className="mt-1 text-xs text-slate-600">Hackathon prototype</p>
          </div>
        </aside>

        {/* Main content */}
        <main className="min-w-0 flex-1 p-5 md:p-8">

          {/* Header */}
          <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="mb-1 flex items-center gap-2 text-xs text-cyan-400">
                <Radio size={14} />
                EMERGENCY OPERATIONS CENTRE
              </div>
              <h2 className="text-2xl font-bold md:text-3xl">{activeTab}</h2>
              <p className="mt-1 text-sm text-slate-500">
                Disaster intelligence and relief coordination
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-400 sm:flex">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                {apiStatus === 'Connected' ? 'Backend connected' : apiStatus}
              </div>
              <button
                onClick={() => setSimulation(!simulation)}
                className="flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
              >
                <Zap size={16} />
                {simulation ? 'Reset Simulation' : 'Simulate Flood'}
              </button>
            </div>
          </header>

          {/* Simulation notice */}
          {simulation && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-300">
              <AlertTriangle size={20} />
              Flood simulation activated. Displayed incident data is simulated.
            </div>
          )}

          {/* Metrics */}
          <section className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: 'Active Incidents', value: simulation ? '06' : '03', change: 'Requires attention', icon: AlertTriangle, color: 'text-rose-400', bg: 'bg-rose-500/10' },
              { label: 'People Affected', value: simulation ? '4,820' : '2,410', change: 'Across 3 locations', icon: Users, color: 'text-amber-400', bg: 'bg-amber-500/10' },
              { label: 'Relief Vehicles', value: '08', change: '5 available', icon: Ambulance, color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
              { label: 'Resources Deployed', value: '64%', change: 'Of available stock', icon: Package, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-sm text-slate-400">{item.label}</p>
                  <div className={`rounded-xl p-2.5 ${item.bg} ${item.color}`}>
                    <item.icon size={19} />
                  </div>
                </div>
                <h3 className="text-3xl font-bold">{item.value}</h3>
                <p className="mt-2 text-xs text-slate-500">{item.change}</p>
              </div>
            ))}
          </section>

          {/* Map and incidents */}
          <section className="mb-7 grid grid-cols-1 gap-5 xl:grid-cols-3">

            {/* Map placeholder */}
            <div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5 xl:col-span-2">
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">Disaster Monitoring Map</h3>
                  <p className="mt-1 text-xs text-slate-500">Incident locations and response zones</p>
                </div>
                <span className="rounded-lg bg-rose-500/10 px-3 py-1.5 text-xs text-rose-400">● Live simulation</span>
              </div>

              <div className="h-72 overflow-hidden rounded-xl border border-slate-700">
  <DisasterMap simulation={simulation} />
</div>

              <div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-400">
                <span><span className="text-rose-400">●</span> Critical</span>
                <span><span className="text-amber-400">●</span> High</span>
                <span><span className="text-yellow-400">●</span> Medium</span>
              </div>
              <div className="mt-5 border-t border-slate-800 pt-4">
  <h3 className="mb-3 font-semibold">Autonomous Route Planner</h3>

  {Object.entries(plannedRoutes).map(([destination, route]) => (
    <div
      key={destination}
      className="mb-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3"
    >
      <p className="text-sm font-medium text-cyan-400">
        {destination}
      </p>

      <p className="mt-1 text-xs text-slate-300">
        {route.path ? route.path.join(' → ') : route.status}
      </p>

      {route.distance_km !== undefined && (
        <p className="mt-1 text-xs text-slate-400">
          Distance: {route.distance_km} km
        </p>
      )}
    </div>
  ))}
</div>
            </div>

            {/* Incidents */}
            <div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="font-semibold">Priority Incidents</h3>
                <span className="text-xs text-cyan-400">View all <ArrowUpRight className="inline" size={13} /></span>
              </div>
              <div className="space-y-4">
                {incidents.map((incident) => (
                  <div key={incident.id} className="border-b border-slate-800 pb-4 last:border-0">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs text-slate-500">{incident.id}</span>
                      <span className={`rounded-md px-2 py-1 text-[10px] ${
                        incident.severity === 'Critical' ? 'bg-rose-500/10 text-rose-400' :
                        incident.severity === 'High' ? 'bg-amber-500/10 text-amber-400' :
                        'bg-yellow-500/10 text-yellow-400'
                      }`}>{incident.severity}</span>
                    </div>
                    <p className="text-sm font-medium">{incident.location}</p><p className="mt-1 text-xs font-semibold text-cyan-400">
  Priority Score: {priorityScores[incident.id] ?? 'Calculating...'}
</p>
{resourceAllocations
  .filter((item) => item.incident_id === incident.id)
  .map((item) => (
    <div
      key={item.incident_id}
      className="mt-2 rounded-md border border-rose-500/20 bg-rose-500/10 p-2"
    >
      {(item.food_shortage > 0 ||
        item.water_shortage > 0 ||
        item.medicine_shortage > 0) ? (
        <>
          <p className="mb-1 text-xs font-semibold text-rose-400">
            RESOURCE SHORTAGE
          </p>

          {item.food_shortage > 0 && (
            <p className="text-xs text-slate-300">
              Food: {item.food_shortage} units
            </p>
          )}

          {item.water_shortage > 0 && (
            <p className="text-xs text-slate-300">
              Water: {item.water_shortage} litres
            </p>
          )}

          {item.medicine_shortage > 0 && (
            <p className="text-xs text-slate-300">
              Medicine: {item.medicine_shortage} kits
            </p>
          )}
        </>
      ) : (
        <p className="text-xs font-semibold text-emerald-400">
          All resource demands fulfilled
        </p>
      )}
    </div>
  ))}
                    <div className="mt-2 flex justify-between text-xs text-slate-500">
                      <span>{incident.people} affected</span>
                      <span>{incident.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Inventory and agents */}
          <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">

            <div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">Relief Inventory</h3>
                  <p className="mt-1 text-xs text-slate-500">Central warehouse stock · Simulated</p>
                </div>
                <Package className="text-cyan-400" size={20} />
              </div>
              <div className="space-y-6">
                {liveInventory.map((item) => (
                  <div key={item.name}>
                    <div className="mb-2 flex justify-between text-sm">
                      <span className="flex items-center gap-2 text-slate-300">
                        <item.icon size={16} className="text-cyan-400" />
                        {item.name}
                      </span>
                      <span className="text-slate-400">{item.stock} {item.unit}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                      <div className={`h-full rounded-full ${item.percent < 25 ? 'bg-rose-400' : 'bg-cyan-400'}`} style={{ width: `${item.percent}%` }} />
                    </div>
                    {item.percent < 25 && (
                      <p className="mt-1 text-[10px] text-rose-400">Low stock warning</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold">AI Agent Activity</h3>
                  <p className="mt-1 text-xs text-slate-500">Coordination system activity log</p>
                </div>
                <BrainCircuit className="text-cyan-400" size={21} />
              </div>
              <div className="space-y-5">
                {activities.map((activity) => (
                  <div key={activity.title} className="flex gap-3">
                    <div className="mt-1">
                      {activity.status === 'Completed'
                        ? <CheckCircle2 className="text-emerald-400" size={17} />
                        : activity.status === 'Warning'
                        ? <AlertTriangle className="text-amber-400" size={17} />
                        : <Clock className="text-cyan-400" size={17} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap justify-between gap-2">
                        <p className="text-sm font-medium">{activity.title}</p>
                        <span className="text-[10px] text-slate-500">{activity.time}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{activity.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <footer className="mt-8 border-t border-slate-800 pt-5 text-center text-xs text-slate-600">
            RESQNET · Disaster Intelligence & Autonomous Relief Coordination Network · Prototype v1.0
          </footer>
        </main>
      </div>
    </div>
  )
}

export default App
