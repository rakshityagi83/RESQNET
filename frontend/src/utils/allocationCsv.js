const resources = ['food', 'water', 'medicine']

export function csvCell(value) {
  let text = value == null ? '' : String(value)

  // Mitigate spreadsheet formula injection.
  if (
    /^[\s\u0000-\u001f]*[=+\-@＝＋－＠]/u.test(text) ||
    /^[\t\r\n]/.test(text)
  ) {
    text = "'" + text
  }

  return '"' + text.replace(/"/g, '""') + '"'
}

export function buildAllocationCsv(records) {
  if (!Array.isArray(records)) {
    throw new TypeError('Expected allocation records')
  }

  const headers = [
    'Allocation ID',
    'Incident ID',
    'Warehouse',
    'Created at (as stored)',
    'Status',
    'Requested food (units)',
    'Requested water (litres)',
    'Requested medicine (kits)',
    'Proposed food (units)',
    'Proposed water (litres)',
    'Proposed medicine (kits)',
    'Preview food shortage',
    'Preview water shortage',
    'Preview medicine shortage',
    'Deducted food (units)',
    'Deducted water (litres)',
    'Deducted medicine (kits)',
    'Submitted by (ID)',
    'Submitted by (username)',
    'Decided by (ID)',
    'Decided by (username)',
    'Decision time (UTC)',
    'Rejection reason'
  ]

  const rows = records.map(record => [
    record.allocation_id,
    record.incident_id,
    record.warehouse,
    record.created_at,
    record.status,

    ...resources.map(
      key => record.requested[key]
    ),

    ...resources.map(
      key => record.proposed_allocation[key]
    ),

    ...resources.map(
      key => record.shortages[key]
    ),

    ...resources.map(
      key => record.status === 'APPROVED'
        ? record.proposed_allocation[key]
        : 0
    ),

    record.submitted_by,
    record.submitted_by_username,
    record.decided_by,
    record.decided_by_username,
    record.decided_at,
    record.rejection_reason
  ])

  return [headers, ...rows]
    .map(row => row.map(csvCell).join(','))
    .join('\r\n') + '\r\n'
}

export function downloadAllocationCsv(records) {
  const csv = buildAllocationCsv(records)

  const blob = new Blob(
    ['\uFEFF', csv],
    { type: 'text/csv;charset=utf-8;' }
  )

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  const date = new Date()
    .toISOString()
    .slice(0, 10)

  anchor.href = url
  anchor.download = `RESQNET-allocations-${date}.csv`

  document.body.appendChild(anchor)

  try {
    anchor.click()
  } finally {
    anchor.remove()

    setTimeout(() => {
      URL.revokeObjectURL(url)
    }, 1000)
  }
}
