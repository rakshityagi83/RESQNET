import test from 'node:test'
import assert from 'node:assert/strict'

import {
  validAuditFields,
  formatAuditActor,
  formatAuditTimestamp
} from '../src/utils/allocationAudit.js'

const legacy = {
  status: 'APPROVED',
  submitted_by: null,
  submitted_by_username: null,
  decided_by: null,
  decided_by_username: null,
  decided_at: null,
  rejection_reason: null
}

const pending = {
  ...legacy,
  status: 'PENDING',
  submitted_by: 10,
  submitted_by_username: 'test_operator'
}

const approved = {
  ...pending,
  status: 'APPROVED',
  decided_by: 20,
  decided_by_username: 'test_admin',
  decided_at: '2026-11-20T04:00:00.123456Z'
}

test('legacy audit fields remain valid', () => {
  assert.equal(validAuditFields(legacy), true)
})

test('pending allocation includes submitter identity', () => {
  assert.equal(validAuditFields(pending), true)
})

test('approved allocation includes decision metadata', () => {
  assert.equal(validAuditFields(approved), true)
})

test('rejected allocation includes explanation', () => {
  assert.equal(
    validAuditFields({
      ...approved,
      status: 'REJECTED',
      rejection_reason: 'Duplicate allocation request'
    }),
    true
  )
})

test('malformed audit metadata is rejected', () => {
  for (const changes of [
    { submitted_by: undefined },
    { submitted_by: -1 },
    { submitted_by: '10' },
    { submitted_by_username: 123 },
    { decided_at: 'invalid date' },
    { decided_at: '2026-11-20T04:00:00' },
    { decided_by: null },
    { decided_at: null },
    { rejection_reason: 'Unexpected rejection reason' }
  ]) {
    assert.equal(
      validAuditFields({ ...approved, ...changes }),
      false
    )
  }
})

test('pending allocations cannot contain decision metadata', () => {
  assert.equal(
    validAuditFields({
      ...approved,
      status: 'PENDING'
    }),
    false
  )
})

test('actor formatting handles missing identities', () => {
  assert.equal(
    formatAuditActor(null, null),
    'Not recorded'
  )

  assert.equal(
    formatAuditActor(10, null),
    'User ID: 10'
  )

  assert.equal(
    formatAuditActor(10, 'test_operator'),
    'test_operator (User ID: 10)'
  )
})

test('decision timestamps are explicitly displayed in UTC', () => {
  assert.equal(
    formatAuditTimestamp(approved.decided_at),
    '2026-11-20 04:00:00 UTC'
  )

  assert.equal(
    formatAuditTimestamp(null),
    'Not recorded'
  )

  assert.equal(
    formatAuditTimestamp('invalid'),
    'Invalid timestamp'
  )
})
