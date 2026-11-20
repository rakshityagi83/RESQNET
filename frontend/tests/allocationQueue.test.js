import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createAuthClient
} from '../src/services/authClient.js'

const RECORD = {
  submitted_by: null,
  submitted_by_username: null,
  decided_by: null,
  decided_by_username: null,
  decided_at: null,
  rejection_reason: null,
  allocation_id: 'test-allocation',
  incident_id: 'TEST-INCIDENT',
  warehouse: 'Test Warehouse',
  status: 'PENDING',
  requested: { food: 40, water: 60, medicine: 10 },
  proposed_allocation: { food: 40, water: 60, medicine: 10 },
  shortages: { food: 0, water: 0, medicine: 0 }
}

const PAGE = {
  allocations: [RECORD],
  count: 1,
  limit: 20,
  offset: 0,
  has_more: false
}

function mockClient(status = 200, data = PAGE) {
  const calls = []

  const client = createAuthClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options })

      return new Response(JSON.stringify(data), {
        status,
        headers: {
          'Content-Type': 'application/json'
        }
      })
    }
  })

  return { client, calls }
}

test('pending queue uses authenticated read requests', async () => {
  const { client, calls } = mockClient()

  const result = await client.listPendingAllocations()

  assert.deepEqual(result, PAGE)

  assert.equal(
    calls[0].url,
    'http://localhost:8000/allocations/pending?limit=20&offset=0'
  )

  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.cache, 'no-store')
  assert.equal(calls[0].options.body, undefined)
})

test('queue supports pagination', async () => {
  const { client, calls } = mockClient(200, {
    ...PAGE,
    limit: 10,
    offset: 20
  })

  await client.listPendingAllocations({
    limit: 10,
    offset: 20
  })

  assert.ok(calls[0].url.endsWith('?limit=10&offset=20'))
})

test('invalid pagination never reaches server', async () => {
  const { client, calls } = mockClient()

  for (const options of [
    { limit: 0 },
    { limit: 101 },
    { offset: -1 },
    { limit: 1.5 }
  ]) {
    await assert.rejects(
      () => client.listPendingAllocations(options),
      error => error.status === 422
    )
  }

  assert.equal(calls.length, 0)
})

test('anonymous queue access returns HTTP 401', async () => {
  const { client } = mockClient(401)

  await assert.rejects(
    () => client.listPendingAllocations(),
    error => error.status === 401
  )
})

test('unauthorized queue access returns HTTP 403', async () => {
  const { client } = mockClient(403)

  await assert.rejects(
    () => client.listPendingAllocations(),
    error => error.status === 403
  )
})

test('invalid allocation records are rejected', async () => {
  const { client } = mockClient(200, {
    ...PAGE,
    allocations: [{
      ...RECORD,
      proposed_allocation: {
        food: -1,
        water: 60,
        medicine: 10
      }
    }]
  })

  await assert.rejects(
    () => client.listPendingAllocations(),
    /Invalid allocation queue response/
  )
})


const REJECTION_ID = '02c25918-24de-4765-b6d4-606021b7abad'
const REJECTION_CSRF = 'a'.repeat(64)

test('rejection sends authenticated CSRF-protected POST', async () => {
  const { client, calls } = mockClient()

  await client.protectedWrite(
    '/allocation/' + REJECTION_ID + '/reject',
    'POST',
    undefined,
    REJECTION_CSRF
  )

  assert.equal(calls.length, 1)

  assert.equal(
    calls[0].url,
    'http://localhost:8000/allocation/' + REJECTION_ID + '/reject'
  )

  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.credentials, 'include')

  assert.equal(
    new Headers(calls[0].options.headers).get('X-CSRF-Token'),
    REJECTION_CSRF
  )
})

test('rejection without CSRF never reaches the server', async () => {
  const { client, calls } = mockClient()

  await assert.rejects(
    () => client.protectedWrite(
      '/allocation/' + REJECTION_ID + '/reject',
      'POST',
      undefined,
      ''
    )
  )

  assert.equal(calls.length, 0)
})

test('unknown allocation decisions remain blocked', async () => {
  const { client, calls } = mockClient()

  await assert.rejects(
    () => client.protectedWrite(
      '/allocation/' + REJECTION_ID + '/delete',
      'POST',
      undefined,
      REJECTION_CSRF
    )
  )

  assert.equal(calls.length, 0)
})


test('history sends authenticated read requests', async () => {
  const { client, calls } = mockClient()

  const result = await client.listAllocationHistory()

  assert.deepEqual(result, PAGE)

  const url = new URL(calls[0].url)

  assert.equal(url.pathname, '/allocations/history')
  assert.equal(url.searchParams.get('status'), 'ALL')
  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.cache, 'no-store')
})

test('history encodes search and status filters', async () => {
  const { client, calls } = mockClient(200, {
    ...PAGE,
    allocations: [{
      ...RECORD,
      status: 'APPROVED'
    }],
    limit: 10,
    offset: 20
  })

  await client.listAllocationHistory({
    status: 'APPROVED',
    q: 'Faridabad & Delhi',
    limit: 10,
    offset: 20
  })

  const url = new URL(calls[0].url)

  assert.equal(url.searchParams.get('status'), 'APPROVED')
  assert.equal(url.searchParams.get('q'), 'Faridabad & Delhi')
  assert.equal(url.searchParams.get('limit'), '10')
  assert.equal(url.searchParams.get('offset'), '20')
})

test('invalid history filters never reach server', async () => {
  const { client, calls } = mockClient()

  for (const options of [
    { status: 'UNKNOWN' },
    { q: 'x'.repeat(151) },
    { q: 123 },
    { offset: -1 }
  ]) {
    await assert.rejects(
      () => client.listAllocationHistory(options),
      error => error.status === 422
    )
  }

  assert.equal(calls.length, 0)
})

test('history rejects inconsistent quantities', async () => {
  const { client } = mockClient(200, {
    ...PAGE,
    allocations: [{
      ...RECORD,
      shortages: {
        food: 999,
        water: 0,
        medicine: 0
      }
    }]
  })

  await assert.rejects(
    () => client.listAllocationHistory(),
    /Invalid allocation queue response/
  )
})

test('unauthorized history requests are rejected', async () => {
  for (const status of [401, 403]) {
    const { client } = mockClient(status)

    await assert.rejects(
      () => client.listAllocationHistory(),
      error => error.status === status
    )
  }
})
