
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
  const [aiAnalyses, setAiAnalyses] = useState({});
const [analyzingId, setAnalyzingId] = useState(null);
  const [plannedRoutes, setPlannedRoutes] = useState({})
  const [vehicleAssignments, setVehicleAssignments] = useState([])
  const [activeTab, setActiveTab] = useState('Overview')
  const [simulation, setSimulation] = useState(false)
  const [apiIncidents, setApiIncidents] = useState([])
const [apiStatus, setApiStatus] = useState('Connecting...')
const [priorityScores, setPriorityScores] = useState({})
const [resourceAllocations, setResourceAllocations] = useState([])
const [remainingInventory, setRemainingInventory] = useState({
  food: 2000,
  water: 3000,
  medicine: 800
})
useEffect(() => {
  setApiStatus('Connecting...')

  fetch('http://127.0.0.1:8000/priority-incidents')
    .then((response) => {
      if (!response.ok) {
        throw new Error('GDACS request failed')
      }
      return response.json()
    })
    .then((data) => {
      setApiIncidents(data.incidents)
      setApiStatus('Connected')
    })
    .catch((error) => {
      console.error('GDACS connection failed:', error)
      setApiIncidents([])
      setApiStatus('Disconnected')
    })
}, [])
const incidents = apiIncidents
const analyzeIncident = async (incidentId) => {
  setAnalyzingId(incidentId);

  try {
    const response = await fetch(
      `http://127.0.0.1:8000/analyze-incident/${encodeURIComponent(incidentId)}`
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "AI analysis failed");
    }

    setAiAnalyses((previous) => ({
      ...previous,
      [incidentId]: data.analysis,
    }));
  } catch (error) {
    alert(error.message);
  } finally {
    setAnalyzingId(null);
  }
};
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
            
            </div>
          </header>
 {/* Live Metrics */}
