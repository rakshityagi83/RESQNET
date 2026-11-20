export function validateRejectionReason(value) {
  const reason = typeof value === 'string'
    ? value.trim()
    : ''

  const length = Array.from(reason).length

  const valid =
    length >= 10 &&
    length <= 500 &&
    !/[\u0000-\u001f\u007f-\u009f]/u.test(reason)

  return { reason, length, valid }
}
