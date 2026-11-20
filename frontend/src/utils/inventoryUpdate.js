const MAX_STOCK = 2147483647
const RESOURCES = ['food', 'water', 'medicine']

function parseQuantity(value, label) {
  const validNumber =
    typeof value === 'number' &&
    Number.isSafeInteger(value)

  const validText =
    typeof value === 'string' &&
    /^[0-9]+$/.test(value.trim())

  if (!validNumber && !validText) {
    throw new Error(`${label} must be a non-negative whole number.`)
  }

  const quantity = Number(value)

  if (
    !Number.isSafeInteger(quantity) ||
    quantity < 0 ||
    quantity > MAX_STOCK
  ) {
    throw new Error(
      `${label} must be between 0 and ${MAX_STOCK}.`
    )
  }

  return quantity
}

export function buildInventoryUpdatePayload(warehouse, values) {
  if (
    !warehouse ||
    !Number.isSafeInteger(warehouse.id) ||
    warehouse.id <= 0 ||
    !values ||
    typeof values !== 'object'
  ) {
    throw new Error('Invalid warehouse inventory request.')
  }

  const expected = {}
  const updated = {}

  for (const resource of RESOURCES) {
    expected[resource] = parseQuantity(
      warehouse[resource],
      `Current ${resource}`
    )

    updated[resource] = parseQuantity(
      values[resource],
      `New ${resource}`
    )
  }

  return {
    ...updated,
    expected
  }
}

export async function submitInventoryUpdate(write, warehouse, values) {
  const payload = buildInventoryUpdatePayload(warehouse, values)

  const response = await write(
    `/warehouses/${warehouse.id}/inventory`,
    'PUT',
    payload
  )

  let data

  try {
    data = await response.json()
  } catch {
    throw new Error(
      'Inventory update result uncertain. Refresh before retrying.'
    )
  }

  if (!response.ok) {
    const error = new Error(
      response.status === 409
        ? 'Inventory has changed. Refresh before retrying.'
        : 'Inventory update failed.'
    )
    error.status = response.status
    throw error
  }

  if (
    data?.warehouse_id !== warehouse.id ||
    !data.inventory ||
    !RESOURCES.every(
      resource => data.inventory[resource] === payload[resource]
    )
  ) {
    throw new Error(
      'Inventory update result uncertain. Refresh before retrying.'
    )
  }

  return data
}
