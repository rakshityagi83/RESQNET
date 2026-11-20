import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildInventoryUpdatePayload,
  submitInventoryUpdate
} from '../src/utils/inventoryUpdate.js'

const warehouse = {
  id: 224,
  food: 100,
  water: 200,
  medicine: 50
}

const updated = {
  food: '150',
  water: '300',
  medicine: '75'
}

test('update sends original and requested stock', () => {
  assert.deepEqual(
    buildInventoryUpdatePayload(warehouse, updated),
    {
      food: 150,
      water: 300,
      medicine: 75,
      expected: {
        food: 100,
        water: 200,
        medicine: 50
      }
    }
  )
})

test('zero inventory is valid', () => {
  const payload = buildInventoryUpdatePayload(
    warehouse,
    { food: '0', water: '0', medicine: '0' }
  )

  assert.equal(payload.food, 0)
  assert.equal(payload.water, 0)
  assert.equal(payload.medicine, 0)
})

test('invalid new quantities are rejected', () => {
  for (const invalid of [
    -1, '1.5', '', 'abc', true, null, 2147483648
  ]) {
    assert.throws(() =>
      buildInventoryUpdatePayload(warehouse, {
        ...updated,
        food: invalid
      })
    )
  }
})

test('invalid original stock is rejected', () => {
  assert.throws(() =>
    buildInventoryUpdatePayload(
      { ...warehouse, water: -1 },
      updated
    )
  )
})

test('successful update sends exactly one request', async () => {
  const calls = []

  const write = async (path, method, body) => {
    calls.push({ path, method, body })

    return {
      ok: true,
      json: async () => ({
        warehouse_id: 224,
        inventory: {
          food: 150,
          water: 300,
          medicine: 75
        }
      })
    }
  }

  const result = await submitInventoryUpdate(
    write, warehouse, updated
  )

  assert.equal(calls.length, 1)
  assert.equal(calls[0].method, 'PUT')
  assert.equal(
    calls[0].path,
    '/warehouses/224/inventory'
  )
  assert.equal(calls[0].body.expected.food, 100)
  assert.equal(result.inventory.food, 150)
})

test('invalid input cannot reach the API', async () => {
  let calls = 0

  await assert.rejects(
    submitInventoryUpdate(
      async () => {
        calls++
        throw new Error('Unexpected request')
      },
      warehouse,
      { ...updated, medicine: -1 }
    )
  )

  assert.equal(calls, 0)
})

test('HTTP 409 propagates without retrying the write', async () => {
  let calls = 0

  const write = async () => {
    calls++
    const error = new Error('Conflict')
    error.status = 409
    throw error
  }

  await assert.rejects(
    submitInventoryUpdate(write, warehouse, updated),
    error => error.status === 409
  )

  assert.equal(calls, 1)
})

test('unconfirmed server response is rejected', async () => {
  const write = async () => ({
    ok: true,
    json: async () => ({
      warehouse_id: 224,
      inventory: { food: 999, water: 300, medicine: 75 }
    })
  })

  await assert.rejects(
    submitInventoryUpdate(write, warehouse, updated),
    /result uncertain/
  )
})
