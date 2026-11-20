import AllocationAuditDetails from './AllocationAuditDetails.jsx'
import { validateRejectionReason } from '../utils/rejectionReason.js'
import AllocationHistory from './AllocationHistory.jsx'
import { useState, useEffect, useRef } from 'react'

import {
  ClipboardList,
  RefreshCw,
  Clock,
  Package,
  Droplets,
  HeartPulse,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  XCircle
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

export default function PendingAllocationQueue({ onApproved }) {
  const {
    isAdmin,
    recoverSession,
    csrfToken,
    busy: authBusy
  } = useAuth()

  const approvalLock = useRef(false)

  const [rejectionDraft, setRejectionDraft] = useState(null)

  const reasonValidation = validateRejectionReason(
    rejectionDraft?.reason ?? ''
  )
  const [approvingId, setApprovingId] = useState(null)
  const [approvalError, setApprovalError] = useState('')
  const [approvalMessage, setApprovalMessage] = useState('')

  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!isAdmin) return

    const controller = new AbortController()

    async function loadQueue() {
      setLoading(true)
      setError('')
      setRecords([])
      setHasMore(false)

      try {
        const data = await authClient.listPendingAllocations({
          limit: PAGE_SIZE,
          offset,
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
            : 'Unable to retrieve pending allocations.'
        )

        if (
          error instanceof AuthApiError &&
          [401, 403].includes(error.status)
        ) {
          await recoverSession()
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    loadQueue()

    return () => controller.abort()
  }, [isAdmin, offset, revision, recoverSession])

  if (!isAdmin) return null

  async function decideRequest(record, action, reason = '') {
    if (
      !isAdmin ||
      authBusy ||
      !csrfToken ||
      approvalLock.current ||
      !['approve', 'reject'].includes(action)
    ) return

    const rejecting = action === 'reject'

    const validation = validateRejectionReason(reason)

    if (rejecting && !validation.valid) {
      setApprovalError(
        'Enter a valid rejection reason of 10-500 characters.'
      )
      return
    }

    if (!rejecting) {
      const confirmed = window.confirm(
        'Approve allocation for ' + record.incident_id +
        '?\n\nWarehouse: ' + record.warehouse +
        '\nFood: ' + record.proposed_allocation.food +
        '\nWater: ' + record.proposed_allocation.water +
        '\nMedical kits: ' + record.proposed_allocation.medicine +
        '\n\nApproval will deduct these quantities from inventory.'
      )

      if (!confirmed) return
    }

    approvalLock.current = true
    setApprovingId(record.allocation_id)
    setApprovalError('')
    setApprovalMessage('')

    try {
      await authClient.protectedWrite(
        '/allocation/' + record.allocation_id + '/' + action,
        'POST',
        rejecting
          ? { reason: validation.reason }
          : undefined,
        csrfToken
      )

      setRejectionDraft(null)

      setApprovalMessage(
        (rejecting
          ? 'Allocation rejected. Inventory unchanged.'
          : 'Allocation approved successfully.') +
        ' Request ID: ' + record.allocation_id
      )

      refreshQueue()

      if (!rejecting && onApproved) {
        try {
          await onApproved()
        } catch {
          setApprovalMessage(
            'Allocation approved. Refresh warehouse inventory.'
          )
        }
      }
    } catch (error) {
      setApprovalError(
        (error instanceof AuthApiError
          ? error.message
          : 'Unable to confirm allocation decision.') +
        ' Refresh the queue and inventory before retrying.'
      )

      if (
        error instanceof AuthApiError &&
        [401, 403].includes(error.status)
      ) {
        await recoverSession()
      }

      refreshQueue()
    } finally {
      approvalLock.current = false
      setApprovingId(null)
    }
  }

  function refreshQueue() {
    setRejectionDraft(null)
    setLoading(true)
    setOffset(0)
    setRevision(previous => previous + 1)
  }

  function changePage(nextOffset) {
    setRejectionDraft(null)
    setLoading(true)
    setOffset(nextOffset)
  }

  return (
    <>
    <section className="mb-6 rounded-2xl border border-slate-800 bg-[#101a2b] p-5">

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold">
            <ClipboardList size={20} className="text-cyan-400" />
            Pending Allocation Approvals
          </h3>

          <p className="mt-2 text-xs text-slate-400">
            Review persisted relief requests submitted by authorized personnel.
          </p>

          <p className="mt-2 flex items-center gap-2 text-xs text-cyan-400">
            <ShieldCheck size={14} />
            Administrator workspace
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setRejectionDraft(null)
            refreshQueue()
          }}
          disabled={loading || Boolean(approvingId)}
          className="flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          <RefreshCw
            size={14}
            className={loading ? 'animate-spin' : ''}
          />
          Refresh queue
        </button>
      </div>

      {approvalMessage && (
        <p role="status" className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-400">
          {approvalMessage}
        </p>
      )}

      {approvalError && (
        <p role="alert" className="mb-4 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-400">
          {approvalError}
        </p>
      )}

      {loading && (
        <p role="status" className="py-4 text-sm text-slate-400">
          Retrieving pending allocations...
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
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center">
          <ClipboardList
            size={25}
            className="mx-auto mb-3 text-slate-500"
          />

          <p className="text-sm text-slate-300">
            No pending allocations on this page.
          </p>

          <p className="mt-2 text-xs text-slate-500">
            Submitted requests will appear here.
          </p>
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-4">

          {records.length > 0 && (
            <p className="text-xs text-slate-400">
              Showing requests {offset + 1} to {offset + records.length}
            </p>
          )}

          {records.map(record => (
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
                      Recorded: {record.created_at.replace('T', ' ')}
                    </p>
                  )}
                </div>

                <span className="flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                  <Clock size={14} />
                  Pending approval
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

                    <p className="mt-1 text-2xl font-bold text-emerald-400">
                      {record.proposed_allocation[key].toLocaleString()}
                    </p>

                    <p className="mt-2 text-xs text-slate-400">
                      Requested: {record.requested[key].toLocaleString()}
                    </p>

                    <p className="mt-1 text-xs text-rose-400">
                      Shortage: {record.shortages[key].toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <p className="text-xs text-amber-300">
                  Awaiting administrator review.
                  Proposed quantities do not reserve or deduct inventory.
                </p>
              </div>
              <AllocationAuditDetails record={record} />

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  disabled={
                    Boolean(approvingId) ||
                    Boolean(rejectionDraft) ||
                    authBusy ||
                    !csrfToken ||
                    !record.warehouse
                  }
                  onClick={() => decideRequest(record, 'approve')}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ShieldCheck size={18} />
                  Approve Allocation
                </button>

                <button
                  type="button"
                  disabled={
                    Boolean(approvingId) ||
                    Boolean(rejectionDraft) ||
                    authBusy ||
                    !csrfToken
                  }
                  onClick={() => {
                    setApprovalError('')
                    setRejectionDraft({
                      id: record.allocation_id,
                      reason: ''
                    })
                  }}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-rose-500/40 bg-rose-500/5 px-4 py-3 text-sm font-semibold text-rose-400 hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <XCircle size={18} />
                  Reject Allocation
                </button>

                {approvingId === record.allocation_id && (
                  <p
                    role="status"
                    className="text-xs text-slate-400 sm:col-span-2"
                  >
                    Processing allocation decision...
                  </p>
                )}
              </div>
              {rejectionDraft?.id === record.allocation_id && (
                <form
                  onSubmit={event => {
                    event.preventDefault()

                    if (!reasonValidation.valid) return

                    decideRequest(
                      record,
                      'reject',
                      rejectionDraft.reason
                    )
                  }}
                  className="mt-4 space-y-3 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4"
                >
                  <h5 className="text-sm font-semibold text-rose-400">
                    Rejection explanation
                  </h5>

                  <label
                    htmlFor={'reason-' + record.allocation_id}
                    className="block text-xs text-slate-300"
                  >
                    Rejection reason *
                  </label>

                  <textarea
                    id={'reason-' + record.allocation_id}
                    value={rejectionDraft.reason}
                    onChange={event => {
                      setRejectionDraft(previous => ({
                        ...previous,
                        reason: event.target.value
                      }))
                    }}
                    rows={4}
                    required
                    disabled={Boolean(approvingId) || authBusy}
                    placeholder="Explain why this allocation should be rejected..."
                    className="w-full rounded-xl border border-slate-700 bg-slate-900 p-3 text-sm text-slate-200 outline-none focus:border-rose-500"
                  />

                  <div className="flex flex-wrap justify-between gap-2 text-xs">
                    <span className={
                      reasonValidation.valid
                        ? 'text-emerald-400'
                        : 'text-slate-400'
                    }>
                      {reasonValidation.valid
                        ? 'Valid explanation'
                        : 'Use 10-500 characters without line breaks or control characters.'}
                    </span>

                    <span className="text-slate-400">
                      {reasonValidation.length}/500
                    </span>
                  </div>

                  <p className="text-xs text-amber-400">
                    Rejection is final. Inventory remains unchanged.
                    Your explanation will be retained in the audit record.
                  </p>

                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      disabled={Boolean(approvingId)}
                      onClick={() => setRejectionDraft(null)}
                      className="rounded-xl border border-slate-700 px-4 py-3 text-sm text-slate-300 disabled:opacity-40"
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      disabled={
                        !reasonValidation.valid ||
                        Boolean(approvingId) ||
                        authBusy ||
                        !csrfToken
                      }
                      className="rounded-xl bg-rose-700 px-4 py-3 text-sm font-semibold text-white hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {approvingId === record.allocation_id
                        ? 'Rejecting...'
                        : 'Confirm Rejection'}
                    </button>
                  </div>
                </form>
              )}

            </article>
          ))}

          {(offset > 0 || hasMore) && (
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={offset === 0 || loading || Boolean(approvingId)}
                onClick={() => changePage(Math.max(0, offset - PAGE_SIZE))}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-2 text-xs disabled:opacity-40"
              >
                <ChevronLeft size={15} />
                Previous
              </button>

              <button
                type="button"
                disabled={!hasMore || loading || Boolean(approvingId)}
                onClick={() => changePage(offset + PAGE_SIZE)}
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

    <AllocationHistory refreshVersion={revision} />

    </>
  )
}
