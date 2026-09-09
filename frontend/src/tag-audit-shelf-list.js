export const SHELF_FILTERS = [
  {key:"todo", label:"Cần kiểm"},
  {key:"remove", label:"Cần tháo"},
  {key:"issues", label:"Có lỗi"},
  {key:"done", label:"Đã xong"},
  {key:"all", label:"Tất cả"},
]

function normalizeText(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase("vi")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function compactText(value) {
  return normalizeText(value).replace(/\s+/g, "")
}

function editDistance(a, b) {
  const left = String(a || "")
  const right = String(b || "")
  if (left === right) return 0
  if (!left.length) return right.length
  if (!right.length) return left.length
  const previous = Array.from({length:right.length + 1}, (_, index) => index)
  for (let i = 1; i <= left.length; i += 1) {
    let diagonal = previous[0]
    previous[0] = i
    for (let j = 1; j <= right.length; j += 1) {
      const old = previous[j]
      const cost = left[i - 1] === right[j - 1] ? 0 : 1
      previous[j] = Math.min(previous[j] + 1, previous[j - 1] + 1, diagonal + cost)
      diagonal = old
    }
  }
  return previous[right.length]
}

function tokenMatchScore(needle, candidate) {
  if (!needle || !candidate) return 0
  if (needle === candidate) return 100
  if (candidate.startsWith(needle)) return 86
  if (candidate.includes(needle)) return 76
  if (/^[a-z]+$/.test(needle) && needle.length >= 4) {
    const allowed = needle.length >= 8 ? 2 : 1
    if (Math.abs(needle.length - candidate.length) <= allowed && editDistance(needle, candidate) <= allowed) return 64
  }
  return 0
}

function shelfItemsFor(shelf, items = []) {
  return (Array.isArray(items) ? items : []).filter(item => item?.shelf_key === shelf?.shelf_key)
}

function searchableParts(shelf, items = []) {
  const shelfItems = shelfItemsFor(shelf, items)
  const technical = [shelf?.shelf_label, shelf?.shelf_key, shelf?.pog_code, shelf?.location_id, ...(shelf?.locations || [])].filter(Boolean)
  const itemParts = shelfItems.flatMap(item => [item?.pog_code, item?.location_id, item?.item_id, item?.item_name]).filter(Boolean)
  return {technical, itemParts, shelfItems}
}

export function shelfSearchHaystack(shelf, items = []) {
  const {technical, itemParts} = searchableParts(shelf, items)
  return normalizeText([...technical, ...itemParts].join(" "))
}

function itemHint(item) {
  const text = [item?.item_id, item?.item_name].filter(Boolean).join(" · ")
  return text ? `Có ${text}` : ""
}

function searchShelf(shelf, items, query) {
  const needle = normalizeText(query)
  if (!needle) return {matches:true, score:0, matchHint:""}
  const compactNeedle = compactText(query)
  const {technical, itemParts, shelfItems} = searchableParts(shelf, items)
  const normalizedTechnical = technical.map(normalizeText)
  const normalizedItems = itemParts.map(normalizeText)
  const compactTechnical = technical.map(compactText)
  const allParts = [...normalizedTechnical, ...normalizedItems]
  const compactParts = [...technical, ...itemParts].map(compactText)

  if (/^p\d{3,8}$/.test(compactNeedle)) {
    const exactItem = shelfItems.find(item => compactText(item?.item_id) === compactNeedle)
    return exactItem ? {matches:true, score:240, matchHint:itemHint(exactItem)} : {matches:false, score:0, matchHint:""}
  }

  const looksLikeShelfCode = /^(?:ke|pog|loc|location|vitri|vt|tang)[a-z0-9]*\d/.test(compactNeedle)
  if (looksLikeShelfCode) {
    const exactTechnical = compactTechnical.some(part => part.includes(compactNeedle))
    if (!exactTechnical) return {matches:false, score:0, matchHint:""}
    return {matches:true, score:225, matchHint:""}
  }

  let score = 0
  if (normalizedTechnical.includes(needle)) score = Math.max(score, 180)
  if (normalizedItems.includes(needle)) score = Math.max(score, 175)
  if (allParts.some(part => part.startsWith(needle))) score = Math.max(score, 160)
  if (allParts.some(part => part.includes(needle))) score = Math.max(score, 145)
  if (compactNeedle && compactParts.some(part => part.includes(compactNeedle))) score = Math.max(score, 150)

  const queryTokens = needle.split(" ").filter(Boolean)
  const candidateTokens = allParts.flatMap(part => part.split(" ").filter(Boolean))
  if (queryTokens.length) {
    const tokenScores = queryTokens.map(token => candidateTokens.reduce((best, candidate) => Math.max(best, tokenMatchScore(token, candidate)), 0))
    if (tokenScores.every(Boolean)) score = Math.max(score, 80 + tokenScores.reduce((sum, value) => sum + value, 0) / tokenScores.length)
  }

  if (!score) return {matches:false, score:0, matchHint:""}

  let matchHint = ""
  for (const item of shelfItems) {
    const id = normalizeText(item?.item_id)
    const name = normalizeText(item?.item_name)
    const compactId = compactText(item?.item_id)
    const compactName = compactText(item?.item_name)
    const itemTokens = `${id} ${name}`.split(" ").filter(Boolean)
    const itemMatches = id === needle || name.includes(needle) || compactId.includes(compactNeedle) || compactName.includes(compactNeedle)
      || queryTokens.every(token => itemTokens.some(candidate => tokenMatchScore(token, candidate)))
    if (itemMatches) {
      matchHint = itemHint(item)
      break
    }
  }
  return {matches:true, score, matchHint}
}

export function shelfStatus(stats) {
  if (!stats || !stats.total) return "todo"
  if (stats.removePending > 0) return "remove"
  if (stats.fail || stats.review) return "issues"
  if (stats.remaining === 0) return "done"
  return "todo"
}

function shelfPriority(status, stats) {
  if ((stats?.removePending || 0) > 0) return 0
  if (status === "issues") return 1
  if ((stats?.checked || 0) > 0 && (stats?.remaining || 0) > 0) return 2
  if (status === "todo") return 3
  return 4
}

function matchesShelfFilter(filter, status, stats, needle) {
  if (filter === "all") return true
  if (needle && filter === "todo") return true
  if (filter === "remove") return (stats?.removePending || 0) > 0
  if (filter === "issues") return (stats?.fail || 0) > 0 || (stats?.review || 0) > 0
  if (filter === "done") return status === "done"
  if (filter === "todo") return status !== "done"
  return status === filter
}

export function smartShelfList(shelves, items, getStats, {query="", filter="todo", limit=12, searchLimit=8} = {}) {
  const needle = normalizeText(query)
  const ranked = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = getStats(shelf.shelf_key)
    const status = shelfStatus(stats)
    const search = searchShelf(shelf, items, query)
    const matchesFilter = matchesShelfFilter(filter, status, stats, needle)
    return {shelf, stats, status, order, priority:shelfPriority(status, stats), matchesQuery:search.matches, matchesFilter, matchScore:search.score, matchHint:search.matchHint}
  }).filter(row => row.matchesQuery && row.matchesFilter)

  ranked.sort((a,b) => needle
    ? b.matchScore - a.matchScore || a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order
    : a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order)
  const safeLimit = needle ? Math.max(1, Number(searchLimit) || 8) : Math.max(1, Number(limit) || 12)
  return {rows: ranked.slice(0, safeLimit), totalMatches: ranked.length}
}

