
import { useState, useEffect } from 'react'
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
  const [warehouses, setWarehouses] = useState([])
  const [apiStatus, setApiStatus] = useState('Connecting...')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [aiAnalyses, setAiAnalyses] = useState({})
  const [analyzingId, setAnalyzingId] = useState(null)
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

    try {
      const [incidentResponse, warehouseResponse] = await Promise.all([
        fetch(`${API}/priority-incidents`),
        fetch(`${API}/warehouses`)
      ])

      if (!incidentResponse.ok) throw new Error('India incident feed unavailable')
      if (!warehouseResponse.ok) throw new Error('Warehouse data unavailable')

      const incidentData = await incidentResponse.json()
      const warehouseData = await warehouseResponse.json()

      setIncidents(incidentData.incidents || [])
      setWarehouses(warehouseData)
      setApiStatus('Connected')

      if (
        allocationForm.incident_id &&
        !(incidentData.incidents || []).some(
          item => item.id === allocationForm.incident_id
        )
      ) {
        setAllocationForm(previous => ({ ...previous, incident_id: '' }))
        setAllocation(null)
      }
    } catch (error) {
      setApiStatus('Disconnected')
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

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
                  ['Priority Alerts', incidents.length, Activity],
                  ['Red Alerts', incidents.filter(x => x.severity === 'Red').length, AlertTriangle],
                  ['Orange Alerts', incidents.filter(x => x.severity === 'Orange').length, Radio],
                  ['Registered Warehouses', warehouses.length, Warehouse]
                ].map(([label, value, Icon]) => (
                  <div key={label} className={cardClass}>
                    <div className="mb-3 flex justify-between">
                      <p className="text-sm text-slate-400">{label}</p>
                      <Icon className="text-cyan-400" size={20} />
                    </div>
                    <h3 className="text-2xl font-bold">{value}</h3>
                    <p className="mt-2 text-xs text-slate-500">
                      {label === 'Priority Alerts' ? 'Live India GDACS records' :
                        label === 'Registered Warehouses' ? 'Operator-entered records' : 'Current GDACS feed'}
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
                  <div className="h-80 overflow-hidden rounded-xl border border-slate-700">
                    <DisasterMap incidents={incidents} />
                  </div>
                  <p className="mt-3 text-xs text-slate-500">
                    Map locations are source coordinates, not verified safe zones.
                  </p>
                </div>

                <div className={cardClass}>
                  <h3 className="mb-4 font-semibold">Priority Incidents</h3>
                  <div className="space-y-4">
                    {incidents.length === 0 && (
                      <p className="text-sm text-slate-500">No current Red or Orange incidents returned by GDACS.</p>
                    )}
                    {incidents.map(incident => (
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
