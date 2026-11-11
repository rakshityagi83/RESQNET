
import { useState, useEffect, useRef } from 'react'
import DisasterMap from './components/DisasterMap'
import {
  Activity, AlertTriangle, ArrowUpRight, BrainCircuit,
  CheckCircle2, Clock, Droplets, HeartPulse, Package,
  Radio, Shield, Users, Warehouse, RefreshCw, Truck
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function App() {
  const [activeTab, setActiveTab] = useState('Overview')
  const [incidents, setIncidents] = useState([])
  const [allIncidents, setAllIncidents] = useState([])
  const [incidentMode, setIncidentMode] = useState('live')
const [historicalIncidents, setHistoricalIncidents] = useState([])
const [historyLoading, setHistoryLoading] = useState(false)
const [historyError, setHistoryError] = useState('')
  const [warehouses, setWarehouses] = useState([])
  const [discoveredWarehouses, setDiscoveredWarehouses] = useState([])
  const [warehouseFilter, setWarehouseFilter] = useState('all')
  const [incidentFilter, setIncidentFilter] = useState('all')
  const [apiStatus, setApiStatus] = useState('Connecting...')
  const [loading, setLoading] = useState(false)
const [message, setMessage] = useState('')
const [aiAnalyses, setAiAnalyses] = useState({})
const [analyzingId, setAnalyzingId] = useState(null)
const [selectedAnalysisId, setSelectedAnalysisId] = useState(null)

const [selectedRouteIncident, setSelectedRouteIncident] = useState(null)
const [selectedRouteWarehouse, setSelectedRouteWarehouse] = useState(null)

const [routeResult, setRouteResult] = useState(null)
const [routeLoading, setRouteLoading] = useState(false)
const [routeError, setRouteError] = useState('')

const [recommendedWarehouses, setRecommendedWarehouses] = useState([])
const [liveFeedError, setLiveFeedError] = useState('')
const registeredRequestIdRef = useRef(0)
const osmRequestIdRef = useRef(0)
const [registeredRecommendations, setRegisteredRecommendations] = useState([])
const [registeredRecommendationsLoading, setRegisteredRecommendationsLoading] = useState(false)
const [registeredRecommendationsError, setRegisteredRecommendationsError] = useState('')

const [registeredRequirements, setRegisteredRequirements] = useState({
  food: '',
  water: '',
  medicine: ''
})

const [recommendationsLoading, setRecommendationsLoading] = useState(false)
const [recommendationsError, setRecommendationsError] = useState('')


  const [allocation, setAllocation] = useState(null)
  const [allocating, setAllocating] = useState(false)

  const [warehouseForm, setWarehouseForm] = useState({
    name: '',
    state: '',
    district: '',
    latitude: '',
    longitude: '',
    verified_by: '',
    food: 0,
    water: 0,
    medicine: 0
  })

  const [allocationForm, setAllocationForm] = useState({
    incident_id: '',
    warehouse_id: '',
    food: 0,
    water: 0,
    medicine: 0
  })

  const loadData = async () => {
    setLoading(true)
    setMessage('')
    setLiveFeedError('')

    const [incidentResult, warehouseResult] = await Promise.allSettled([
      (async () => {
        const response = await fetch(`${API}/india-incidents`)

        if (!response.ok) {
          throw new Error(`GDACS request failed (HTTP ${response.status})`)
        }

        return response.json()
      })(),

      (async () => {
        const response = await fetch(`${API}/warehouses`)

        if (!response.ok) {
          throw new Error(`Warehouse request failed (HTTP ${response.status})`)
        }

        return response.json()
      })()
    ])

    if (incidentResult.status === 'fulfilled') {
      const fetchedIncidents = Array.isArray(incidentResult.value.incidents)
        ? incidentResult.value.incidents
        : []

      const priorityIncidents = fetchedIncidents.filter(
        incident => ['Red', 'Orange'].includes(incident.severity)
      )

      setAllIncidents(fetchedIncidents)
      setIncidents(priorityIncidents)

      if (
        allocationForm.incident_id &&
        !priorityIncidents.some(
          item => item.id === allocationForm.incident_id
        )
      ) {
        setAllocationForm(previous => ({
          ...previous,
          incident_id: ''
        }))
        setAllocation(null)
      }
    } else {
      setAllIncidents([])
      setIncidents([])
      setLiveFeedError(
        'Live GDACS feed unavailable. Current incident status cannot be confirmed.'
      )
    }

    if (warehouseResult.status === 'fulfilled') {
      setWarehouses(
        Array.isArray(warehouseResult.value)
          ? warehouseResult.value
          : []
      )
    } else {
      setMessage('Registered warehouse data unavailable.')
    }

    setApiStatus(
      incidentResult.status === 'fulfilled' &&
      warehouseResult.status === 'fulfilled'
        ? 'Connected'
        : 'Degraded'
    )

    setLoading(false)
  }


  useEffect(() => {
    loadData()
  }, [])

useEffect(() => {
  const loadDiscoveredWarehouses = async () => {
    try {
      const response = await fetch(
        `${API}/warehouses/discover/snapshot`
      )

      if (!response.ok) {
        throw new Error('Warehouse snapshot unavailable')
      }

      const data = await response.json()

      setDiscoveredWarehouses(data.warehouses || [])

      console.log(
        'Discovered warehouses:',
        data.total
      )
    } catch (error) {
      console.error(
        'Warehouse discovery error:',
        error
      )
    }
  }

  loadDiscoveredWarehouses()
}, [])


useEffect(() => {
  if (incidentMode !== 'historical') return

  const controller = new AbortController()

  const loadHistoricalIncidents = async () => {
    setHistoryLoading(true)
    setHistoryError('')

    try {
      const response = await fetch(
        `${API}/historical-incidents?days=60`,
        { signal: controller.signal }
      )

      if (!response.ok) {
        throw new Error('Historical GDACS data unavailable')
      }

      const data = await response.json()

      if (!controller.signal.aborted) {
        setHistoricalIncidents(
          Array.isArray(data.incidents) ? data.incidents : []
        )
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setHistoryError(error.message)
      }
    } finally {
      if (!controller.signal.aborted) {
        setHistoryLoading(false)
      }
    }
  }

  loadHistoricalIncidents()

  return () => controller.abort()
}, [incidentMode])


useEffect(() => {
  if (!selectedRouteIncident || !selectedRouteWarehouse) {
    setRouteResult(null)
    setRouteError('')
    setRouteLoading(false)
    return
  }

  const controller = new AbortController()

  const calculateRoute = async () => {
    setRouteLoading(true)
    setRouteResult(null)
    setRouteError('')

    try {
      const response = await fetch(`${API}/routing/calculate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        signal: controller.signal,
        body: JSON.stringify({
          warehouse_lat: Number(selectedRouteWarehouse.latitude),
          warehouse_lon: Number(selectedRouteWarehouse.longitude),
          incident_lat: Number(selectedRouteIncident.latitude),
          incident_lon: Number(selectedRouteIncident.longitude)
        })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Route calculation failed')
      }

      if (!controller.signal.aborted) {
        setRouteResult(data)
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setRouteError(error.message)
      }
    } finally {
      if (!controller.signal.aborted) {
        setRouteLoading(false)
      }
    }
  }

  calculateRoute()

  return () => controller.abort()
}, [selectedRouteIncident, selectedRouteWarehouse])


  const updateWarehouseForm = (key, value) => {
    setWarehouseForm(previous => ({ ...previous, [key]: value }))
  }

  const updateAllocationForm = (key, value) => {
    setAllocationForm(previous => ({ ...previous, [key]: value }))
    setAllocation(null)
  }

  const registerWarehouse = async (event) => {
    event.preventDefault()
    setMessage('Registering warehouse...')

    try {
      const response = await fetch(`${API}/warehouses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: warehouseForm.name,
          state: warehouseForm.state,
          district: warehouseForm.district,
          latitude: warehouseForm.latitude === '' ? null : Number(warehouseForm.latitude),
          longitude: warehouseForm.longitude === '' ? null : Number(warehouseForm.longitude),
          verified_by: warehouseForm.verified_by
        })
      })

      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Warehouse registration failed')

      const inventoryResponse = await fetch(
        `${API}/warehouses/${data.warehouse_id}/inventory`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            food: Number(warehouseForm.food),
            water: Number(warehouseForm.water),
            medicine: Number(warehouseForm.medicine)
          })
        }
      )

      const inventoryData = await inventoryResponse.json()
      if (!inventoryResponse.ok) {
        throw new Error(inventoryData.detail || 'Inventory update failed')
      }

      setWarehouseForm({
        name: '', state: '', district: '',
        latitude: '', longitude: '', verified_by: '',
        food: 0, water: 0, medicine: 0
      })

      setMessage('Warehouse and inventory registered successfully.')
      await loadData()
    } catch (error) {
      setMessage(error.message)
    }
  }

  const updateStock = async (warehouse) => {
    const food = window.prompt('Enter confirmed food stock:', warehouse.food)
    if (food === null) return
    const water = window.prompt('Enter confirmed water stock:', warehouse.water)
    if (water === null) return
    const medicine = window.prompt('Enter confirmed medicine stock:', warehouse.medicine)
    if (medicine === null) return

    const values = [food, water, medicine].map(Number)
    if (values.some(value => !Number.isInteger(value) || value < 0)) {
      setMessage('Enter non-negative whole numbers for all stock quantities.')
      return
    }

    try {
      const response = await fetch(
        `${API}/warehouses/${warehouse.id}/inventory`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            food: values[0],
            water: values[1],
            medicine: values[2]
          })
        }
      )

      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Stock update failed')

      setMessage('Inventory updated.')
      await loadData()
    } catch (error) {
      setMessage(error.message)
    }
  }

  const analyzeIncident = async (incidentId) => {
    setAnalyzingId(incidentId)

    try {
      const response = await fetch(
        `${API}/analyze-incident/${encodeURIComponent(incidentId)}`
      )
      const data = await response.json()

      if (!response.ok) throw new Error(data.detail || 'AI analysis failed')

      setAiAnalyses(previous => ({
        ...previous,
        [incidentId]: data.analysis
      }))
    } catch (error) {
      setMessage(error.message)
    } finally {
      setAnalyzingId(null)
    }
  }

