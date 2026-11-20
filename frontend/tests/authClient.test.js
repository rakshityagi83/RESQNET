import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createAuthClient,
  AuthApiError
} from '../src/services/authClient.js'

const CSRF = 'a'.repeat(64)

const SESSION = {
  user: {
    id: 167,
    username: 'testadmin',
    role: 'admin'
  },
  csrf_token: CSRF
}

function mockClient(status = 200, data = SESSION) {
  const calls = []

  const client = createAuthClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options })

      return new Response(
        status === 204 ? null : JSON.stringify(data),
        {
          status,
          headers: {
            'Content-Type': 'application/json'
          }
        }
      )
    }
  })

  return { client, calls }
}

test('login sends credentials and enables cookies', async () => {
  const { client, calls } = mockClient()

  const result = await client.login(
    'testadmin',
    'disposable-test-password'
  )

  assert.equal(result.user.role, 'admin')
  assert.equal(result.csrfToken, CSRF)

  assert.equal(
    calls[0].url,
    'http://localhost:8000/auth/login'
  )

  const options = calls[0].options

  assert.equal(options.credentials, 'include')
  assert.equal(options.cache, 'no-store')
  assert.equal(options.redirect, 'error')

  assert.deepEqual(JSON.parse(options.body), {
    username: 'testadmin',
    password: 'disposable-test-password'
  })
})

test('session recovery does not require a password', async () => {
  const { client, calls } = mockClient()

  const result = await client.recoverSession()

  assert.equal(result.user.id, 167)
  assert.equal(result.csrfToken, CSRF)

  assert.equal(
    calls[0].url,
    'http://localhost:8000/auth/session'
  )

  assert.equal(calls[0].options.body, undefined)
  assert.equal(calls[0].options.credentials, 'include')
})

test('logout sends session-bound CSRF token', async () => {
  const { client, calls } = mockClient(204)

  await client.logout(CSRF)

  assert.equal(
    calls[0].url,
    'http://localhost:8000/auth/logout'
  )

  assert.equal(
    calls[0].options.headers.get('X-CSRF-Token'),
    CSRF
  )
})

test('logout without CSRF never reaches API', async () => {
  const { client, calls } = mockClient()

  await assert.rejects(
    () => client.logout(undefined),
    AuthApiError
  )

  assert.equal(calls.length, 0)
})

test('protected inventory update includes CSRF', async () => {
  const { client, calls } = mockClient(200, {
    message: 'Inventory updated'
  })

  const response = await client.protectedWrite(
    '/warehouses/1/inventory',
    'PUT',
    { food: 100, water: 200, medicine: 50 },
    CSRF
  )

  assert.equal(response.status, 200)
  assert.equal(calls[0].options.method, 'PUT')

  assert.equal(
    calls[0].options.headers.get('X-CSRF-Token'),
    CSRF
  )
})

test('protected write without CSRF is rejected locally', async () => {
  const { client, calls } = mockClient()

  await assert.rejects(
    () => client.protectedWrite(
      '/warehouses',
      'POST',
      {},
      undefined
    ),
    AuthApiError
  )

  assert.equal(calls.length, 0)
})

test('unapproved request destinations are rejected', async () => {
  assert.throws(
    () => createAuthClient({
      baseUrl: 'https://untrusted.example'
    }),
    /Unsafe authentication API destination/
  )

  const { client, calls } = mockClient()

  await assert.rejects(
    () => client.protectedWrite(
      '//untrusted.example',
      'POST',
      {},
      CSRF
    ),
    AuthApiError
  )

  assert.equal(calls.length, 0)
})

test('invalid credentials return sanitized errors', async () => {
  const { client } = mockClient(401, {
    detail: 'sensitive-test-marker'
  })

  await assert.rejects(
    () => client.login('testadmin', 'wrong-password'),
    error =>
      error.status === 401 &&
      !error.message.includes('sensitive-test-marker')
  )
})

test('unsupported account roles are rejected', async () => {
  const { client } = mockClient(200, {
    ...SESSION,
    user: {
      ...SESSION.user,
      role: 'unknown'
    }
  })

  await assert.rejects(
    () => client.recoverSession(),
    /Invalid authentication response/
  )
})

test('invalid CSRF response is rejected', async () => {
  const { client } = mockClient(200, {
    ...SESSION,
    csrf_token: 'invalid-token'
  })

  await assert.rejects(
    () => client.recoverSession(),
    /Invalid authentication response/
  )
})

test('network failure returns a controlled error', async () => {
  const client = createAuthClient({
    fetchImpl: async () => {
      throw new Error('Internal network failure')
    }
  })

  await assert.rejects(
    () => client.recoverSession(),
    error =>
      error.status === 0 &&
      error.message ===
        'Unable to reach the authentication server.'
  )
})

test('rate-limited login returns HTTP 429 error', async () => {
  const { client } = mockClient(429)

  await assert.rejects(
    () => client.login('testadmin', 'wrong-password'),
    error => error.status === 429
  )
})
