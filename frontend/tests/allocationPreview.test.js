import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAllocationPreviewDraft,
  prepareAllocationPreviewRequest,
  submitAllocationPreview
} from '../src/utils/allocationPreview.js'

const ID_1 = '12345678-1234-4234-8234-123456789abc'
const ID_2 = '12345678-1234-4234-8234-123456789abd'

const form = {
  incident_id: 'TEST-INCIDENT',
  warehouse_id: '224',
  food: '30',
  water: '40',
  medicine: '1'
}

function createResponse(replayed = false, status = 'PENDING HUMAN APPROVAL') {
  return {
    ok: true,
    json: async () => ({
      allocation_id: 'allocation-test-id',
      incident: { id: 'TEST-INCIDENT' },
      warehouse: 'Test Warehouse',
      requested: { food: 30, water: 40, medicine: 1 },
      available: { food: 50, water: 80, medicine: 10 },
      proposed_allocation: { food: 30, water: 40, medicine: 1 },
      shortages: { food: 0, water: 0, medicine: 0 },
      status,
      replayed
    })
  }
}

test('draft contains validated numeric quantities', () => {
  assert.deepEqual(buildAllocationPreviewDraft(form), {
    incident_id: 'TEST-INCIDENT',
    warehouse_id: 224,
    food: 30,
    water: 40,
    medicine: 1
  })
})

test('same form and user reuse the original UUID', () => {
  const first = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  )

  const second = prepareAllocationPreviewRequest(
    first.request,
    { ...form },
    7,
    () => { throw new Error('Must not generate another UUID') }
  )

  assert.deepEqual(second.payload, first.payload)
})

test('changing quantities starts a new allocation request', () => {
  const first = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  )

  const changed = prepareAllocationPreviewRequest(
    first.request,
    { ...form, food: '31' },
    7,
    () => ID_2
  )

  assert.equal(changed.payload.client_request_id, ID_2)
  assert.equal(changed.payload.food, 31)
})

test('changing authenticated user creates a new request ID', () => {
  const first = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  )

  const second = prepareAllocationPreviewRequest(
    first.request, form, 8, () => ID_2
  )

  assert.equal(second.payload.client_request_id, ID_2)
})

test('invalid inputs never generate request IDs', () => {
  let generated = 0
  const makeId = () => {
    generated++
    return ID_1
  }

  for (const invalid of [
    { ...form, warehouse_id: '' },
    { ...form, incident_id: '' },
    { ...form, food: -1 },
    { ...form, food: '1.5' },
    { ...form, medicine: '2147483648' }
  ]) {
    assert.throws(() =>
      prepareAllocationPreviewRequest(
        null, invalid, 7, makeId
      )
    )
  }

  assert.equal(generated, 0)
})

test('network failure retry preserves exactly the same UUID', async () => {
  const first = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  )

  const bodies = []

  const write = async (_path, _method, body) => {
    bodies.push(body)

    if (bodies.length === 1) {
      throw new Error('Network interrupted')
    }

    return createResponse(true)
  }

  await assert.rejects(
    submitAllocationPreview(write, first.payload),
    /Network interrupted/
  )

  const retry = prepareAllocationPreviewRequest(
    first.request,
    form,
    7,
    () => { throw new Error('Retry generated a new ID') }
  )

  const result = await submitAllocationPreview(
    write, retry.payload
  )

  assert.equal(result.replayed, true)
  assert.equal(bodies.length, 2)
  assert.deepEqual(bodies[0], bodies[1])
})

test('an approved allocation replay is recognized', async () => {
  const payload = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  ).payload

  const result = await submitAllocationPreview(
    async () => createResponse(true, 'APPROVED'),
    payload
  )

  assert.equal(result.status, 'APPROVED')
  assert.equal(result.replayed, true)
})

test('unconfirmed server response is rejected', async () => {
  const payload = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  ).payload

  await assert.rejects(
    submitAllocationPreview(
      async () => ({
        ok: true,
        json: async () => ({ message: 'OK' })
      }),
      payload
    ),
    /result uncertain/
  )
})

test('HTTP 409 propagates without automatically retrying', async () => {
  const payload = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  ).payload

  let calls = 0

  const write = async () => {
    calls++
    const error = new Error('HTTP 409')
    error.status = 409
    throw error
  }

  await assert.rejects(
    submitAllocationPreview(write, payload),
    error => error.status === 409
  )

  assert.equal(calls, 1)
})


test('zero requested resources are rejected before UUID creation', () => {
  const empty = {
    ...form,
    food: '0',
    water: '0',
    medicine: '0'
  }

  let generated = 0

  assert.throws(
    () => prepareAllocationPreviewRequest(
      null,
      empty,
      7,
      () => {
        generated++
        return ID_1
      }
    ),
    /at least one relief resource/
  )

  assert.equal(generated, 0)
})

test('one positive resource remains a valid request', () => {
  const draft = buildAllocationPreviewDraft({
    ...form,
    food: '0',
    water: '1',
    medicine: '0'
  })

  assert.equal(draft.food, 0)
  assert.equal(draft.water, 1)
  assert.equal(draft.medicine, 0)
})

test('empty server allocation is rejected', async () => {
  const payload = prepareAllocationPreviewRequest(
    null, form, 7, () => ID_1
  ).payload

  const write = async () => ({
    ok: true,
    json: async () => ({
      allocation_id: 'allocation-test-id',
      incident: { id: 'TEST-INCIDENT' },
      warehouse: 'Test Warehouse',
      requested: { food: 30, water: 40, medicine: 1 },
      available: { food: 0, water: 0, medicine: 0 },
      proposed_allocation: { food: 0, water: 0, medicine: 0 },
      shortages: { food: 30, water: 40, medicine: 1 },
      status: 'PENDING HUMAN APPROVAL',
      replayed: false
    })
  })

  await assert.rejects(
    submitAllocationPreview(write, payload),
    /result uncertain/
  )
})
