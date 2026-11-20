import {
  User,
  ShieldCheck,
  Clock,
  ClipboardList
} from 'lucide-react'

import {
  formatAuditActor,
  formatAuditTimestamp
} from '../utils/allocationAudit.js'

export default function AllocationAuditDetails({ record }) {
  const pending = record.status === 'PENDING'
  const rejected = record.status === 'REJECTED'

  return (
    <section
      aria-label="Allocation audit trail"
      className="mt-4 space-y-3 rounded-xl border border-slate-700/70 bg-slate-900/60 p-4"
    >
      <h5 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        <ClipboardList size={15} />
        Allocation Audit Trail
      </h5>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 items-start gap-2">
          <User size={17} className="mt-1 shrink-0 text-cyan-400" />

          <div className="min-w-0">
            <p className="text-xs text-slate-400">
              Submitted by
            </p>

            <p className="mt-1 break-words text-sm text-slate-200">
              {formatAuditActor(
                record.submitted_by,
                record.submitted_by_username
              )}
            </p>
          </div>
        </div>

        {!pending && (
          <div className="flex min-w-0 items-start gap-2">
            <ShieldCheck
              size={17}
              className="mt-1 shrink-0 text-emerald-400"
            />

            <div className="min-w-0">
              <p className="text-xs text-slate-400">
                {rejected ? 'Rejected by' : 'Approved by'}
              </p>

              <p className="mt-1 break-words text-sm text-slate-200">
                {formatAuditActor(
                  record.decided_by,
                  record.decided_by_username
                )}
              </p>
            </div>
          </div>
        )}
      </div>

      {pending ? (
        <p className="text-xs text-amber-400">
          Awaiting administrator decision.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <Clock size={15} className="shrink-0" />

          Decision time:

          <span className="text-slate-300">
            {formatAuditTimestamp(record.decided_at)}
          </span>
        </div>
      )}

      {rejected && (
        <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
          <p className="text-xs font-semibold text-rose-400">
            Rejection reason
          </p>

          <p className="mt-2 break-words text-sm text-slate-300">
            {record.rejection_reason ?? 'Not recorded'}
          </p>
        </div>
      )}
    </section>
  )
}