function lastCheckedAtForShelf(shelfKey, items, progress, removalProgress) {
  let latest = 0
  for (const item of Array.isArray(items) ? items : []) {
    if (item?.shelf_key !== shelfKey) continue
    const source = item?.expected_action === "thao_tem"
      ? removalProgress?.[item?.removal_key]
      : progress?.[item?.check_key]
    const timestamp = Date.parse(source?.checkedAt || "")
    if (Number.isFinite(timestamp)) latest = Math.max(latest, timestamp)
  }
  return latest
}

function unresolvedIssueCount(shelfKey, items, progress, removalProgress) {
  let count = 0
  for (const item of Array.isArray(items) ? items : []) {
    if (item?.shelf_key !== shelfKey) continue
    if (item?.expected_action === "thao_tem") {
      const state = removalProgress?.[item?.removal_key]
      if (state?.state === "still_present" || state?.state === "not_found") count += 1
      continue
    }
    const state = progress?.[item?.check_key]
    if ((state?.state === "fail" || state?.state === "review") && !state?.resolved) count += 1
  }
  return count
}

function locationReason(shelf) {
  const locations = Array.isArray(shelf?.locations) ? shelf.locations.filter(Boolean) : []
  if (!locations.length) return ""
  const first = locations.slice(0, 2).join(" · ")
  return locations.length > 2 ? `${first} · +${locations.length - 2} vị trí` : first
}

/**
 * Build the focus-state shelf directory.
 *
 * The search field is also a browse entry point: focusing it with an empty query
 * must expose a ready-to-tap shelf list, not only a handful of recommendations.
 * Rows remain progress-aware and are ordered for store work:
 * removal -> in-progress -> unresolved issues -> untouched -> completed.
 */