const analyzeFromMap = (incidentId) => {
  setSelectedAnalysisId(incidentId)
  analyzeIncident(incidentId)
}

const recommendForIncident = async (incident) => {
  const requestId = ++osmRequestIdRef.current

  // Invalidate previous registered warehouse requests.
  registeredRequestIdRef.current += 1

  setSelectedRouteIncident(incident)
  setSelectedRouteWarehouse(null)

  setRegisteredRecommendations([])
  setRegisteredRecommendationsError('')
  setRegisteredRecommendationsLoading(false)

  setRecommendedWarehouses([])
  setRecommendationsError('')
  setRecommendationsLoading(true)

  try {
    const response = await fetch(
      `${API}/recommendations/ranked`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          incident_lat: Number(incident.latitude),
          incident_lon: Number(incident.longitude),
          limit: 10
        })
      }
    )

    const data = await response.json()

    // Ignore results from a previously selected incident.
    if (requestId !== osmRequestIdRef.current) {
      return
    }

    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : 'Warehouse recommendation failed'
      )
    }

    setRecommendedWarehouses(
      Array.isArray(data.candidates) ? data.candidates : []
    )

  } catch (error) {
    if (requestId === osmRequestIdRef.current) {
      setRecommendationsError(error.message)
    }
  } finally {
    if (requestId === osmRequestIdRef.current) {
      setRecommendationsLoading(false)
    }
  }
}

