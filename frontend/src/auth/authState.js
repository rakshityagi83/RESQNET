export function initialAuthState(enabled = true) {
  return {
    status: enabled ? 'checking' : 'disabled',
    session: null,
    busy: null,
    error: ''
  }
}

export function authReducer(state, action) {
  switch (action.type) {
    case 'START':
      return {
        ...state,
        busy: action.operation,
        error: ''
      }

    case 'AUTHENTICATED':
      return {
        status: 'authenticated',
        session: action.session,
        busy: null,
        error: ''
      }

    case 'ANONYMOUS':
      return {
        status: 'anonymous',
        session: null,
        busy: null,
        error: action.error || ''
      }

    case 'UNAVAILABLE':
      return {
        status: 'unavailable',
        session: null,
        busy: null,
        error: action.error
      }

    case 'LOGOUT_FAILED':
      return {
        ...state,
        busy: null,
        error: action.error
      }

    default:
      return state
  }
}