export function smartShelfSuggestions(shelves, items, getStats, progress = {}, removalProgress = {}, {limit=7, browseLimit=60} = {}) {
  const rows = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = getStats(shelf.shelf_key)
    return {
      shelf,
      stats,
      order,
      status:shelfStatus(stats),
      lastCheckedAt:lastCheckedAtForShelf(shelf.shelf_key, items, progress, removalProgress),
      unresolvedIssues:unresolvedIssueCount(shelf.shelf_key, items, progress, removalProgress),
    }
  })
  const result = []
  const seen = new Set()
  const highlightFloor = Math.max(1, Number(limit) || 7)
  const maxBrowse = Math.max(highlightFloor, Math.min(rows.length, Math.max(1, Number(browseLimit) || 60)))
  const add = (row, kind, label, reason) => {
    if (!row || seen.has(row.shelf.shelf_key) || result.length >= maxBrowse) return
    seen.add(row.shelf.shelf_key)
    result.push({...row, kind, label, reason})
  }

  const dueRemoval = rows
    .filter(row => row.stats.removePending > 0)
    .sort((a,b) => b.stats.removePending - a.stats.removePending || b.lastCheckedAt - a.lastCheckedAt || a.order - b.order)
  for (const row of dueRemoval) {
    const loc = locationReason(row.shelf)
    add(row, "remove", "Cần tháo trước", `${row.stats.removePending} tem cần tháo${loc ? ` · ${loc}` : ""}`)
  }

  const inProgress = rows
    .filter(row => row.stats.removePending === 0 && row.stats.remaining > 0 && row.stats.checked > 0)
    .sort((a,b) => b.lastCheckedAt - a.lastCheckedAt || b.stats.checked - a.stats.checked || a.order - b.order)
  inProgress.forEach((row, index) => {
    const loc = locationReason(row.shelf)
    add(row, "resume", index === 0 ? "Tiếp tục đang kiểm" : "Đang kiểm dở", `${row.stats.checked}/${row.stats.total} action · còn ${row.stats.remaining}${loc ? ` · ${loc}` : ""}`)
  })

  const issues = rows
    .filter(row => row.unresolvedIssues > 0 && !seen.has(row.shelf.shelf_key))
    .sort((a,b) => b.unresolvedIssues - a.unresolvedIssues || b.lastCheckedAt - a.lastCheckedAt || a.order - b.order)
  for (const row of issues) {
    const loc = locationReason(row.shelf)
    add(row, "issue", "Cần quay lại", `${row.unresolvedIssues} Sai/Review chưa xử lý${loc ? ` · ${loc}` : ""}`)
  }

  const untouched = rows
    .filter(row => row.stats.removePending === 0 && row.stats.checked === 0 && row.stats.remaining > 0 && !seen.has(row.shelf.shelf_key))
    .sort((a,b) => a.order - b.order)
  for (const row of untouched) {
    const loc = locationReason(row.shelf)
    add(row, "todo", "Chưa kiểm", `${row.stats.total} action${loc ? ` · ${loc}` : ""}`)
  }

  const remaining = rows
    .filter(row => row.stats.remaining > 0 && !seen.has(row.shelf.shelf_key))
    .sort((a,b) => a.order - b.order)
  for (const row of remaining) {
    const loc = locationReason(row.shelf)
    add(row, "next", "Nên kiểm tiếp", `${row.stats.checked}/${row.stats.total} action · còn ${row.stats.remaining}${loc ? ` · ${loc}` : ""}`)
  }

  const completed = rows
    .filter(row => !seen.has(row.shelf.shelf_key))
    .sort((a,b) => a.order - b.order)
  for (const row of completed) {
    const loc = locationReason(row.shelf)
    add(row, "done", "Đã xong", `${row.stats.total} action đã hoàn thành${loc ? ` · ${loc}` : ""}`)
  }

  return result
}

export function nextShelfKey(shelves, progressStatsByKey, {excludeKey=""} = {}) {
  const rows = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = progressStatsByKey(shelf.shelf_key)
    const status = shelfStatus(stats)
    return {shelf, stats, status, priority:shelfPriority(status, stats), order}
  }).filter(row => row.shelf.shelf_key !== excludeKey && (row.stats.remaining > 0 || row.stats.removePending > 0))
  rows.sort((a,b) => a.priority - b.priority || b.stats.removePending - a.stats.removePending || b.stats.checked - a.stats.checked || a.order - b.order)
  return rows[0]?.shelf?.shelf_key || ""
}
