export const SHELF_FAIL_REASONS = [
  "Sai giá",
  "Sai ngày",
  "Sai CTKM",
  "Thiếu tem",
  "Dư tem",
  "Sai sản phẩm",
  "Khác",
]

export const REMOVAL_STATES = new Set(["removed", "still_present", "not_found"])

export function localDay(now = new Date()) {
  const date = now instanceof Date ? now : new Date(now)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function progressStorageKey(contextId, day = localDay()) {
  return `ctkm.shelf.progress.v2:${String(day || "unknown-day")}:${String(contextId || "unknown")}`
}

export function removalStorageKey(storeScopeId) {
  return `ctkm.shelf.removal.v2:${String(storeScopeId || "unknown-store")}`
}

export function extraTagStorageKey(storeScopeId) {
  return `ctkm.shelf.extra.v1:${String(storeScopeId || "unknown-store")}`
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

export function normalizeRemovalProgress(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {}
  const result = {}
  for (const [key, value] of Object.entries(raw)) {
    if (!value || typeof value !== "object" || !REMOVAL_STATES.has(value.state)) continue
    result[key] = {
      state: value.state,
      note: String(value.note || ""),
      checkedAt: String(value.checkedAt || ""),
    }
  }
  return result
}

export function normalizeExtraTags(raw) {
  if (!Array.isArray(raw)) return []
  return raw.filter(row => row && typeof row === "object" && row.id).map(row => ({
    id: String(row.id),
    item_id: String(row.item_id || ""),
    item_name: String(row.item_name || ""),
    shelf_key: String(row.shelf_key || ""),
    shelf_label: String(row.shelf_label || ""),
    note: String(row.note || ""),
    checkedAt: String(row.checkedAt || ""),
    resolved: Boolean(row.resolved),
  }))
}

function removalStateToday(value, day = localDay()) {
  if (!value || !REMOVAL_STATES.has(value.state)) return null
  if (value.state === "removed") return "pass"
  if (!value.checkedAt || localDay(value.checkedAt) !== day) return null
  if (value.state === "still_present") return "fail"
  if (value.state === "not_found") return "review"
  return null
}

export function itemProgressState(item, progress, removalProgress = {}, day = localDay()) {
  if (item?.expected_action === "thao_tem") {
    return removalStateToday(normalizeRemovalProgress(removalProgress)[item?.removal_key], day)
  }
  return normalizeProgress(progress)[item?.check_key]?.state || null
}

export function progressStats(items, progress, removalProgress = {}, day = localDay()) {
  const safeItems = Array.isArray(items) ? items : []
  const safeProgress = normalizeProgress(progress)
  const safeRemoval = normalizeRemovalProgress(removalProgress)
  let pass = 0
  let fail = 0
  let review = 0
  let attachTotal = 0
  let removeTotal = 0
  let removed = 0
  let removeStillPresent = 0
  let removeNotFound = 0

  for (const item of safeItems) {
    if (item?.expected_action === "thao_tem") {
      removeTotal += 1
      const removal = safeRemoval[item?.removal_key]
      if (removal?.state === "removed") removed += 1
      const state = removalStateToday(removal, day)
      if (state === "pass") pass += 1
      else if (state === "fail") { fail += 1; removeStillPresent += 1 }
      else if (state === "review") { review += 1; removeNotFound += 1 }
      continue
    }
    attachTotal += 1
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
    attachTotal,
    removeTotal,
    removed,
    removePending: Math.max(0, removeTotal - removed),
    removeStillPresent,
    removeNotFound,
  }
}

export function shelfStats(items, progress, shelfKey, removalProgress = {}, day = localDay()) {
  const shelfItems = (Array.isArray(items) ? items : []).filter(item => item?.shelf_key === shelfKey)
  return progressStats(shelfItems, progress, removalProgress, day)
}

function isCheckedNow(item, progress, removalProgress, day) {
  if (item?.expected_action === "thao_tem") {
    const removal = normalizeRemovalProgress(removalProgress)[item?.removal_key]
    if (removal?.state === "removed") return true
    return Boolean(removal?.checkedAt && localDay(removal.checkedAt) === day && REMOVAL_STATES.has(removal.state))
  }
  return Boolean(normalizeProgress(progress)[item?.check_key])
}

export function firstUncheckedIndex(items, progress, startIndex = 0, removalProgress = {}, day = localDay()) {
  const safeItems = Array.isArray(items) ? items : []
  if (!safeItems.length) return -1
  const start = Math.max(0, Math.min(safeItems.length - 1, Number(startIndex) || 0))
  for (let index = start; index < safeItems.length; index += 1) {
    if (!isCheckedNow(safeItems[index], progress, removalProgress, day)) return index
  }
  for (let index = 0; index < start; index += 1) {
    if (!isCheckedNow(safeItems[index], progress, removalProgress, day)) return index
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

export function recordRemovalDecision(removalProgress, removalKey, state, note = "", now = new Date()) {
  const safe = normalizeRemovalProgress(removalProgress)
  if (!removalKey || !REMOVAL_STATES.has(state)) return safe
  return {
    ...safe,
    [removalKey]: {
      state,
      note: String(note || ""),
      checkedAt: now instanceof Date ? now.toISOString() : String(now || ""),
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

export function resetProgressForItems(progress, items) {
  const safe = normalizeProgress(progress)
  const keys = new Set((Array.isArray(items) ? items : []).filter(item => item?.expected_action !== "thao_tem").map(item => item?.check_key).filter(Boolean))
  return Object.fromEntries(Object.entries(safe).filter(([key]) => !keys.has(key)))
}

export function resetRemovalTodayForItems(removalProgress, items, day = localDay()) {
  const safe = normalizeRemovalProgress(removalProgress)
  const keys = new Set((Array.isArray(items) ? items : []).filter(item => item?.expected_action === "thao_tem").map(item => item?.removal_key).filter(Boolean))
  const result = {...safe}
  for (const key of keys) {
    const value = result[key]
    if (!value || value.state === "removed") continue
    if (value.checkedAt && localDay(value.checkedAt) === day) delete result[key]
  }
  return result
}

export function resetRemovalToday(removalProgress, day = localDay()) {
  const safe = normalizeRemovalProgress(removalProgress)
  const result = {...safe}
  for (const [key, value] of Object.entries(result)) {
    if (value.state === "removed") continue
    if (value.checkedAt && localDay(value.checkedAt) === day) delete result[key]
  }
  return result
}

export function markExtraResolved(extraTags, id, resolved = true) {
  return normalizeExtraTags(extraTags).map(row => row.id === id ? {...row, resolved:Boolean(resolved)} : row)
}

export function buildShelfCameraUrl(shelfKey, itemId = "", checkKey = "") {
  const params = new URLSearchParams({ mode: "quick" })
  if (shelfKey) params.set("shelf", String(shelfKey).trim())
  if (itemId) params.set("item_id", String(itemId).trim().toUpperCase())
  if (checkKey) params.set("check_key", String(checkKey).trim())
  return `/scan-tem?${params.toString()}`
}

export function parseShelfCameraContext(search = "") {
  const query = typeof search === "string" ? search : ""
  const params = new URLSearchParams(query.startsWith("?") ? query : `?${query}`)
  const shelf = String(params.get("shelf") || "").trim()
  const itemId = String(params.get("item_id") || "").trim().toUpperCase()
  const checkKey = String(params.get("check_key") || "").trim()
  return {
    shelf,
    itemId,
    checkKey,
    hasContext: Boolean(shelf || itemId),
  }
}

export function buildShelfReturnUrl(shelfKey = "") {
  const params = new URLSearchParams({ mode: "shelf" })
  if (shelfKey) params.set("shelf", String(shelfKey).trim())
  return `/scan-tem?${params.toString()}`
}

export function applyCameraScanToShelfProgress(progress, shelfItems, scanResult, now = new Date()) {
  const safeProgress = normalizeProgress(progress)
  const safeItems = Array.isArray(shelfItems) ? shelfItems : []
  if (!scanResult || !safeItems.length) {
    return { progress: safeProgress, matchedItem: null, matched: false }
  }

  const observedId = String(
    scanResult.observed?.item_id ||
    scanResult.expected?.item_id ||
    scanResult.item_id ||
    ""
  ).trim().toUpperCase()

  const scanCheckKey = String(scanResult.check_key || "").trim()

  let matchedItem = null
  if (scanCheckKey) {
    matchedItem = safeItems.find(item => item.check_key === scanCheckKey) || null
  }
  if (!matchedItem && observedId) {
    matchedItem = safeItems.find(item => String(item.item_id || "").trim().toUpperCase() === observedId) || null
  }

  if (!matchedItem || !matchedItem.check_key) {
    return { progress: safeProgress, matchedItem: null, matched: false }
  }

  const verdictCode = String(scanResult.verdict?.code || "").toUpperCase()
  const severity = String(scanResult.verdict?.severity || "").toLowerCase()
  let state = "review"
  let reason = ""

  if (verdictCode === "PASS" || severity === "success") {
    state = "pass"
    reason = ""
  } else if (verdictCode === "FAIL" || severity === "error") {
    state = "fail"
    reason = String(scanResult.verdict?.title || scanResult.verdict?.detail || "Sai theo camera")
  } else {
    state = "review"
    reason = String(scanResult.verdict?.title || scanResult.verdict?.detail || "Review từ camera")
  }

  const updatedProgress = recordDecision(
    safeProgress,
    matchedItem.check_key,
    state,
    reason,
    "Camera check",
    now
  )

  return {
    progress: updatedProgress,
    matchedItem,
    matched: true,
  }
}

