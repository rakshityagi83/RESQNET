import test from 'node:test'
import assert from 'node:assert/strict'

import {
  validateRejectionReason
} from '../src/utils/rejectionReason.js'

import {
  createAuthClient
} from '../src/services/authClient.js'

test('rejection explanation trims surrounding whitespace', () => {
  const result = validateRejectionReason(
    '  Duplicate allocation request  '
  )

  assert.equal(result.reason, 'Duplicate allocation request')
  assert.equal(result.valid, true)
})

test('rejection explanation enforces length boundaries', () => {
  assert.equal(validateRejectionReason('x'.repeat(9)).valid, false)
  assert.equal(validateRejectionReason('x'.repeat(10)).valid, true)
  assert.equal(validateRejectionReason('x'.repeat(500)).valid, true)
  assert.equal(validateRejectionReason('x'.repeat(501)).valid, false)
})

test('rejection explanation counts Unicode code points', () => {
  const result = validateRejectionReason(
    '\u{1F600}'.repeat(10)
  )

  assert.equal(result.length, 10)
  assert.equal(result.valid, true)
})

test('rejection explanation rejects control characters', () => {
  for (const character of ['\x00', '\n', '\r', '\t', '\x7f']) {
    const result = validateRejectionReason(
      'Duplicate' + character + 'allocation request'
    )

    assert.equal(result.valid, false)
  }
})

test('empty or non-string explanations are rejected', () => {
  for (const value of ['', '   ', null, undefined, 123]) {
    assert.equal(
      validateRejectionReason(value).valid,
      false
    )
  }
})

test('rejection sends reason with authenticated CSRF request', async () => {
  const calls = []

  const client = createAuthClient({
    fetchImpl: async (url, options) => {
      calls.push({ url, options })

      return new Response(
        JSON.stringify({ status: 'REJECTED' }),
        { status: 200 }
      )
    }
  })

  const csrf = 'a'.repeat(64)

  const validation = validateRejectionReason(
    '  Duplicate allocation request  '
  )

  assert.equal(validation.valid, true)

  await client.protectedWrite(
    '/allocation/02c25918-24de-4765-b6d4-606021b7abad/reject',
    'POST',
    { reason: validation.reason },
    csrf
  )

  assert.equal(calls.length, 1)

  assert.equal(
    calls[0].options.credentials,
    'include'
  )

  assert.equal(
    new Headers(calls[0].options.headers).get('X-CSRF-Token'),
    csrf
  )

  assert.deepEqual(
    JSON.parse(calls[0].options.body),
    { reason: 'Duplicate allocation request' }
  )
})
