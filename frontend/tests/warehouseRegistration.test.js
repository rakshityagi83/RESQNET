import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildWarehouseRegistrationPayload,
  submitWarehouseRegistration
} from '../src/utils/warehouseRegistration.js'

const form = {
  name: 'Atomic Test Warehouse',
  state: 'Haryana',
  district: 'Faridabad',
  latitude: '',
  longitude: '',
  verified_by: 'Test Administrator',
  food: '500',
  water: '1000',
  medicine: '100'
}

test('registration payload includes validated initial stock', () => {
  const payload = buildWarehouseRegistrationPayload(form)

  assert.equal(payload.food, 500)
  assert.equal(payload.water, 1000)
  assert.equal(payload.medicine, 100)
  assert.equal(payload.latitude, null)
  assert.equal(payload.longitude, null)
})

test('zero stock is accepted', () => {
  const payload = buildWarehouseRegistrationPayload({
    ...form,
    food: 0,
    water: '0',
    medicine: 0
  })

  assert.equal(payload.food, 0)
  assert.equal(payload.water, 0)
  assert.equal(payload.medicine, 0)
})

test('invalid initial stock is rejected', () => {
  for (const invalid of [
    -1, 1.5, '', ' ', 'abc', true, null, 2147483648
  ]) {
    assert.throws(() =>
      buildWarehouseRegistrationPayload({
        ...form,
        food: invalid
      })
    )
  }
})

test('registration makes exactly one POST request', async () => {
  const calls = []

  const write = async (path, method, body) => {
    calls.push({ path, method, body })

    return {
      ok: true,
      json: async () => ({ warehouse_id: 71 })
    }
  }

  const result = await submitWarehouseRegistration(
    write, form
  )

  assert.equal(result.warehouse_id, 71)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].path, '/warehouses')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].body.food, 500)
  assert.equal(calls[0].body.water, 1000)
  assert.equal(calls[0].body.medicine, 100)
})

test('invalid input never reaches the API', async () => {
  let calls = 0

  const write = async () => {
    calls++
    throw new Error('Should not be called')
  }

  await assert.rejects(
    submitWarehouseRegistration(write, {
      ...form,
      medicine: -1
    })
  )

  assert.equal(calls, 0)
})

test('server rejection is reported without a second write', async () => {
  let calls = 0

  const write = async () => {
    calls++

    return {
      ok: false,
      json: async () => ({
        detail: 'Invalid warehouse registration'
      })
    }
  }

  await assert.rejects(
    submitWarehouseRegistration(write, form),
    /Invalid warehouse registration/
  )

  assert.equal(calls, 1)
})

test('unexpected success response is not treated as confirmed', async () => {
  const write = async () => ({
    ok: true,
    json: async () => ({ message: 'OK' })
  })

  await assert.rejects(
    submitWarehouseRegistration(write, form),
    /Registration result uncertain/
  )
})