const recommendRegisteredForIncident = async (incident) => {
  const requestId = ++registeredRequestIdRef.current

  setRegisteredRecommendations([])
  setRegisteredRecommendationsError('')
  setRegisteredRecommendationsLoading(true)

  try {
    const requirements = {
      food: Number(registeredRequirements.food),
      water: Number(registeredRequirements.water),
      medicine: Number(registeredRequirements.medicine)
    }

    if (
      Object.values(requirements).some(
        value => !Number.isSafeInteger(value) || value < 0
      )
    ) {
      throw new Error(
        'Enter valid non-negative whole numbers for supplies.'
      )
    }

    if (!Object.values(requirements).some(value => value > 0)) {
      throw new Error('Request at least one supply.')
    }

    const response = await fetch(
      `${API}/recommendations/registered/ranked`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          incident_lat: Number(incident.latitude),
          incident_lon: Number(incident.longitude),
          ...requirements,
          limit: 10
        })
      }
    )

    const data = await response.json()

    // Ignore responses belonging to an older request or incident.
    if (requestId !== registeredRequestIdRef.current) {
      return
    }

    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : 'Registered warehouse recommendation failed'
      )
    }

    setRegisteredRecommendations(
      Array.isArray(data.warehouses) ? data.warehouses : []
    )

  } catch (error) {
    if (requestId === registeredRequestIdRef.current) {
      setRegisteredRecommendationsError(error.message)
    }
  } finally {
    if (requestId === registeredRequestIdRef.current) {
      setRegisteredRecommendationsLoading(false)
    }
  }
}


