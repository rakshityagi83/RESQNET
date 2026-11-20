const MAX_STOCK = 2147483647

function parseStock(value, name) {
  if (
    value == null ||
    typeof value === 'boolean' ||
    (typeof value === 'string' && value.trim() === '')
  ) {
    throw new Error(`${name} must be a non-negative whole number.`)
  }

  const quantity = Number(value)

  if (
    !Number.isSafeInteger(quantity) ||
    quantity < 0 ||
    quantity > MAX_STOCK
  ) {
    throw new Error(
      `${name} must be a whole number between 0 and ${MAX_STOCK}.`
    )
  }

  return quantity
}

export function buildWarehouseRegistrationPayload(form) {
  if (!form || typeof form !== 'object') {
    throw new Error('Warehouse registration details are required.')
  }

  return {
    name: form.name,
    state: form.state,
    district: form.district,
    latitude: form.latitude === '' || form.latitude == null
      ? null
      : Number(form.latitude),
    longitude: form.longitude === '' || form.longitude == null
      ? null
      : Number(form.longitude),
    verified_by: form.verified_by,
    food: parseStock(form.food, 'Food'),
    water: parseStock(form.water, 'Water'),
    medicine: parseStock(form.medicine, 'Medical kits')
  }
}

export async function submitWarehouseRegistration(write, form) {
  const payload = buildWarehouseRegistrationPayload(form)

  // One authenticated write; no follow-up inventory PUT.
  const response = await write('/warehouses', 'POST', payload)

  let data

  try {
    data = await response.json()
  } catch {
    throw new Error(
      'Registration response unreadable. Check the warehouse list before retrying.'
    )
  }

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : 'Warehouse registration failed.'
    )
  }

  if (
    !Number.isSafeInteger(data?.warehouse_id) ||
    data.warehouse_id < 1
  ) {
    throw new Error(
      'Registration result uncertain. Check the warehouse list before retrying.'
    )
  }

  return data
}
