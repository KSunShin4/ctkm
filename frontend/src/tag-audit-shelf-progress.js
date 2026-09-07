export const SHELF_FAIL_REASONS = [
  "Sai giá",
  "Sai ngày",
  "Sai CTKM",
  "Thiếu tem",
  "Dư tem",
  "Sai sản phẩm",
  "Khác",
]

export function localDay(now = new Date()) {
  const date = now instanceof Date ? now : new Date(now)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function progressStorageKey(contextId, day = localDay()) {
  return `ctkm.shelf.progress.v1:${String(day || "unknown-day")}:${String(contextId || "unknown")}`
}

export function normalizeProgress(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {}
  const result = {}
  for (const [key, value] of Object.entries(raw)) {
    if (!value || typeof value !== "object") continue
    const state = value.state === "pass" || value.state === "fail" || value.state === "review"
      ? value.state
      : null
    if (!state) continue
    result[key] = {
      state,
      reason: String(value.reason || ""),
      note: String(value.note || ""),
      checkedAt: String(value.checkedAt || ""),
      resolved: Boolean(value.resolved),
    }
  }
  return result
}

export function progressStats(items, progress) {
  const safeItems = Array.isArray(items) ? items : []
  const safeProgress = normalizeProgress(progress)
  let pass = 0
  let fail = 0
  let review = 0
  for (const item of safeItems) {
    const state = safeProgress[item?.check_key]?.state
    if (state === "pass") pass += 1
    else if (state === "fail") fail += 1
    else if (state === "review") review += 1
  }
  const checked = pass + fail + review
  return {
    total: safeItems.length,
    checked,
    remaining: Math.max(0, safeItems.length - checked),
    pass,
    fail,
    review,
  }
}

export function shelfStats(items, progress, shelfKey) {
  const shelfItems = (Array.isArray(items) ? items : []).filter(item => item?.shelf_key === shelfKey)
  return progressStats(shelfItems, progress)
}

export function firstUncheckedIndex(items, progress, startIndex = 0) {
  const safeItems = Array.isArray(items) ? items : []
  const safeProgress = normalizeProgress(progress)
  if (!safeItems.length) return -1
  const start = Math.max(0, Math.min(safeItems.length - 1, Number(startIndex) || 0))
  for (let index = start; index < safeItems.length; index += 1) {
    if (!safeProgress[safeItems[index]?.check_key]) return index
  }
  for (let index = 0; index < start; index += 1) {
    if (!safeProgress[safeItems[index]?.check_key]) return index
  }
  return -1
}

export function recordDecision(progress, checkKey, state, reason = "", note = "", now = new Date()) {
  const safe = normalizeProgress(progress)
  if (!checkKey) return safe
  if (!new Set(["pass", "fail", "review"]).has(state)) return safe
  return {
    ...safe,
    [checkKey]: {
      state,
      reason: state === "pass" ? "" : String(reason || ""),
      note: String(note || ""),
      checkedAt: now instanceof Date ? now.toISOString() : String(now || ""),
      resolved: false,
    },
  }
}

export function markResolved(progress, checkKey, resolved = true) {
  const safe = normalizeProgress(progress)
  if (!safe[checkKey]) return safe
  return {
    ...safe,
    [checkKey]: { ...safe[checkKey], resolved: Boolean(resolved) },
  }
}
