export const SHELF_FILTERS = [
  {key:"todo", label:"Cần kiểm"},
  {key:"all", label:"Tất cả"},
  {key:"issues", label:"Có lỗi"},
  {key:"done", label:"Đã xong"},
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
  if (needle.length >= 4) {
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
  const technical = [shelf?.shelf_label, shelf?.shelf_key, shelf?.pog_code, shelf?.location_id].filter(Boolean)
  const itemParts = shelfItems.flatMap(item => [item?.pog_code, item?.location_id, item?.item_id, item?.item_name]).filter(Boolean)
  return {technical, itemParts, shelfItems}
}

export function shelfSearchHaystack(shelf, items = []) {
  const {technical, itemParts} = searchableParts(shelf, items)
  return normalizeText([...technical, ...itemParts].join(" "))
}

function searchShelf(shelf, items, query) {
  const needle = normalizeText(query)
  if (!needle) return {matches:true, score:0, matchHint:""}
  const compactNeedle = compactText(query)
  const {technical, itemParts, shelfItems} = searchableParts(shelf, items)
  const normalizedTechnical = technical.map(normalizeText)
  const normalizedItems = itemParts.map(normalizeText)
  const allParts = [...normalizedTechnical, ...normalizedItems]
  const compactParts = [...technical, ...itemParts].map(compactText)

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
      matchHint = [item?.item_id, item?.item_name].filter(Boolean).join(" · ")
      if (matchHint) matchHint = `Có ${matchHint}`
      break
    }
  }
  return {matches:true, score, matchHint}
}

export function shelfStatus(stats) {
  if (!stats || !stats.total) return "todo"
  if (stats.fail || stats.review) return "issues"
  if (stats.remaining === 0) return "done"
  return "todo"
}

function shelfPriority(status, stats) {
  return status === "issues" ? 0 : stats.checked > 0 && stats.remaining > 0 ? 1 : status === "todo" ? 2 : 3
}

export function smartShelfList(shelves, items, getStats, {query="", filter="todo", limit=12, searchLimit=8} = {}) {
  const needle = normalizeText(query)
  const ranked = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = getStats(shelf.shelf_key)
    const status = shelfStatus(stats)
    const search = searchShelf(shelf, items, query)
    const matchesFilter = filter === "all" || status === filter || (filter === "todo" && (needle ? true : status !== "done"))
    return {shelf, stats, status, order, priority:shelfPriority(status, stats), matchesQuery:search.matches, matchesFilter, matchScore:search.score, matchHint:search.matchHint}
  }).filter(row => row.matchesQuery && row.matchesFilter)

  ranked.sort((a,b) => needle
    ? b.matchScore - a.matchScore || a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order
    : a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order)
  const safeLimit = needle ? Math.max(1, Number(searchLimit) || 8) : Math.max(1, Number(limit) || 12)
  return {rows: ranked.slice(0, safeLimit), totalMatches: ranked.length}
}

function lastCheckedAtForShelf(shelfKey, items, progress) {
  let latest = 0
  for (const item of Array.isArray(items) ? items : []) {
    if (item?.shelf_key !== shelfKey) continue
    const timestamp = Date.parse(progress?.[item?.check_key]?.checkedAt || "")
    if (Number.isFinite(timestamp)) latest = Math.max(latest, timestamp)
  }
  return latest
}

function unresolvedIssueCount(shelfKey, items, progress) {
  let count = 0
  for (const item of Array.isArray(items) ? items : []) {
    if (item?.shelf_key !== shelfKey) continue
    const state = progress?.[item?.check_key]
    if ((state?.state === "fail" || state?.state === "review") && !state?.resolved) count += 1
  }
  return count
}

