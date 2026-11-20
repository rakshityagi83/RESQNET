const MAX_QUANTITY = 2147483647

const UUID4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const RESOURCES = ['food', 'water', 'medicine']

function parseQuantity(value, field) {
  const validNumber =
    typeof value === 'number' &&
    Number.isSafeInteger(value) &&
    value >= 0 &&
    value <= MAX_QUANTITY

  const validString =
    typeof value === 'string' &&
    /^[0-9]+$/.test(value) &&
    Number.isSafeInteger(Number(value)) &&
    Number(value) <= MAX_QUANTITY

  if (!validNumber && !validString) {
    throw new Error(
      `${field} must be a non-negative whole number.`
    )
  }

  return Number(value)
}

export function buildAllocationPreviewDraft(form) {
  if (
    !form ||
    typeof form.incident_id !== 'string' ||
    !form.incident_id.trim()
  ) {
    throw new Error('Select a valid incident.')
  }

  const warehouse = form.warehouse_id

  const warehouseId =
    typeof warehouse === 'number'
      ? warehouse
      : typeof warehouse === 'string' &&
          /^[1-9][0-9]*$/.test(warehouse)
        ? Number(warehouse)
        : NaN

  if (
    !Number.isSafeInteger(warehouseId) ||
    warehouseId <= 0
  ) {
    throw new Error('Select a valid warehouse.')
  }

  const draft = {
    incident_id: form.incident_id,
    warehouse_id: warehouseId,
    food: parseQuantity(form.food, 'Food'),
    water: parseQuantity(form.water, 'Water'),
    medicine: parseQuantity(form.medicine, 'Medical kits')
  }

  if (RESOURCES.every(key => draft[key] === 0)) {
    throw new Error('Request at least one relief resource.')
  }

  return draft
}

export function prepareAllocationPreviewRequest(
  previous,
  form,
  userId,
  createUuid = () => globalThis.crypto.randomUUID()
) {
  if (!Number.isSafeInteger(userId) || userId <= 0) {
    throw new Error('Authenticated user required.')
  }

  // Validate before generating an identifier.
  const draft = buildAllocationPreviewDraft(form)
  const fingerprint = JSON.stringify(draft)

  const reuse =
    previous?.userId === userId &&
    previous?.fingerprint === fingerprint &&
    UUID4_PATTERN.test(previous?.requestId ?? '')

  const requestId = reuse
    ? previous.requestId
    : createUuid()

  if (
    typeof requestId !== 'string' ||
    !UUID4_PATTERN.test(requestId)
  ) {
    throw new Error('Unable to generate a secure request ID.')
  }

  return {
    request: {
      userId,
      fingerprint,
      requestId
    },
    payload: {
      ...draft,
      client_request_id: requestId
    }
  }
}

export async function submitAllocationPreview(write, payload) {
  const response = await write(
    '/allocation/preview',
    'POST',
    payload
  )

  let data

  try {
    data = await response.json()
  } catch {
    throw new Error(
      'Allocation preview result uncertain. Retry the same request.'
    )
  }

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : 'Allocation preview request failed.'
    )
  }

  const validQuantities = quantities =>
    quantities &&
    RESOURCES.every(key =>
      Number.isSafeInteger(quantities[key]) &&
      quantities[key] >= 0
    )

  const valid =
    data &&
    typeof data.allocation_id === 'string' &&
    data.allocation_id.length > 0 &&
    data.incident?.id === payload.incident_id &&
    typeof data.warehouse === 'string' &&
    [
      'PENDING HUMAN APPROVAL',
      'APPROVED',
      'REJECTED'
    ].includes(data.status) &&
    typeof data.replayed === 'boolean' &&
    validQuantities(data.requested) &&
    validQuantities(data.available) &&
    validQuantities(data.proposed_allocation) &&
    validQuantities(data.shortages) &&
    RESOURCES.some(
      key => data.proposed_allocation[key] > 0
    ) &&
    RESOURCES.every(key =>
      data.requested[key] === payload[key] &&
      data.proposed_allocation[key] <= data.available[key] &&
      data.requested[key] ===
        data.proposed_allocation[key] + data.shortages[key]
    )

  if (!valid) {
    throw new Error(
      'Allocation preview result uncertain. Retry the same request.'
    )
  }

  return data
}
