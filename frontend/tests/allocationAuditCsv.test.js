import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAllocationCsv
} from '../src/utils/allocationCsv.js'

const record = {
  allocation_id: 'test-allocation',
  incident_id: 'test-incident',
  warehouse: 'Test Warehouse',
  created_at: '2026-11-20T03:00:00',
  status: 'REJECTED',

  requested: {
    food: 100,
    water: 200,
    medicine: 10
  },

  proposed_allocation: {
    food: 100,
    water: 200,
    medicine: 10
  },

  shortages: {
    food: 0,
    water: 0,
    medicine: 0
  },

  submitted_by: 10,
  submitted_by_username: 'test_operator',
  decided_by: 20,
  decided_by_username: 'test_admin',
  decided_at: '2026-11-20T04:00:00.123456Z',
  rejection_reason: 'Duplicate allocation request'
}

test('CSV includes all six audit headers', () => {
  const headers = buildAllocationCsv([])
    .split('\r\n')[0]

  assert.equal(headers.split(',').length, 23)

  for (const header of [
    'Submitted by (ID)',
    'Submitted by (username)',
    'Decided by (ID)',
    'Decided by (username)',
    'Decision time (UTC)',
    'Rejection reason'
  ]) {
    assert.ok(headers.includes(`"${header}"`))
  }
})

test('CSV preserves authenticated actors and decision information', () => {
  const row = buildAllocationCsv([record])
    .split('\r\n')[1]

  assert.ok(
    row.endsWith(
      '"10","test_operator","20","test_admin",' +
      '"2026-11-20T04:00:00.123456Z",' +
      '"Duplicate allocation request"'
    )
  )
})

test('legacy CSV records leave unknown audit fields empty', () => {
  const legacy = {
    ...record,
    submitted_by: null,
    submitted_by_username: null,
    decided_by: null,
    decided_by_username: null,
    decided_at: null,
    rejection_reason: null
  }

  const row = buildAllocationCsv([legacy])
    .split('\r\n')[1]

  assert.ok(row.endsWith(',"","","","","",""'))
})

test('audit explanations cannot inject spreadsheet formulas', () => {
  const csv = buildAllocationCsv([{
    ...record,
    rejection_reason: '=HYPERLINK("unsafe")'
  }])

  assert.ok(csv.includes(
    `"'=HYPERLINK(""unsafe"")"`
  ))
})
