export function rebalanceManualMorningTimes(config, assignments, date) {
  const result = assignments.map(row => ({...row}))
  const morning = result.filter(row => row.date === date && row.shift === "MORNING")
  if (!morning.length || morning.length > 3) return result

  const overrides = new Map(
    (config?.morning_time_overrides || [])
      .filter(item => item.date === date)
      .map(item => [item.employee_id, item.start])
  )

  if (morning.length <= 2) {
    for (const row of morning) {
      row.start_time = overrides.get(row.employee_id) === "07:00" ? "07:00" : "06:00"
    }
    return result
  }

  const forced07 = morning.filter(row => overrides.get(row.employee_id) === "07:00")
  const forced06 = new Set(
    morning
      .filter(row => overrides.get(row.employee_id) === "06:00")
      .map(row => row.employee_id)
  )

  let late = null
  if (forced07.length === 1) {
    late = forced07[0]
  } else if (forced07.length === 0) {
    const currentLate = morning.filter(
      row => row.start_time === "07:00" && !forced06.has(row.employee_id)
    )
    if (currentLate.length === 1) {
      late = currentLate[0]
    } else {
      const managerId = (config?.employees || []).find(
        employee => employee.active && employee.role === "STORE_MANAGER"
      )?.id
      const candidates = morning.filter(row => !forced06.has(row.employee_id))
      late = candidates.find(row => row.employee_id === managerId) || candidates[0] || null
    }
  }

  if (late) {
    for (const row of morning) {
      row.start_time = row.employee_id === late.employee_id ? "07:00" : "06:00"
    }
  } else {
    // Multiple explicit 07:00 locks are a real HARD conflict. Preserve them so
    // validation can explain the problem instead of silently deleting a lock.
    for (const row of morning) {
      const forced = overrides.get(row.employee_id)
      if (forced === "07:00" || forced === "06:00") row.start_time = forced
    }
  }
  return result
}