export function smartShelfSuggestions(shelves, items, getStats, progress = {}, {limit=7} = {}) {
  const rows = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = getStats(shelf.shelf_key)
    return {
      shelf,
      stats,
      order,
      status:shelfStatus(stats),
      lastCheckedAt:lastCheckedAtForShelf(shelf.shelf_key, items, progress),
      unresolvedIssues:unresolvedIssueCount(shelf.shelf_key, items, progress),
    }
  })
  const result = []
  const seen = new Set()
  const maxSuggestions = Math.max(1, Number(limit) || 7)
  const add = (row, kind, label, reason) => {
    if (!row || seen.has(row.shelf.shelf_key) || result.length >= maxSuggestions) return
    seen.add(row.shelf.shelf_key)
    result.push({...row, kind, label, reason})
  }

  const inProgress = rows
    .filter(row => row.stats.remaining > 0 && row.stats.checked > 0)
    .sort((a,b) => b.lastCheckedAt - a.lastCheckedAt || b.stats.checked - a.stats.checked || a.order - b.order)
  const recent = inProgress[0] || null
  if (recent) add(recent, "resume", "Tiếp tục đang kiểm", `${recent.stats.checked}/${recent.stats.total} action · còn ${recent.stats.remaining}`)

  const remaining = rows.filter(row => row.stats.remaining > 0)
  const anchor = recent ? recent.order : -1
  const orderedAfter = [...remaining]
    .filter(row => !seen.has(row.shelf.shelf_key))
    .sort((a,b) => {
      const da = a.order > anchor ? a.order - anchor : a.order + rows.length - anchor
      const db = b.order > anchor ? b.order - anchor : b.order + rows.length - anchor
      return da - db
    })
  const firstNext = orderedAfter[0] || null
  add(firstNext, "next", "Nên kiểm tiếp", firstNext?.stats.checked ? `${firstNext.stats.checked}/${firstNext.stats.total} action · còn ${firstNext.stats.remaining}` : `${firstNext?.stats.total || 0} action · chưa kiểm`)

  const almostDone = [...rows]
    .filter(row => row.stats.remaining > 0 && row.stats.checked > 0 && row.stats.remaining <= 3 && !seen.has(row.shelf.shelf_key))
    .sort((a,b) => a.stats.remaining - b.stats.remaining || b.lastCheckedAt - a.lastCheckedAt)
  for (const row of almostDone) add(row, "almost", "Sắp xong", `Chỉ còn ${row.stats.remaining} action`)

  const issues = [...rows]
    .filter(row => row.unresolvedIssues > 0 && !seen.has(row.shelf.shelf_key))
    .sort((a,b) => b.unresolvedIssues - a.unresolvedIssues || b.lastCheckedAt - a.lastCheckedAt)
  for (const row of issues) add(row, "issue", "Cần quay lại", `${row.unresolvedIssues} Sai/Review chưa xử lý`)

  const secondNext = orderedAfter.find(row => !seen.has(row.shelf.shelf_key)) || null
  add(secondNext, "next", "Nên kiểm tiếp", secondNext?.stats.checked ? `${secondNext.stats.checked}/${secondNext.stats.total} action · còn ${secondNext.stats.remaining}` : `${secondNext?.stats.total || 0} action · chưa kiểm`)

  for (const row of inProgress) add(row, "resume", "Đang kiểm dở", `${row.stats.checked}/${row.stats.total} action · còn ${row.stats.remaining}`)

  const untouched = rows.filter(row => row.stats.checked === 0 && row.stats.remaining > 0 && !seen.has(row.shelf.shelf_key))
  for (const row of untouched) add(row, "todo", "Chưa kiểm", `${row.stats.total} action`)

  return result
}

export function nextShelfKey(shelves, progressStatsByKey) {
  const rows = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = progressStatsByKey(shelf.shelf_key)
    const status = shelfStatus(stats)
    return {shelf, stats, status, priority:shelfPriority(status, stats), order}
  }).filter(row => row.stats.remaining > 0)
  rows.sort((a,b) => a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order)
  return rows[0]?.shelf?.shelf_key || ""
}
