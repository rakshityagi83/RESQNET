import test from 'node:test'
import assert from 'node:assert/strict'

import {
  csvCell,
  buildAllocationCsv
} from '../src/utils/allocationCsv.js'

const record = {
  allocation_id: 'test-allocation',
  incident_id: 'TEST-INCIDENT',
  warehouse: 'Test Warehouse',
  created_at: '2026-11-20T02:55:17',
  status: 'APPROVED',
  requested: {
    food: 500,
    water: 1000,
    medicine: 100
  },
  proposed_allocation: {
    food: 500,
    water: 1000,
    medicine: 100
  },
  shortages: {
    food: 0,
    water: 0,
    medicine: 0
  }
}


function deductedColumns(row) {
  // Extract quoted CSV cells, including escaped quotes.
  const cells = row.match(/"(?:[^"]|"")*"/g) ?? []

  assert.equal(cells.length, 23)

  // Deducted quantities occupy columns 15-17.
  return cells.slice(14, 17).join(',')
}

test('CSV includes allocation identifiers and headers', () => {
  const csv = buildAllocationCsv([record])

  assert.ok(csv.includes('"Allocation ID"'))
  assert.ok(csv.includes('"Status"'))
  assert.ok(csv.includes('"test-allocation"'))
  assert.ok(csv.includes('"TEST-INCIDENT"'))
  assert.ok(csv.includes('"APPROVED"'))
})

test('approved allocations include deducted quantities', () => {
  const csv = buildAllocationCsv([record])
  const row = csv.trim().split('\r\n')[1]

  assert.ok(
    deductedColumns(row) === ('"500","1000","100"')
  )
})

test('rejected allocations have zero deducted quantities', () => {
  const csv = buildAllocationCsv([{
    ...record,
    status: 'REJECTED'
  }])

  const row = csv.trim().split('\r\n')[1]

  assert.ok(deductedColumns(row) === ('"0","0","0"'))
})

test('pending allocations have zero deducted quantities', () => {
  const csv = buildAllocationCsv([{
    ...record,
    status: 'PENDING'
  }])

  const row = csv.trim().split('\r\n')[1]

  assert.ok(deductedColumns(row) === ('"0","0","0"'))
})

test('CSV safely escapes quotes and commas', () => {
  assert.equal(
    csvCell('Warehouse, "Sector 75"'),
    '"Warehouse, ""Sector 75"""'
  )
})

test('dangerous spreadsheet formulas are neutralized', () => {
  for (const value of [
    '=1+1',
    '+1+1',
    '-1+1',
    '@SUM(1,2)',
    '  =1+1',
    '\t=1+1',
    '\r=1+1',
    '＝1+1'
  ]) {
    assert.ok(csvCell(value).startsWith('"\''))
  }
})

test('missing values export as empty cells', () => {
  assert.equal(csvCell(null), '""')
  assert.equal(csvCell(undefined), '""')
  assert.equal(csvCell(0), '"0"')
})

test('empty exports contain headers only', () => {
  const csv = buildAllocationCsv([])

  assert.equal(
    csv.trim().split('\r\n').length,
    1
  )
})
