export const SHELF_FILTERS = [
  {key:"todo", label:"Cần kiểm"},
  {key:"all", label:"Tất cả"},
  {key:"issues", label:"Có lỗi"},
  {key:"done", label:"Đã xong"},
]

function normalizeText(value) {
  return String(value || "").trim().toLocaleLowerCase("vi")
}

export function shelfSearchHaystack(shelf, items = []) {
  const shelfItems = items.filter(item => item?.shelf_key === shelf?.shelf_key)
  return normalizeText([
    shelf?.shelf_label,
    shelf?.shelf_key,
    ...shelfItems.flatMap(item => [item?.pog_code, item?.location_id, item?.item_id, item?.item_name]),
  ].filter(Boolean).join(" "))
}

export function shelfStatus(stats) {
  if (!stats || !stats.total) return "todo"
  if (stats.fail || stats.review) return "issues"
  if (stats.remaining === 0) return "done"
  return "todo"
}

export function smartShelfList(shelves, items, getStats, {query="", filter="todo", limit=12} = {}) {
  const needle = normalizeText(query)
  const ranked = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = getStats(shelf.shelf_key)
    const status = shelfStatus(stats)
    const haystack = shelfSearchHaystack(shelf, items)
    const matchesQuery = !needle || haystack.includes(needle)
    const matchesFilter = filter === "all" || status === filter || (filter === "todo" && status !== "done")
    const priority = status === "issues" ? 0 : stats.checked > 0 && stats.remaining > 0 ? 1 : status === "todo" ? 2 : 3
    return {shelf, stats, status, order, priority, matchesQuery, matchesFilter}
  }).filter(row => row.matchesQuery && row.matchesFilter)

  ranked.sort((a,b) => a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order)
  const safeLimit = needle ? ranked.length : Math.max(1, Number(limit) || 12)
  return {rows: ranked.slice(0, safeLimit), totalMatches: ranked.length}
}

export function nextShelfKey(shelves, progressStatsByKey) {
  const rows = (Array.isArray(shelves) ? shelves : []).map((shelf, order) => {
    const stats = progressStatsByKey(shelf.shelf_key)
    const status = shelfStatus(stats)
    const priority = status === "issues" ? 0 : stats.checked > 0 && stats.remaining > 0 ? 1 : status === "todo" ? 2 : 3
    return {shelf, stats, status, priority, order}
  }).filter(row => row.stats.remaining > 0)
  rows.sort((a,b) => a.priority - b.priority || b.stats.checked - a.stats.checked || a.order - b.order)
  return rows[0]?.shelf?.shelf_key || ""
}
