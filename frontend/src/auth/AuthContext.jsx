import {
  createContext,
  useContext,
  useReducer,
  useRef,
  useEffect,
  useCallback
} from 'react'

import {
  authClient,
  AuthApiError
} from '../services/authClient.js'

import {
  initialAuthState,
  authReducer
} from './authState.js'

const AuthContext = createContext(null)

export function AuthProvider({ children, enabled = false }) {
  const [state, dispatch] = useReducer(
    authReducer,
    enabled,
    initialAuthState
  )

  const activeOperation = useRef(null)

  const run = useCallback(async (
    operation,
    task,
    signal
  ) => {
    if (!enabled || activeOperation.current) {
      return false
    }

    const current = { operation }

    activeOperation.current = current

    dispatch({
      type: 'START',
      operation
    })

    try {
      const session = await task()

      if (
        signal?.aborted ||
        activeOperation.current !== current
      ) {
        return false
      }

      dispatch(
        operation === 'logout'
          ? { type: 'ANONYMOUS' }
          : { type: 'AUTHENTICATED', session }
      )

      return true
    } catch (error) {
      if (
        signal?.aborted ||
        activeOperation.current !== current
      ) {
        return false
      }

      const status = error instanceof AuthApiError
        ? error.status
        : 0

      const message = error instanceof AuthApiError
        ? error.message
        : 'Authentication service unavailable.'

      if (operation === 'logout') {
        dispatch({
          type: 'LOGOUT_FAILED',
          error: message
        })
      } else if (
        status === 401 ||
        (
          operation === 'login' &&
          [422, 429].includes(status)
        )
      ) {
        dispatch({
          type: 'ANONYMOUS',
          error: operation === 'recover' ? '' : message
        })
      } else {
        dispatch({
          type: 'UNAVAILABLE',
          error: message
        })
      }

      return false
    } finally {
      if (activeOperation.current === current) {
        activeOperation.current = null
      }
    }
  }, [enabled])

  const recoverSession = useCallback(
    signal => run(
      'recover',
      () => authClient.recoverSession(signal),
      signal
    ),
    [run]
  )

  useEffect(() => {
    if (!enabled) return

    const controller = new AbortController()

    recoverSession(controller.signal)

    return () => {
      controller.abort()
      activeOperation.current = null
    }
  }, [enabled, recoverSession])

  async function login(username, password) {
    if (state.status !== 'anonymous') {
      return false
    }

    return run(
      'login',
      () => authClient.login(username, password)
    )
  }

  async function logout() {
    if (
      state.status !== 'authenticated' ||
      !state.session
    ) {
      return false
    }

    return run(
      'logout',
      () => authClient.logout(state.session.csrfToken)
    )
  }

  const user = state.session?.user || null

  return (
    <AuthContext.Provider
      value={{
        status: state.status,
        busy: state.busy,
        error: state.error,
        user,
        csrfToken: state.session?.csrfToken || null,
        isAuthenticated: state.status === 'authenticated',
        isAdmin: user?.role === 'admin',
        isOperator: ['admin', 'operator'].includes(user?.role),
        login,
        logout,
        recoverSession
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth requires AuthProvider')
  }

  return context
}
