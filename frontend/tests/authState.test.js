import test from 'node:test'
import assert from 'node:assert/strict'

import {
  initialAuthState,
  authReducer
} from '../src/auth/authState.js'

const SESSION = {
  user: {
    id: 167,
    username: 'testadmin',
    role: 'admin'
  },
  csrfToken: 'a'.repeat(64)
}

const authenticated = () => authReducer(
  initialAuthState(),
  {
    type: 'AUTHENTICATED',
    session: SESSION
  }
)

test('startup begins with session checking', () => {
  const state = initialAuthState()

  assert.equal(state.status, 'checking')
  assert.equal(state.session, null)
})

test('authentication can remain disabled', () => {
  const state = initialAuthState(false)

  assert.equal(state.status, 'disabled')
  assert.equal(state.session, null)
})

test('successful authentication stores session in state', () => {
  const state = authenticated()

  assert.equal(state.status, 'authenticated')
  assert.deepEqual(state.session, SESSION)
  assert.equal(state.error, '')
})

test('starting an operation sets busy state', () => {
  const state = authReducer(authenticated(), {
    type: 'START',
    operation: 'logout'
  })

  assert.equal(state.busy, 'logout')
  assert.deepEqual(state.session, SESSION)
})

test('successful logout clears identity and CSRF', () => {
  const state = authReducer(authenticated(), {
    type: 'ANONYMOUS'
  })

  assert.equal(state.status, 'anonymous')
  assert.equal(state.session, null)
  assert.equal(state.busy, null)
})

test('expired session clears authentication state', () => {
  const state = authReducer(authenticated(), {
    type: 'ANONYMOUS',
    error: 'Session expired'
  })

  assert.equal(state.session, null)
  assert.equal(state.error, 'Session expired')
})

test('server failure differs from anonymous session', () => {
  const state = authReducer(initialAuthState(), {
    type: 'UNAVAILABLE',
    error: 'Server unavailable'
  })

  assert.equal(state.status, 'unavailable')
  assert.equal(state.session, null)
})

test('failed logout does not falsely report success', () => {
  const state = authReducer(authenticated(), {
    type: 'LOGOUT_FAILED',
    error: 'Logout failed'
  })

  assert.equal(state.status, 'authenticated')
  assert.deepEqual(state.session, SESSION)
  assert.equal(state.busy, null)
  assert.equal(state.error, 'Logout failed')
})
