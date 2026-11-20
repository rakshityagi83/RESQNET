import AllocationAuditDetails from './AllocationAuditDetails.jsx'
import { downloadAllocationCsv } from '../utils/allocationCsv.js'
import { useEffect, useState } from 'react'

import {
  History,
  Download,
  Search,
  RefreshCw,
  Package,
  Droplets,
  HeartPulse,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronLeft,
  ChevronRight
} from 'lucide-react'

import { useAuth } from '../auth/AuthContext.jsx'
import {
  authClient,
  AuthApiError
} from '../services/authClient.js'

const PAGE_SIZE = 20

const resources = [
  ['Food packages', 'food', Package],
  ['Water litres', 'water', Droplets],
  ['Medical kits', 'medicine', HeartPulse]
]

const statuses = [
  ['ALL', 'All'],
  ['PENDING', 'Pending'],
  ['APPROVED', 'Approved'],
  ['REJECTED', 'Rejected']
]

const statusStyles = {
  PENDING: {
    label: 'Pending',
    color: 'text-amber-400 bg-amber-500/10',
    icon: Clock,
    note: 'Awaiting review. Inventory not deducted.'
  },
  APPROVED: {
    label: 'Approved',
    color: 'text-emerald-400 bg-emerald-500/10',
    icon: CheckCircle2,
    note: 'Allocation approved and inventory deducted.'
  },
  REJECTED: {
    label: 'Rejected',
    color: 'text-rose-400 bg-rose-500/10',
    icon: XCircle,
    note: 'Allocation rejected. No inventory deducted.'
  }
}

