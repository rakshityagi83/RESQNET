import { validAuditFields } from '../utils/allocationAudit.js'
const LOCAL_API = 'http://localhost:8000'

export class AuthApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'AuthApiError'
    this.status = status
  }
}

function errorMessage(status) {
  switch (status) {
    case 401:
      return 'Invalid credentials or expired session.'
    case 403:
      return 'Request forbidden or permission denied.'
    case 422:
      return 'Invalid authentication request.'
    case 409:
      return 'Request conflicts with current server state. Refresh and retry.'
    case 429:
      return 'Too many login attempts. Try again later.'
    default:
      return 'Authentication service unavailable.'
  }
}

function validateSession(data) {
  const user = data?.user

  if (
    !user ||
    !Number.isSafeInteger(user.id) ||
    user.id <= 0 ||
    typeof user.username !== 'string' ||
    !user.username ||
    !['admin', 'operator'].includes(user.role) ||
    typeof data.csrf_token !== 'string' ||
    !/^[a-f0-9]{64}$/.test(data.csrf_token)
  ) {
    throw new AuthApiError(
      0,
      'Invalid authentication response.'
    )
  }

  return {
    user: {
      id: user.id,
      username: user.username,
      role: user.role
    },
    csrfToken: data.csrf_token
  }
}

export function createAuthClient({
  baseUrl = LOCAL_API,
  fetchImpl = globalThis.fetch
} = {}) {
  // Local-only until production deployment is configured.
  if (baseUrl !== LOCAL_API) {
    throw new Error('Unsafe authentication API destination.')
  }

  async function request(
    path,
    { method = 'POST', body, csrfToken, signal } = {}
  ) {
    const headers = new Headers({
      Accept: 'application/json'
    })

    if (body !== undefined) {
      headers.set('Content-Type', 'application/json')
    }

    if (csrfToken !== undefined) {
      if (
        typeof csrfToken !== 'string' ||
        !/^[a-f0-9]{64}$/.test(csrfToken)
      ) {
        throw new AuthApiError(403, 'Invalid CSRF token.')
      }

      headers.set('X-CSRF-Token', csrfToken)
    }

    let response

    try {
      response = await fetchImpl(baseUrl + path, {
        method,
        headers,
        credentials: 'include',
        cache: 'no-store',
        redirect: 'error',
        body: body === undefined
          ? undefined
          : JSON.stringify(body),
        signal
      })
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw error
      }

      throw new AuthApiError(
        0,
        'Unable to reach the authentication server.'
      )
    }

    if (!response.ok) {
      throw new AuthApiError(
        response.status,
        errorMessage(response.status)
      )
    }

    return response
  }

  async function readSession(response) {
    if (response.status !== 200) {
      throw new AuthApiError(
        0,
        'Unexpected authentication response.'
      )
    }

    let data

    try {
      data = await response.json()
    } catch {
      throw new AuthApiError(
        0,
        'Invalid authentication response.'
      )
    }

    return validateSession(data)
  }

  async function readAllocationPage(
    path,
    { limit = 20, offset = 0, status = 'PENDING', q = '', signal } = {}
  ) {
    if (
      !Number.isInteger(limit) ||
      limit < 1 ||
      limit > 100 ||
      !Number.isSafeInteger(offset) ||
      offset < 0
    ) {
      throw new AuthApiError(422, 'Invalid queue pagination.')
    }

    const statuses = [
      'ALL', 'PENDING', 'APPROVED', 'REJECTED'
    ]

    if (
      !statuses.includes(status) ||
      typeof q !== 'string' ||
      q.length > 150
    ) {
      throw new AuthApiError(422, 'Invalid history filters.')
    }

    const query = new URLSearchParams({
      limit: String(limit),
      offset: String(offset)
    })

    if (path === '/allocations/history') {
      query.set('status', status)
      query.set('q', q.trim())
    }

    const response = await request(
      path + '?' + query.toString(),
      { method: 'GET', signal }
    )

    let data

    try {
      data = await response.json()
    } catch {
      throw new AuthApiError(0, 'Invalid allocation queue response.')
    }

    const keys = ['food', 'water', 'medicine']

    const validQuantities = quantities =>
      quantities &&
      keys.every(
        key =>
          Number.isSafeInteger(quantities[key]) &&
          quantities[key] >= 0
      )

    const validRecord = record =>
      record &&
      typeof record.allocation_id === 'string' &&
      typeof record.incident_id === 'string' &&
      (record.warehouse === null ||
        typeof record.warehouse === 'string') &&
      ['PENDING', 'APPROVED', 'REJECTED'].includes(record.status) &&
      (status === 'ALL' || record.status === status) &&
      (record.created_at == null ||
        typeof record.created_at === 'string') &&
      validAuditFields(record) &&
      validQuantities(record.requested) &&
      validQuantities(record.proposed_allocation) &&
      validQuantities(record.shortages) &&
      keys.every(
        key =>
          record.requested[key] ===
          record.proposed_allocation[key] + record.shortages[key]
      )

    if (
      !data ||
      !Array.isArray(data.allocations) ||
      data.count !== data.allocations.length ||
      data.count > limit ||
      data.limit !== limit ||
      data.offset !== offset ||
      typeof data.has_more !== 'boolean' ||
      !data.allocations.every(validRecord)
    ) {
      throw new AuthApiError(0, 'Invalid allocation queue response.')
    }

    return data
  }

  return {
    async listPendingAllocations(
      { limit = 20, offset = 0, signal } = {}
    ) {
      return readAllocationPage('/allocations/pending', {
        limit,
        offset,
        status: 'PENDING',
        signal
      })
    },

    async listAllocationHistory(
      { limit = 20, offset = 0, status = 'ALL', q = '', signal } = {}
    ) {
      return readAllocationPage('/allocations/history', {
        limit,
        offset,
        status,
        q,
        signal
      })
    },

    async login(username, password, signal) {
      const response = await request('/auth/login', {
        body: { username, password },
        signal
      })

      return readSession(response)
    },

    async recoverSession(signal) {
      const response = await request('/auth/session', {
        signal
      })

      return readSession(response)
    },

    async logout(csrfToken, signal) {
      if (!csrfToken) {
        throw new AuthApiError(403, 'CSRF token required.')
      }

      const response = await request('/auth/logout', {
        csrfToken,
        signal
      })

      if (response.status !== 204) {
        throw new AuthApiError(
          0,
          'Unexpected logout response.'
        )
      }
    },

    async protectedWrite(path, method, body, csrfToken, signal) {
      const allowed =
        (method === 'POST' && path === '/warehouses') ||
        (method === 'PUT' &&
          /^\/warehouses\/[1-9]\d*\/inventory$/.test(path)) ||
        (method === 'POST' &&
          path === '/allocation/preview') ||
        (method === 'POST' &&
          /^\/allocation\/[a-f0-9-]{36}\/(?:approve|reject)$/.test(path))

      if (!allowed) {
        throw new AuthApiError(
          403,
          'Unsupported protected operation.'
        )
      }

      if (!csrfToken) {
        throw new AuthApiError(403, 'CSRF token required.')
      }

      return request(path, {
        method,
        body,
        csrfToken,
        signal
      })
    }
  }
}

export const authClient = createAuthClient()