<section className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
  {[
    {
      label: 'Priority Alerts',
      value: apiIncidents.length,
      detail: 'Live source records',
      icon: Activity,
      color: 'text-cyan-400',
      bg: 'bg-cyan-500/10'
    },
    {
      label: 'Red Alerts',
      value: apiIncidents.filter((item) => item.severity === 'Red').length,
      detail: 'Highest alert level',
      icon: AlertTriangle,
      color: 'text-rose-400',
      bg: 'bg-rose-500/10'
    },
    {
      label: 'Orange Alerts',
      value: apiIncidents.filter((item) => item.severity === 'Orange').length,
      detail: 'Elevated alert level',
      icon: Radio,
      color: 'text-amber-400',
      bg: 'bg-amber-500/10'
    },
    {
      label: 'People Affected',
      value: 'Unavailable',
      detail: 'No verified figure in feed',
      icon: Users,
      color: 'text-slate-400',
      bg: 'bg-slate-500/10'
    },
  ].map((item) => (
    <div key={item.label} className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-slate-400">{item.label}</p>
        <div className={`rounded-xl p-2.5 ${item.bg} ${item.color}`}>
          <item.icon size={19} />
        </div>
      </div>
      <h3 className="text-2xl font-bold">{item.value}</h3>
      <p className="mt-2 text-xs text-slate-500">{item.detail}</p>
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
<DisasterMap incidents={incidents} />
</div>
{simulation && (
  <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-400">
    <div className="flex items-center gap-2">
      <span className="h-2 w-5 border-t-2 border-dashed border-rose-500"></span>
      Blocked Road
    </div>

    <div className="flex items-center gap-2">
      <span className="h-2 w-5 border-t-2 border-green-500"></span>
      Alternative Route
    </div>

    <div className="flex items-center gap-2">
      <span className="h-2 w-2 rounded-full bg-rose-500"></span>
      Critical Incident
    </div>
  </div>
)}

<div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-400">
  <span><span className="text-rose-400">●</span> Red Alert</span>
  <span><span className="text-amber-400">●</span> Orange Alert</span>
  <span><span className="text-green-400">●</span> Green Alert</span>
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
            incident.severity === 'Red' ? 'bg-rose-500/10 text-rose-400' :
            incident.severity === 'Orange' ? 'bg-amber-500/10 text-amber-400' :
            'bg-green-500/10 text-green-400'
          }`}>{incident.severity}</span>
        </div>
        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
  <p className="text-xs font-semibold text-amber-400">
    RESOURCE ALLOCATION PENDING
  </p>
  <p className="mt-1 text-xs text-slate-400">
    Verified warehouse inventory is not connected.
    Resource requirements cannot yet be calculated.
  </p>
</div>
<div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-slate-500">
  <span>Population impact: Not reported</span>
  <span>{incident.time}</span>
</div>
{incident.source_url && (
  <a
    href={incident.source_url}
    target="_blank"
    rel="noreferrer"
    className="mt-2 inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300"
  >
    View official GDACS report
    <ArrowUpRight size={13} />
  </a>
)}

<button
  onClick={() => analyzeIncident(incident.id)}
  disabled={analyzingId === incident.id}
  className="mt-3 w-full rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
>
  {analyzingId === incident.id ? "Analyzing..." : "Generate AI Analysis"}
</button>

{aiAnalyses[incident.id] && (
  <div className="mt-3 rounded-lg border border-cyan-500/30 bg-slate-900 p-4">
    <h4 className="mb-2 font-semibold text-cyan-400">
      RESQNET AI Analysis
    </h4>
    <div className="whitespace-pre-wrap text-sm leading-6 text-slate-300">
      {aiAnalyses[incident.id]}
    </div>
    <p className="mt-3 text-xs text-amber-400">
      AI-generated recommendations. Human verification required.
    </p>
  </div>
)}

      </div>
    ))}
  </div>
</div>
</section>

          {/* Simulation notice */}
          {simulation && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-300">
              <AlertTriangle size={20} />
              Flood simulation activated. Displayed incident data is simulated.
            </div>
          )}

       {/* Resource Distribution */}
<section className="mb-7 rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
  <div className="mb-4 flex items-center justify-between">
    <div>
      <h3 className="text-lg font-semibold">Resource Distribution</h3>
      <p className="mt-1 text-xs text-slate-500">
        Emergency supply planning and allocation
      </p>
    </div>
    <span className="text-xs text-amber-400">
      Awaiting Inventory Data
    </span>
  </div>

  <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
    <Package className="mb-3 text-amber-400" size={22} />

    <p className="text-sm font-medium text-amber-300">
      Resource allocation unavailable
    </p>

    <p className="mt-2 text-xs leading-5 text-slate-400">
      No verified warehouse inventory or supply availability
      source is connected. RESQNET cannot currently calculate
      resource requirements or recommend allocations.
    </p>
  </div>
</section>
         {/* Inventory and agents */}
<section className="grid grid-cols-1 gap-5 xl:grid-cols-2">

<div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
  <div className="mb-6 flex items-center justify-between">
    <div>
      <h3 className="font-semibold">Relief Inventory</h3>
      <p className="mt-1 text-xs text-slate-500">
        Operational warehouse data
      </p>
    </div>
    <Package className="text-cyan-400" size={20} />
  </div>

  <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
    <AlertTriangle className="mb-3 text-amber-400" size={22} />
    <p className="text-sm font-medium text-amber-300">
      Inventory data not connected
    </p>
    <p className="mt-2 text-xs leading-5 text-slate-400">
      RESQNET does not currently have access to a verified warehouse
      inventory source. Resource quantities and allocations are
      therefore unavailable.
    </p>
  </div>
</div>

<div className="rounded-2xl border border-slate-800 bg-[#101a2b] p-5">
  <div className="mb-6 flex items-center justify-between">
    <div>
      <h3 className="font-semibold">AI Agent Activity</h3>
      <p className="mt-1 text-xs text-slate-500">
        System activity status
      </p>
    </div>
    <BrainCircuit className="text-cyan-400" size={21} />
  </div>

  <div className="space-y-4">
    <div className="flex gap-3">
      <CheckCircle2 className="mt-1 text-emerald-400" size={17} />
      <div>
        <p className="text-sm font-medium">GDACS Data Retrieval</p>
        <p className="mt-1 text-xs text-slate-500">
          Live disaster event feed retrieved successfully.
        </p>
      </div>
    </div>

    <div className="flex gap-3">
      <CheckCircle2 className="mt-1 text-emerald-400" size={17} />
      <div>
        <p className="text-sm font-medium">Priority Alert Filtering</p>
        <p className="mt-1 text-xs text-slate-500">
          Red and Orange alerts separated from the event feed.
        </p>
      </div>
    </div>

    <div className="flex gap-3">
      <Clock className="mt-1 text-cyan-400" size={17} />
      <div>
        <p className="text-sm font-medium">AI Disaster Analysis</p>
        <p className="mt-1 text-xs text-slate-500">
          Not connected yet.
        </p>
      </div>
    </div>
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