export default function AllocationHistory({
  refreshVersion = 0
}) {
  const { isAdmin, recoverSession } = useAuth()

  const [draft, setDraft] = useState('')
  const [filters, setFilters] = useState({
    status: 'ALL',
    q: '',
    offset: 0,
    revision: 0
  })

  const [records, setRecords] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isAdmin) return

    const controller = new AbortController()

    async function loadHistory() {
      setLoading(true)
      setError('')
      setRecords([])
      setHasMore(false)

      try {
        const data = await authClient.listAllocationHistory({
          limit: PAGE_SIZE,
          offset: filters.offset,
          status: filters.status,
          q: filters.q,
          signal: controller.signal
        })

        if (controller.signal.aborted) return

        setRecords(data.allocations)
        setHasMore(data.has_more)
      } catch (error) {
        if (controller.signal.aborted) return

        setError(
          error instanceof AuthApiError
            ? error.message
            : 'Unable to retrieve allocation history.'
        )

        if (
          error instanceof AuthApiError &&
          error.status === 401
        ) {
          await recoverSession()
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    loadHistory()

    return () => controller.abort()

  }, [isAdmin, filters, refreshVersion, recoverSession])

  function updateFilters(changes) {
    setLoading(true)

    setFilters(previous => ({
      ...previous,
      ...changes,
      revision: previous.revision + 1
    }))
  }

  function searchHistory(event) {
    event.preventDefault()

    updateFilters({
      q: draft.trim(),
      offset: 0
    })
  }

  if (!isAdmin) return null

  return (
    <section className="mb-6 rounded-2xl border border-slate-800 bg-[#101a2b] p-5">

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold">
            <History size={20} className="text-cyan-400" />
            Allocation History
          </h3>

          <p className="mt-2 text-xs text-slate-400">
            Persistent records of relief allocation decisions.
          </p>
        </div>

        <button
          type="button"
          disabled={loading}
          onClick={() => updateFilters({ offset: 0 })}
          className="flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          <RefreshCw
            size={14}
            className={loading ? 'animate-spin' : ''}
          />
          Refresh history
        </button>
      </div>

      <form
        onSubmit={searchHistory}
        className="mb-4 flex flex-wrap gap-2"
      >
        <input
          type="search"
          aria-label="Search allocation history"
          placeholder="Incident, warehouse or request ID"
          value={draft}
          maxLength={150}
          onChange={event => setDraft(event.target.value)}
          className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
        />

        <button
          type="submit"
          className="flex items-center gap-2 rounded-xl bg-cyan-500/10 px-4 py-2 text-sm text-cyan-400 hover:bg-cyan-500/20"
        >
          <Search size={16} />
          Search
        </button>

        <button
          type="button"
          onClick={() => {
            setDraft('')
            updateFilters({
              q: '',
              status: 'ALL',
              offset: 0
            })
          }}
          className="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-400"
        >
          Clear
        </button>
      </form>

      <div className="mb-5 flex flex-wrap gap-2">
        {statuses.map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filters.status === value}
            onClick={() => updateFilters({
              status: value,
              offset: 0
            })}
            className={
              'rounded-lg px-4 py-2 text-xs font-medium ' +
              (filters.status === value
                ? 'bg-cyan-500/15 text-cyan-400'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200')
            }
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          Export records from the current filtered page.
        </p>

        <button
          type="button"
          disabled={loading || Boolean(error) || records.length === 0}
          onClick={() => {
            try {
              downloadAllocationCsv(records)
            } catch {
              setError('Unable to export allocation records.')
            }
          }}
          className="flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-cyan-500/5 px-4 py-2 text-xs font-medium text-cyan-400 hover:bg-cyan-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Download size={16} />
          Export CSV
        </button>
      </div>

      {filters.q && (
        <p className="mb-3 break-all text-xs text-slate-400">
          Searching for: {filters.q}
        </p>
      )}

      {loading && (
        <p role="status" className="py-4 text-sm text-slate-400">
          Retrieving allocation history...
        </p>
      )}

      {!loading && error && (
        <p
          role="alert"
          className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-sm text-rose-400"
        >
          {error}
        </p>
      )}

      {!loading && !error && records.length === 0 && (
        <div className="rounded-xl border border-slate-800 p-8 text-center">
          <History size={26} className="mx-auto mb-3 text-slate-500" />
          <p className="text-sm text-slate-300">
            No matching allocation records.
          </p>
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-4">
          {records.length > 0 && (
            <p className="text-xs text-slate-400">
              Showing records {filters.offset + 1} to {filters.offset + records.length}
            </p>
          )}

          {records.map(record => {
            const style = statusStyles[record.status]
            const StatusIcon = style.icon

            return (
              <article
                key={record.allocation_id}
                className="rounded-xl border border-slate-700 bg-slate-950/30 p-4"
              >
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 className="font-semibold text-slate-100">
                      {record.incident_id}
                    </h4>

                    <p className="mt-1 text-sm text-slate-400">
                      {record.warehouse || 'Warehouse unavailable'}
                    </p>

                    <p className="mt-2 break-all text-xs text-slate-500">
                      Request ID: {record.allocation_id}
                    </p>

                    {record.created_at && (
                      <p className="mt-2 text-xs text-slate-500">
                        Created: {record.created_at.replace('T', ' ')}
                      </p>
                    )}
                  </div>

                  <span className={
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-xs ' +
                    style.color
                  }>
                    <StatusIcon size={15} />
                    {style.label}
                  </span>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  {resources.map(([label, key, Icon]) => (
                    <div
                      key={key}
                      className="rounded-xl bg-slate-900 p-4"
                    >
                      <Icon size={18} className="mb-2 text-cyan-400" />

                      <p className="text-xs text-slate-400">
                        {label}
                      </p>

                      <p className="mt-1 text-2xl font-bold text-slate-100">
                        {record.proposed_allocation[key].toLocaleString()}
                      </p>

                      <p className="text-xs text-slate-500">
                        {record.status === 'APPROVED'
                          ? 'Approved quantity'
                          : 'Proposed quantity'}
                      </p>

                      <p className="mt-2 text-xs text-slate-400">
                        Requested: {record.requested[key].toLocaleString()}
                      </p>

                      <p className={
                        'mt-1 text-xs ' +
                        (record.shortages[key] > 0
                          ? 'text-rose-400'
                          : 'text-slate-400')
                      }>
                        Preview shortage: {record.shortages[key].toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>

                <p className={
                  'mt-4 rounded-lg p-3 text-xs ' +
                  style.color
                }>
                  {style.note}
                </p>
                <AllocationAuditDetails record={record} />
            </article>
            )
          })}

          {(filters.offset > 0 || hasMore) && (
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={filters.offset === 0}
                onClick={() => updateFilters({
                  offset: Math.max(0, filters.offset - PAGE_SIZE)
                })}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-2 text-xs disabled:opacity-40"
              >
                <ChevronLeft size={15} />
                Previous
              </button>

              <button
                type="button"
                disabled={!hasMore}
                onClick={() => updateFilters({
                  offset: filters.offset + PAGE_SIZE
                })}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-2 text-xs disabled:opacity-40"
              >
                Next
                <ChevronRight size={15} />
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
