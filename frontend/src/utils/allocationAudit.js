import { validateRejectionReason } from './rejectionReason.js'

const validId = value =>
  value === null ||
  (Number.isSafeInteger(value) && value > 0)

const validUsername = value =>
  value === null ||
  (
    typeof value === 'string' &&
    value.trim().length > 0 &&
    value.length <= 32
  )

export function validAuditFields(record) {
  if (!record) return false

  const {
    submitted_by,
    submitted_by_username,
    decided_by,
    decided_by_username,
    decided_at,
    rejection_reason
  } = record

  if (
    !validId(submitted_by) ||
    !validId(decided_by) ||
    !validUsername(submitted_by_username) ||
    !validUsername(decided_by_username)
  ) return false

  if (
    (submitted_by === null &&
      submitted_by_username !== null) ||
    (decided_by === null &&
      decided_by_username !== null)
  ) return false

  if (
    decided_at !== null &&
    (
      typeof decided_at !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(decided_at) ||
      !Number.isFinite(Date.parse(decided_at))
    )
  ) return false

  if (
    (decided_by === null) !== (decided_at === null)
  ) return false

  if (
    rejection_reason !== null &&
    (
      typeof rejection_reason !== 'string' ||
      !validateRejectionReason(rejection_reason).valid
    )
  ) return false

  if (
    record.status !== 'REJECTED' &&
    rejection_reason !== null
  ) return false

  if (
    record.status === 'PENDING' &&
    decided_by !== null
  ) return false

  return true
}

export function formatAuditActor(id, username) {
  if (id == null) return 'Not recorded'

  if (!username) return `User ID: ${id}`

  return `${username} (User ID: ${id})`
}

export function formatAuditTimestamp(value) {
  if (!value) return 'Not recorded'

  const date = new Date(value)

  if (!Number.isFinite(date.getTime())) {
    return 'Invalid timestamp'
  }

  return date.toISOString()
    .slice(0, 19)
    .replace('T', ' ') + ' UTC'
}