useEffect(() => {
  if (!selectedAnalysisId || !aiAnalyses[selectedAnalysisId]) {
    return
  }

  document.getElementById('gemini-analysis-panel')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start'
  })
}, [selectedAnalysisId, aiAnalyses])



  const previewAllocation = async (event) => {
    event.preventDefault()
    setAllocating(true)
    setAllocation(null)
    setMessage('Calculating allocation preview...')

    try {
      const response = await fetch(`${API}/allocation/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_id: allocationForm.incident_id,
          warehouse_id: Number(allocationForm.warehouse_id),
          food: Number(allocationForm.food),
          water: Number(allocationForm.water),
          medicine: Number(allocationForm.medicine)
        })
      })

      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Allocation preview failed')

      setAllocation(data)
      setMessage('Allocation preview generated. No inventory has been deducted.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setAllocating(false)
    }
  }

  const approveAllocation = async () => {
    if (!allocation?.allocation_id) return

    if (!window.confirm('Approve this allocation and deduct the displayed stock?')) {
      return
    }

    try {
      const response = await fetch(
        `${API}/allocation/${allocation.allocation_id}/approve`,
        { method: 'POST' }
      )

      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Approval failed')

      setMessage('Allocation approved. Inventory has been deducted.')
      setAllocation(null)
      await loadData()
    } catch (error) {
      setMessage(error.message)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500'

  const cardClass =
    'rounded-2xl border border-slate-800 bg-[#101a2b] p-5'

  const Field = ({ label, value, onChange, type = 'text', required = true }) => (
    <label className="block">
      <span className="mb-2 block text-xs text-slate-400">{label}</span>
      <input
        className={inputClass}
        type={type}
        min={type === 'number' ? 0 : undefined}
        required={required}
        value={value}
        onChange={event => onChange(event.target.value)}
      />
    </label>
  )

  const NavButton = ({ name, icon: Icon }) => (
    <button
      onClick={() => setActiveTab(name)}
      className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm ${
        activeTab === name
          ? 'bg-cyan-500/10 text-cyan-400'
          : 'text-slate-400 hover:bg-slate-800'
      }`}
    >
      <Icon size={18} />
      {name}
    </button>
  )

  return (
    <div className="min-h-screen bg-[#080d18] text-slate-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-[#0c1422] p-5 lg:flex lg:flex-col">
          <div className="mb-10 flex items-center gap-3">
            <div className="rounded-xl bg-cyan-500/15 p-2.5 text-cyan-400">
              <Shield size={25} />
            </div>
            <div>
              <h1 className="text-xl font-bold">RESQNET INDIA</h1>
              <p className="text-[10px] tracking-[3px] text-slate-500">
                EMERGENCY RESPONSE
              </p>
            </div>
          </div>

          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">
            Workspace
          </p>

          <nav className="space-y-2">
            <NavButton name="Overview" icon={Activity} />
            <NavButton name="Incidents" icon={AlertTriangle} />
            <NavButton name="Warehouses" icon={Warehouse} />
            <NavButton name="Allocation" icon={Truck} />
          </nav>

          <div className="mt-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="mb-2 flex items-center gap-2 text-xs text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              {apiStatus}
            </div>
            <p className="text-xs text-slate-500">India disaster response prototype</p>
          </div>
        </aside>

        <main className="min-w-0 flex-1 p-5 md:p-8">
          <header className="mb-7 flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="mb-1 flex items-center gap-2 text-xs text-cyan-400">
                <Radio size={14} />
                INDIA EMERGENCY OPERATIONS CENTRE
              </div>
              <h2 className="text-2xl font-bold md:text-3xl">{activeTab}</h2>
              <p className="mt-1 text-sm text-slate-500">
                Disaster intelligence and relief coordination
              </p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={loadData}
                disabled={loading}
                className="flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800"
              >
                <RefreshCw size={14} />
                Refresh
              </button>
            </div>
          </header>

          {message && (
            <div className="mb-5 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 text-sm text-cyan-300">
              {message}
              <button className="float-right" onClick={() => setMessage('')}>×</button>
            </div>
          )}

          {activeTab === 'Overview' && (
            <>
              <section className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">

{[
  [
    incidentMode === 'historical' ? 'Historical Events' : 'Priority Alerts',
    incidentMode === 'historical' ? historicalIncidents.length : incidents.length,
    Activity
  ],
  [
    incidentMode === 'historical' ? 'Historical Red Events' : 'Red Alerts',
    (incidentMode === 'historical' ? historicalIncidents : incidents)
      .filter(x => x.severity === 'Red').length,
    AlertTriangle
  ],
  [
    incidentMode === 'historical' ? 'Historical Orange Events' : 'Orange Alerts',
    (incidentMode === 'historical' ? historicalIncidents : incidents)
      .filter(x => x.severity === 'Orange').length,
    Radio
  ],
  [
    'Registered Warehouses',
    warehouses.length,
    Warehouse
  ]
].map(([label, value, Icon]) => (

                  <div key={label} className={cardClass}>
                    <div className="mb-3 flex justify-between">
                      <p className="text-sm text-slate-400">{label}</p>
                      <Icon className="text-cyan-400" size={20} />
                    </div>
                    <h3 className="text-2xl font-bold">{value}</h3>
                    <p className="mt-2 text-xs text-slate-500">

{label === 'Registered Warehouses'
  ? 'Current operator-entered records'
  : incidentMode === 'historical'
    ? 'Historical GDACS records — last 60 days'
    : 'Current India GDACS feed'}

                    </p>
                  </div>
                ))}
              </section>

              <section className="mb-7 grid grid-cols-1 gap-5 xl:grid-cols-3">
                <div className={`${cardClass} xl:col-span-2`}>
                  <h3 className="mb-1 font-semibold">India Disaster Monitoring Map</h3>
                  <p className="mb-4 text-xs text-slate-500">
                    Current incident coordinates from GDACS
                  </p>

<div className="mb-3 flex flex-wrap items-center gap-2">
  {[
    ['live', 'Live Monitoring'],
    ['historical', 'Historical (60 days)']
  ].map(([mode, label]) => (
    <button
      key={mode}
      type="button"
      onClick={() => setIncidentMode(mode)}
      aria-pressed={incidentMode === mode}
      className={`rounded-lg px-4 py-2 text-xs font-semibold ${
        incidentMode === mode
          ? 'bg-cyan-600 text-white'
          : 'bg-slate-800 text-slate-300'
      }`}
    >
      {label}
    </button>
  ))}
</div>

{incidentMode === 'historical' && (
  <p className="mb-3 text-xs text-amber-400">
    Historical GDACS records — not active emergency alerts.
    {historyLoading && ' Loading records...'}
    {historyError && ` Error: ${historyError}`}
    {!historyLoading && !historyError &&
      ` ${historicalIncidents.length} events loaded.`}
  </p>
)}


<div className="mb-3 flex flex-wrap items-center gap-2">
  {['all', 'Red', 'Orange', 'Green'].map(level => (
    <button
      key={level}
      onClick={() => setIncidentFilter(level)}
      className={`rounded-lg px-3 py-2 text-xs font-medium ${
        incidentFilter === level
          ? 'bg-cyan-600 text-white'
          : 'bg-slate-800 text-slate-300'
      }`}
    >
      {level === 'all' ? 'All Disasters' : `${level} Alerts`}
    </button>
  ))}
</div>


<div className="mb-3 flex flex-wrap items-center gap-2">
  <button
    onClick={() => setWarehouseFilter('all')}
    className={`rounded-lg px-3 py-2 text-xs font-medium ${
      warehouseFilter === 'all'
        ? 'bg-blue-600 text-white'
        : 'bg-slate-800 text-slate-300'
    }`}
  >
    All Warehouses ({discoveredWarehouses.length})
  </button>

  <button
    onClick={() => setWarehouseFilter('named')}
    className={`rounded-lg px-3 py-2 text-xs font-medium ${
      warehouseFilter === 'named'
        ? 'bg-blue-600 text-white'
        : 'bg-slate-800 text-slate-300'
    }`}
  >
    Named Only ({
      discoveredWarehouses.filter(
        w => w.name && w.name !== 'Unnamed warehouse'
      ).length
    })
  </button>
</div>

                  <div className="h-80 overflow-hidden rounded-xl border border-slate-700">
                  <DisasterMap

incidents={
  (
    incidentMode === 'historical'
      ? historicalIncidents
      : allIncidents
  ).filter(
    incident =>
      incidentFilter === 'all' ||
      incident.severity === incidentFilter
  )
}

                   discoveredWarehouses={
                    warehouseFilter === 'named'
                      ? discoveredWarehouses.filter(
                          w => w.name && w.name !== 'Unnamed warehouse'
                        )
                      : discoveredWarehouses
                  }

                  onAnalyzeIncident={analyzeFromMap}
                  selectedRouteIncident={selectedRouteIncident}
                  selectedRouteWarehouse={selectedRouteWarehouse}
                  aiAnalyses={aiAnalyses}
                  analyzingId={analyzingId}

                  onSelectRouteIncident={recommendForIncident}
                  onSelectRouteWarehouse={setSelectedRouteWarehouse}
                  routeResult={routeResult}
                    />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    Map locations are source coordinates, not verified safe zones.
                  </p>
                </div>


<div className={cardClass}>
  <h3 className="mb-4 font-semibold">
    {incidentMode === 'historical'
      ? 'Historical Incidents'
      : 'Priority Incidents'}
  </h3>

  {incidentMode === 'historical' && (
    <p className="mb-3 text-xs text-amber-400">
      Historical GDACS records only. Not active emergency alerts.
    </p>
  )}

  <div className="space-y-4">
    {(incidentMode === 'historical'
      ? historicalIncidents
      : incidents).length === 0 && (
      <p className="text-sm text-slate-500">
        {incidentMode === 'historical'
          ? historyLoading
            ? 'Loading historical incidents...'
            : historyError || 'No historical incidents found.'

: liveFeedError || 'No current Red or Orange incidents returned by GDACS.'}

      </p>
    )}

    {(incidentMode === 'historical'
      ? historicalIncidents
      : incidents).map(incident => (

                      <div key={incident.id} className="border-b border-slate-800 pb-4 last:border-0">
                        <div className="flex justify-between gap-2">
                          <p className="text-sm font-medium">{incident.location}</p>
                          <span className={`h-fit rounded px-2 py-1 text-[10px] ${
                            incident.severity === 'Red'
                              ? 'bg-rose-500/10 text-rose-400'
                              : 'bg-amber-500/10 text-amber-400'
                          }`}>{incident.severity}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {incident.type} · {incident.time || 'Time unavailable'}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          Population impact: {incident.people ?? 'Not reported'}
                        </p>
                        {incident.source_url && (
                          <a href={incident.source_url} target="_blank" rel="noreferrer"
                            className="mt-2 inline-flex items-center gap-1 text-xs text-cyan-400">
                            GDACS report <ArrowUpRight size={12} />
                          </a>
                        )}
                        <button
                          onClick={() => analyzeIncident(incident.id)}
                          disabled={analyzingId === incident.id}
                          className="mt-3 w-full rounded-lg bg-cyan-600 px-3 py-2 text-xs font-semibold disabled:opacity-50"
                        >
                          {analyzingId === incident.id ? 'Analyzing...' : 'Generate AI Analysis'}
                        </button>
                        {aiAnalyses[incident.id] && (
                          <div className="mt-3 rounded-lg border border-cyan-500/20 bg-slate-900 p-3">
                            <p className="mb-2 text-xs font-semibold text-cyan-400">Gemini Analysis</p>
                            <p className="whitespace-pre-wrap text-xs leading-5 text-slate-300">
                              {aiAnalyses[incident.id]}
                            </p>
                            <p className="mt-3 text-[10px] text-amber-400">
                              Human verification required.
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </section>

{/* Disaster-to-warehouse route planning */}
{(selectedRouteIncident || selectedRouteWarehouse) && (
  <section className={`${cardClass} mb-7`}>
    <div className="mb-4">
      <h3 className="text-xl font-bold text-white">
        Disaster-to-Warehouse Route Planning
      </h3>
      <p className="mt-1 text-sm text-slate-400">
        Select a disaster and a warehouse from the map.
      </p>
    </div>

    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-rose-500/30 bg-slate-900 p-4">
        <p className="mb-2 text-sm font-semibold text-rose-400">
          Selected Disaster
        </p>
        {selectedRouteIncident ? (
          <>
            <p className="font-medium">
              {selectedRouteIncident.location}
            </p>
            <p className="mt-1 text-sm text-slate-400">
              {selectedRouteIncident.type} · {selectedRouteIncident.severity}
            </p>
            <button
              type="button"
              onClick={() => setSelectedRouteIncident(null)}
              className="mt-3 text-xs text-rose-400 hover:underline"
            >
              Clear selection
            </button>
          </>
        ) : (
          <p className="text-sm text-slate-500">
            No disaster selected.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-blue-500/30 bg-slate-900 p-4">
        <p className="mb-2 text-sm font-semibold text-blue-400">
          Selected Warehouse
        </p>
        {selectedRouteWarehouse ? (
          <>
            <p className="font-medium">
              {selectedRouteWarehouse.name || 'Unnamed warehouse'}
            </p>
            <p className="mt-1 text-sm text-amber-400">
              OSM location — unverified. Inventory unknown.
            </p>
            <button
              type="button"
              onClick={() => setSelectedRouteWarehouse(null)}
              className="mt-3 text-xs text-blue-400 hover:underline"
            >
              Clear selection
            </button>
          </>
        ) : (
          <p className="text-sm text-slate-500">
            No warehouse selected.
          </p>
        )}
      </div>
    </div>


{/* Automatic warehouse recommendations */}
{selectedRouteIncident && (
  <div className="mt-6">
    <h4 className="text-lg font-semibold text-white">
      Top Recommended Warehouse Locations
    </h4>

    <p className="mt-1 text-xs text-amber-400">
      Ranked by estimated road travel time.
      OSM locations are unverified and inventory is unknown.
    </p>

    {recommendationsLoading && (
      <p className="mt-3 text-sm text-cyan-400">
        Calculating warehouse routes...
      </p>
    )}

    {recommendationsError && (
      <p className="mt-3 text-sm text-rose-400" role="alert">
        {recommendationsError}
      </p>
    )}

    {!recommendationsLoading &&
      !recommendationsError &&
      recommendedWarehouses.length === 0 && (
        <p className="mt-3 text-sm text-slate-400">
          No warehouse recommendations available.
        </p>
      )}

    <div className="mt-4 space-y-3">
      {recommendedWarehouses.slice(0, 5).map((warehouse, index) => (
        <div
          key={warehouse.id ?? index}
          className="rounded-xl border border-slate-700 bg-slate-900 p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-white">
                #{index + 1} {warehouse.name || 'Unnamed warehouse'}
              </p>

              <p className="mt-1 text-sm text-slate-300">
                Road distance:{' '}
                {warehouse.road_distance_km != null
                  ? `${warehouse.road_distance_km} km`
                  : 'Unavailable'}
              </p>

              <p className="text-sm text-slate-300">
                Estimated drive time:{' '}
                {warehouse.estimated_drive_minutes != null
                  ? `${warehouse.estimated_drive_minutes} min`
                  : 'Unavailable'}
              </p>

              <p className="mt-1 text-xs text-amber-400">
                Unverified location · Inventory unknown
              </p>
            </div>

            <button
              type="button"
              disabled={!warehouse.road_reachable}
              onClick={() => setSelectedRouteWarehouse(warehouse)}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {selectedRouteWarehouse?.id === warehouse.id
                ? 'Selected'
                : warehouse.road_reachable
                  ? 'Select Location'
                  : 'No Road Route'}
            </button>
          </div>
        </div>
      ))}
    </div>
  </div>
)}


{/* Registered warehouse inventory recommendations */}
{selectedRouteIncident && (
  <div className="mt-6 rounded-xl border border-cyan-500/30 bg-slate-900 p-5">
    <h4 className="text-lg font-semibold text-white">
      Inventory-Aware Warehouse Recommendations
    </h4>

    <p className="mt-2 text-xs text-amber-400">
      Uses operator-recorded inventory and estimated driving times.
      Stock and road safety are not independently verified.
    </p>

    <div className="mt-4 grid gap-4 sm:grid-cols-3">
      {['food', 'water', 'medicine'].map(key => (
        <label key={key} className="block text-sm text-slate-300">
          <span className="mb-2 block capitalize">{key}</span>
          <input
            type="number"
            min="0"
            step="1"
            value={registeredRequirements[key]}
            onChange={e =>
              setRegisteredRequirements(previous => ({
                ...previous,
                [key]: e.target.value
              }))
            }
            className="w-full rounded-lg border border-slate-600 bg-slate-800 p-3 text-white"
            placeholder="0"
          />
        </label>
      ))}
    </div>

    <button
      type="button"
      disabled={registeredRecommendationsLoading}
      onClick={() =>
        recommendRegisteredForIncident(selectedRouteIncident)
      }
      className="mt-4 rounded-lg bg-cyan-600 px-5 py-3 font-semibold text-white disabled:opacity-50"
    >
      {registeredRecommendationsLoading
        ? 'Checking inventory and routes...'
        : 'Find Stock-Aware Warehouses'}
    </button>

    {registeredRecommendationsError && (
      <p className="mt-3 text-sm text-rose-400" role="alert">
        {registeredRecommendationsError}
      </p>
    )}

{/* Registered warehouse recommendation results */}
<div className="mt-5 space-y-3">
  {registeredRecommendations.map((warehouse, index) => (
    <div
      key={warehouse.id}
      className="rounded-xl border border-slate-700 bg-slate-800 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h5 className="font-semibold text-white">
          #{index + 1} {warehouse.name}
        </h5>

        <span className={`rounded-lg px-3 py-1 text-xs font-semibold ${
          warehouse.stock_status === 'full'
            ? 'bg-green-500/20 text-green-400'
            : warehouse.stock_status === 'partial'
              ? 'bg-amber-500/20 text-amber-400'
              : 'bg-red-500/20 text-red-400'
        }`}>
          {warehouse.stock_status === 'full'
            ? 'Full Stock Coverage'
            : warehouse.stock_status === 'partial'
              ? 'Partial Stock Coverage'
              : 'Insufficient Stock'}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs text-slate-400">
            Recorded Supply Coverage
          </p>
          <p className="text-xl font-bold text-cyan-400">
            {warehouse.coverage_percent}%
          </p>
        </div>

        <div>
          <p className="text-xs text-slate-400">
            Estimated Driving Time
          </p>
          <p className="text-xl font-bold text-white">
            {warehouse.estimated_drive_minutes != null
              ? `${warehouse.estimated_drive_minutes} min`
              : 'Unavailable'}
          </p>
        </div>

        <div>
          <p className="text-xs text-slate-400">
            Road Distance
          </p>
          <p className="font-semibold text-white">
            {warehouse.road_distance_km != null
              ? `${warehouse.road_distance_km} km`
              : 'Unavailable'}
          </p>
        </div>

        <div>
          <p className="text-xs text-slate-400">
            Modeled Road Reachability
          </p>
          <p className="font-semibold text-white">
            {warehouse.road_reachable
              ? 'Route found'
              : 'No route found'}
          </p>
        </div>
      </div>

      <div className="mt-4 border-t border-slate-700 pt-3">
        <p className="mb-2 text-sm font-semibold text-white">
          Supply Shortages
        </p>

        {['food', 'water', 'medicine'].map(key => (
          <p key={key} className="text-sm text-slate-300">
            <span className="capitalize">{key}:</span>{' '}
            <span className={
              warehouse.shortages?.[key] > 0
                ? 'text-rose-400'
                : 'text-green-400'
            }>
              {warehouse.shortages?.[key] ?? 'Unknown'}
            </span>
          </p>
        ))}
      </div>

      <p className="mt-3 text-xs text-amber-400">
        Operator-recorded stock, not independently verified.
        Routing estimates do not confirm road safety.
      </p>
    </div>
  ))}
</div>

  </div>
)}


{selectedRouteIncident && selectedRouteWarehouse && (
  <div className="mt-5 rounded-xl border border-cyan-500/30 bg-slate-900 p-5">
    <h4 className="mb-4 text-lg font-semibold text-white">
      Driving Route Details
    </h4>

    {routeLoading && (
      <p className="text-sm text-cyan-400">
        Calculating the driving route...
      </p>
    )}

    {routeError && (
      <p className="text-sm text-rose-400" role="alert">
        Route unavailable: {routeError}
      </p>
    )}

    {!routeLoading && !routeError && !routeResult && (
      <p className="text-sm text-slate-400">
        Waiting for route information.
      </p>
    )}

    {routeResult && !routeLoading && !routeError && (
      <>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg bg-slate-800 p-4">
            <p className="text-xs text-slate-400">Road Distance</p>
            <p className="mt-2 text-2xl font-bold text-cyan-400">
              {routeResult.distance_km} km
            </p>
          </div>

          <div className="rounded-lg bg-slate-800 p-4">
            <p className="text-xs text-slate-400">
              Estimated Driving Time
            </p>
            <p className="mt-2 text-2xl font-bold text-white">
              {routeResult.duration_minutes} min
            </p>
          </div>

          <div className="rounded-lg bg-slate-800 p-4">
            <p className="text-xs text-slate-400">Routing Status</p>
            <p className="mt-2 text-sm font-semibold text-emerald-400">
              Road route calculated
            </p>
          </div>
        </div>

        <p className="mt-4 text-xs text-slate-400">
          Source: {routeResult.provider || 'Routing service'}
        </p>

        <p className="mt-2 text-xs text-amber-400">
          {routeResult.warning}
        </p>

        {incidentMode === 'historical' && (
          <p className="mt-2 text-xs font-semibold text-amber-400">
            Historical disaster simulation only. Not an active dispatch.
          </p>
        )}
      </>
    )}
  </div>
)}


    <p className="mt-3 text-xs text-amber-400">
    Driving distances and times are estimated using OSRM. Road safety and accessibility are not independently verified. Historical incidents are demonstration scenarios. Viewing recommendations does not reserve, deduct, or dispatch supplies.
    </p>
  </section>
)}

              {selectedAnalysisId && aiAnalyses[selectedAnalysisId] && (
                <section
                  id="gemini-analysis-panel"
                  className={`${cardClass} mb-7 scroll-mt-6`}
                >
                  <h3 className="mb-2 text-xl font-bold text-white">
                    Gemini Disaster Intelligence Analysis
                  </h3>

                  <p className="mb-4 text-sm text-slate-400">
                    Incident ID: {selectedAnalysisId}
                  </p>

                  <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
                    <div className="max-h-[550px] overflow-y-auto">
                      <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-200">
                        {aiAnalyses[selectedAnalysisId]}
                      </p>
                    </div>
                  </div>

                  <p className="mt-4 text-sm text-amber-400">
                    AI-generated assessment. Human verification required.
                    Do not use as the sole basis for emergency decisions.
                  </p>
                </section>
              )}

              <div className={cardClass}>
                <h3 className="mb-3 font-semibold">RESQNET Coordination Status</h3>
                <div className="grid gap-3 sm:grid-cols-3">
                  <p className="text-xs text-emerald-400"><CheckCircle2 className="mr-1 inline" size={14}/> GDACS incident feed</p>
                  <p className="text-xs text-emerald-400"><CheckCircle2 className="mr-1 inline" size={14}/> Gemini analysis endpoint</p>
                  <p className="text-xs text-cyan-400"><Clock className="mr-1 inline" size={14}/> Human-approved allocation workflow</p>
                </div>
              </div>
            </>
          )}

          {activeTab === 'Incidents' && (
            <section className={cardClass}>
              <h3 className="mb-4 font-semibold">India Priority Incident Feed</h3>
              {incidents.length === 0 && <p className="text-sm text-slate-500">No priority incidents currently available.</p>}
              <div className="space-y-3">
                {incidents.map(item => (
                  <div key={item.id} className="rounded-xl border border-slate-800 p-4">
                    <div className="flex flex-wrap justify-between gap-2">
                      <p className="font-medium">{item.location}</p>
                      <span className="text-xs text-cyan-400">{item.severity}</span>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {item.type} · {item.time} · {item.latitude}, {item.longitude}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Population impact: {item.people ?? 'Not reported'}
                    </p>
                    {item.source_url && <a className="mt-2 inline-block text-xs text-cyan-400" href={item.source_url} target="_blank" rel="noreferrer">Official GDACS report ↗</a>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {activeTab === 'Warehouses' && (
            <>
              <section className={`${cardClass} mb-6`}>
                <h3 className="mb-2 font-semibold">Register Relief Warehouse</h3>
                <p className="mb-5 text-xs text-amber-400">
                  Enter actual stock figures supplied by an authorised operator.
                </p>

                <form onSubmit={registerWarehouse} className="grid gap-4 md:grid-cols-2">
                  <Field label="Warehouse name" value={warehouseForm.name} onChange={v => updateWarehouseForm('name', v)} />
                  <Field label="Operator / verifier name" value={warehouseForm.verified_by} onChange={v => updateWarehouseForm('verified_by', v)} />
                  <Field label="State" value={warehouseForm.state} onChange={v => updateWarehouseForm('state', v)} />
                  <Field label="District" value={warehouseForm.district} onChange={v => updateWarehouseForm('district', v)} />
                  <Field label="Latitude (optional)" type="number" required={false} value={warehouseForm.latitude} onChange={v => updateWarehouseForm('latitude', v)} />
                  <Field label="Longitude (optional)" type="number" required={false} value={warehouseForm.longitude} onChange={v => updateWarehouseForm('longitude', v)} />
                  <Field label="Food packages (units)" type="number" value={warehouseForm.food} onChange={v => updateWarehouseForm('food', v)} />
                  <Field label="Water (litres)" type="number" value={warehouseForm.water} onChange={v => updateWarehouseForm('water', v)} />
                  <Field label="Medical kits (units)" type="number" value={warehouseForm.medicine} onChange={v => updateWarehouseForm('medicine', v)} />
                  <div className="flex items-end">
                    <button className="w-full rounded-lg bg-cyan-600 px-4 py-3 text-sm font-semibold hover:bg-cyan-500">
                      Register Warehouse
                    </button>
                  </div>
                </form>
              </section>

              <section className={cardClass}>
                <h3 className="mb-4 font-semibold">Registered Warehouse Inventory</h3>
                <p className="mb-4 text-xs text-slate-500">
                  Operator-entered stock. RESQNET has not independently verified these quantities.
                </p>
                {warehouses.length === 0 && (
                  <p className="text-sm text-slate-500">No warehouses registered yet. Add one above.</p>
                )}
                <div className="space-y-3">
                  {warehouses.map(warehouse => (
                    <div key={warehouse.id} className="rounded-xl border border-slate-800 p-4">
                      <div className="flex flex-wrap justify-between gap-2">
                        <div>
                          <h4 className="font-medium">{warehouse.name}</h4>
                          <p className="mt-1 text-xs text-slate-500">
                            {warehouse.district}, {warehouse.state}
                          </p>
                          <p className="mt-1 text-[10px] text-slate-500">
                            Operator: {warehouse.verified_by}
                          </p>
                        </div>
                        <button onClick={() => updateStock(warehouse)}
                          className="h-fit rounded-lg border border-cyan-500/30 px-3 py-2 text-xs text-cyan-400">
                          Update stock
                        </button>
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        <div className="rounded-lg bg-slate-900 p-3">
                          <Package size={16} className="mb-2 text-cyan-400"/>
                          <p className="text-lg font-bold">{warehouse.food}</p>
                          <p className="text-[10px] text-slate-500">Food units</p>
                        </div>
                        <div className="rounded-lg bg-slate-900 p-3">
                          <Droplets size={16} className="mb-2 text-cyan-400"/>
                          <p className="text-lg font-bold">{warehouse.water}</p>
                          <p className="text-[10px] text-slate-500">Water litres</p>
                        </div>
                        <div className="rounded-lg bg-slate-900 p-3">
                          <HeartPulse size={16} className="mb-2 text-cyan-400"/>
                          <p className="text-lg font-bold">{warehouse.medicine}</p>
                          <p className="text-[10px] text-slate-500">Medical kits</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}

          {activeTab === 'Allocation' && (
            <>
              <section className={`${cardClass} mb-6`}>
                <h3 className="mb-2 font-semibold">Relief Resource Allocation</h3>
                <p className="mb-5 text-xs text-slate-400">
                  Select a live incident, warehouse and requested quantities to calculate an allocation preview.
                </p>

                <form onSubmit={previewAllocation} className="grid gap-4 md:grid-cols-2">
                  <label>
                    <span className="mb-2 block text-xs text-slate-400">Live India incident</span>
                    <select required className={inputClass}
                      value={allocationForm.incident_id}
                      onChange={e => updateAllocationForm('incident_id', e.target.value)}>
                      <option value="">Select incident</option>
                      {incidents.map(item => (
                        <option key={item.id} value={item.id}>
                          {item.location} — {item.severity}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    <span className="mb-2 block text-xs text-slate-400">Warehouse</span>
                    <select required className={inputClass}
                      value={allocationForm.warehouse_id}
                      onChange={e => updateAllocationForm('warehouse_id', e.target.value)}>
                      <option value="">Select warehouse</option>
                      {warehouses.map(item => (
                        <option key={item.id} value={item.id}>
                          {item.name} — {item.district}, {item.state}
                        </option>
                      ))}
                    </select>
                  </label>

                  <Field label="Requested food packages" type="number" value={allocationForm.food}
                    onChange={v => updateAllocationForm('food', v)} />
                  <Field label="Requested water (litres)" type="number" value={allocationForm.water}
                    onChange={v => updateAllocationForm('water', v)} />
                  <Field label="Requested medical kits" type="number" value={allocationForm.medicine}
                    onChange={v => updateAllocationForm('medicine', v)} />

                  <div className="flex items-end">
                    <button disabled={allocating || incidents.length === 0 || warehouses.length === 0}
                      className="w-full rounded-lg bg-cyan-600 px-4 py-3 text-sm font-semibold disabled:opacity-40">
                      {allocating ? 'Calculating...' : 'Generate Allocation Preview'}
                    </button>
                  </div>
                </form>
              </section>

              {allocation && (
                <section className={cardClass}>
                  <div className="mb-4 flex flex-wrap justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">Allocation Preview</h3>
                      <p className="mt-1 text-xs text-slate-500">
                        {allocation.incident.location} · {allocation.warehouse}
                      </p>
                    </div>
                    <span className="h-fit rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                      Pending approval
                    </span>
                  </div>

                  <p className="mb-4 text-xs text-slate-400">
                    Requested quantities are operator-supplied, not automatically verified disaster requirements.
                  </p>

                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      ['Food', 'food', 'units'],
                      ['Water', 'water', 'litres'],
                      ['Medical kits', 'medicine', 'units']
                    ].map(([label, key, unit]) => (
                      <div key={key} className="rounded-xl bg-slate-900 p-4">
                        <p className="text-xs text-slate-400">{label}</p>
                        <p className="mt-2 text-xl font-bold text-emerald-400">
                          {allocation.proposed_allocation[key]}
                        </p>
                        <p className="text-[10px] text-slate-500">Allocated · {unit}</p>
                        <p className="mt-3 text-xs text-rose-400">
                          Shortage: {allocation.shortages[key]}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                    <p className="text-sm font-medium text-amber-300">Human approval required</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Previewing does not deduct stock. Approval below will deduct the proposed quantities from this warehouse.
                    </p>
                  </div>

                  <button onClick={approveAllocation}
                    className="mt-4 w-full rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold hover:bg-emerald-500">
                    Approve Allocation & Deduct Stock
                  </button>
                </section>
              )}
            </>
          )}

          <footer className="mt-8 border-t border-slate-800 pt-5 text-center text-xs text-slate-600">
            RESQNET INDIA · Disaster Intelligence & Relief Coordination · Prototype v2.0
          </footer>
        </main>
      </div>
    </div>
  )
}

export default App
