import React, { useEffect, useMemo, useState } from "react"
import ProductNav from "./ProductNav.jsx"
import { cacheUploadedWorkbook, readCachedWorkbook } from "./tag-audit-context-cache.js"
import {
  SHELF_FAIL_REASONS,
  buildShelfCameraUrl,
  extraTagStorageKey,
  firstUncheckedIndex,
  markExtraResolved,
  markResolved,
  normalizeExtraTags,
  normalizeProgress,
  normalizeRemovalProgress,
  progressStats,
  progressStorageKey,
  recordDecision,
  recordRemovalDecision,
  removalStorageKey,
  resetProgressForItems,
  resetRemovalToday,
  resetRemovalTodayForItems,
  shelfStats,
} from "./tag-audit-shelf-progress.js"
import {
  SHELF_FILTERS,
  nextShelfKey,
  smartShelfList,
  smartShelfSuggestions,
} from "./tag-audit-shelf-list.js"

const SESSION_KEY = "ctkm.shelf.session.v1"
const INITIAL_SHELF_LIMIT = 12

async function apiJson(url, options = {}) {
  const response = await fetch(url, options)
  let data = null
  try { data = await response.json() } catch {}
  if (!response.ok) {
    const error = new Error(typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`)
    error.status = response.status
    throw error
  }
  return data
}

function formatMoney(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return "—"
  return `${Math.round(number).toLocaleString("vi-VN")}đ`
}

function formatDate(value) {
  const text = String(value || "").trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}/${match[2]}` : text || "—"
}

function readStored(key, normalizer, fallback) {
  if (!key) return fallback
  try { return normalizer(JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback))) } catch { return fallback }
}

function writeStored(key, value) {
  if (!key) return
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

function ProgressBar({ stats }) {
  const percent = stats.total ? Math.round(stats.checked * 100 / stats.total) : 0
  return <div className="shelf-progress-wrap">
    <div className="shelf-progress-label"><strong>{stats.checked} / {stats.total} action đã kiểm</strong><span>Còn {stats.remaining} lượt{stats.removePending ? ` · ${stats.removePending} cần tháo` : ""} · {percent}%</span></div>
    <div className="shelf-progress-track"><div className="shelf-progress-fill" style={{width:`${percent}%`}} /></div>
  </div>
}

function suggestionTone(kind) {
  if (kind === "remove") return "remove"
  if (kind === "resume") return "resume"
  if (kind === "issue") return "issue"
  if (kind === "almost") return "almost"
  return "next"
}

function removalLabel(state) {
  if (state === "removed") return "Đã tháo"
  if (state === "still_present") return "Vẫn còn tem"
  if (state === "not_found") return "Không tìm thấy"
  return "Chưa xử lý"
}

export default function TagAuditShelfCheck() {
  const [session, setSession] = useState(null)
  const [progress, setProgress] = useState({})
  const [removalProgress, setRemovalProgress] = useState({})
  const [extraTags, setExtraTags] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [view, setView] = useState("shelves")
  const [shelfKey, setShelfKey] = useState("")
  const [index, setIndex] = useState(0)
  const [showReasons, setShowReasons] = useState(false)
  const [note, setNote] = useState("")
  const [shelfQuery, setShelfQuery] = useState("")
  const [shelfFilter, setShelfFilter] = useState("todo")
  const [shelfLimit, setShelfLimit] = useState(INITIAL_SHELF_LIMIT)
  const [searchFocused, setSearchFocused] = useState(false)
  const [showProgressMenu, setShowProgressMenu] = useState(false)
  const [extraDraft, setExtraDraft] = useState({item_id:"",item_name:"",shelf_key:"",note:""})
  const [extraError, setExtraError] = useState("")

  const items = Array.isArray(session?.items) ? session.items : []
  const shelves = Array.isArray(session?.shelves) ? session.shelves : []
  const overall = useMemo(() => progressStats(items, progress, removalProgress), [items, progress, removalProgress])
  const activePass = Math.max(0, overall.pass - overall.removed)
  const shelfItems = useMemo(() => items.filter(item => item.shelf_key === shelfKey), [items, shelfKey])
  const current = shelfItems[index] || null
  const currentRemoval = current?.expected_action === "thao_tem" ? removalProgress[current?.removal_key] : null

  const taskFailures = useMemo(() => items.flatMap(item => {
    if (item.expected_action === "thao_tem") {
      const state = removalProgress[item.removal_key]
      if (state?.state === "still_present" || state?.state === "not_found") return [{item, state, kind:"remove"}]
      return []
    }
    const state = progress[item.check_key]
    return state && ["fail","review"].includes(state.state) ? [{item, state, kind:"check"}] : []
  }), [items, progress, removalProgress])
  const unresolvedTaskCount = taskFailures.filter(row => row.kind === "remove" || !row.state.resolved).length
  const unresolvedExtraCount = extraTags.filter(row => !row.resolved).length
  const issueCount = unresolvedTaskCount + unresolvedExtraCount

  const shelfStatsByKey = useMemo(() => {
    const result = new Map()
    for (const shelf of shelves) result.set(shelf.shelf_key, shelfStats(items, progress, shelf.shelf_key, removalProgress))
    return result
  }, [shelves, items, progress, removalProgress])
  const getShelfStats = key => shelfStatsByKey.get(key) || {total:0,checked:0,remaining:0,pass:0,fail:0,review:0,attachTotal:0,removeTotal:0,removed:0,removePending:0}
  const nextKey = useMemo(() => nextShelfKey(shelves, getShelfStats), [shelves, shelfStatsByKey])
  const nextAfterCurrent = useMemo(() => nextShelfKey(shelves, getShelfStats, {excludeKey:shelfKey}), [shelves, shelfStatsByKey, shelfKey])
  const nextShelf = shelves.find(shelf => shelf.shelf_key === nextKey) || null
  const smartList = useMemo(
    () => smartShelfList(shelves, items, getShelfStats, {query:shelfQuery, filter:shelfFilter, limit:shelfLimit, searchLimit:8}),
    [shelves, items, shelfStatsByKey, shelfQuery, shelfFilter, shelfLimit],
  )
  const suggestions = useMemo(
    () => smartShelfSuggestions(shelves, items, getShelfStats, progress, removalProgress, {limit:7}),
    [shelves, items, shelfStatsByKey, progress, removalProgress],
  )

  const progressKey = session?.context_id ? progressStorageKey(session.context_id) : ""
  const removalKey = session?.store_scope_id ? removalStorageKey(session.store_scope_id) : ""
  const extraKey = session?.workbook_scope_id ? extraTagStorageKey(session.workbook_scope_id) : ""

  const acceptSession = data => {
    setSession(data)
    const initialProg = readStored(progressStorageKey(data?.context_id), normalizeProgress, {})
    const initialRem = readStored(removalStorageKey(data?.store_scope_id), normalizeRemovalProgress, {})
    setProgress(initialProg)
    setRemovalProgress(initialRem)
    setExtraTags(readStored(extraTagStorageKey(data?.workbook_scope_id), normalizeExtraTags, []))
    if (data?.session_id) localStorage.setItem(SESSION_KEY, data.session_id)
    setShelfQuery(""); setShelfFilter("todo"); setShelfLimit(INITIAL_SHELF_LIMIT); setSearchFocused(false)
    setShowProgressMenu(false); setExtraError(""); setError("")

    const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null
    const targetShelf = urlParams?.get("shelf") || ""
    if (targetShelf && Array.isArray(data?.shelves) && data.shelves.some(s => s.shelf_key === targetShelf)) {
      const targetItems = (Array.isArray(data?.items) ? data.items : []).filter(item => item.shelf_key === targetShelf)
      let resume = firstUncheckedIndex(targetItems, initialProg, 0, initialRem)
      if (resume < 0) {
        resume = targetItems.findIndex(item => item.expected_action === "thao_tem" && initialRem[item.removal_key]?.state !== "removed")
      }
      setShelfKey(targetShelf)
      setIndex(resume >= 0 ? resume : 0)
      setView("check")
    } else {
      setShelfKey("")
    }
  }

  const uploadWorkbook = async file => {
    if (!file) return
    setLoading(true); setError("")
    try {
      const form = new FormData(); form.append("workbook", file)
      const data = await apiJson("/api/tag-audit/shelf/session", {method:"POST", body:form})
      await cacheUploadedWorkbook(file)
      acceptSession(data)
      setView("shelves")
    } catch (err) {
      setError(err.message || "Không đọc được workbook")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const savedId = localStorage.getItem(SESSION_KEY) || ""
      if (savedId) {
        try {
          const data = await apiJson(`/api/tag-audit/shelf/session/${encodeURIComponent(savedId)}`)
          if (!cancelled) { acceptSession(data); setLoading(false); return }
        } catch {}
      }
      const cached = await readCachedWorkbook()
      if (cached?.blob) {
        try {
          const file = new File([cached.blob], cached.name || "ctkm.xlsx", {type:cached.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
          const form = new FormData(); form.append("workbook", file)
          const data = await apiJson("/api/tag-audit/shelf/session", {method:"POST", body:form})
          if (!cancelled) { acceptSession(data); setLoading(false); return }
        } catch {}
      }
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [])

  const persistProgress = next => { setProgress(next); writeStored(progressKey, next) }
  const persistRemoval = next => { setRemovalProgress(next); writeStored(removalKey, next) }
  const persistExtras = next => { setExtraTags(next); writeStored(extraKey, next) }

  const openShelf = key => {
    const target = items.filter(item => item.shelf_key === key)
    let resume = firstUncheckedIndex(target, progress, 0, removalProgress)
    if (resume < 0) {
      resume = target.findIndex(item => item.expected_action === "thao_tem" && removalProgress[item.removal_key]?.state !== "removed")
    }
    setShelfKey(key)
    setIndex(resume >= 0 ? resume : 0)
    setShowReasons(false); setNote(""); setSearchFocused(false); setShowProgressMenu(false)
    setView("check")
  }

  const advanceAfter = (nextProgress, nextRemoval) => {
    const next = firstUncheckedIndex(shelfItems, nextProgress, index + 1, nextRemoval)
    setShowReasons(false); setNote("")
    if (next >= 0) setIndex(next)
    else setView("shelfDone")
  }

  const decide = (state, reason = "") => {
    if (!current) return
    const next = recordDecision(progress, current.check_key, state, reason, note)
    persistProgress(next)
    advanceAfter(next, removalProgress)
  }

  const decideRemoval = state => {
    if (!current?.removal_key) return
    const next = recordRemovalDecision(removalProgress, current.removal_key, state, note)
    persistRemoval(next)
    advanceAfter(progress, next)
  }

  const reopenFailure = item => {
    const target = items.filter(row => row.shelf_key === item.shelf_key)
    const targetIndex = Math.max(0, target.findIndex(row => row.task_key === item.task_key))
    setShelfKey(item.shelf_key); setIndex(targetIndex); setShowReasons(false); setNote(""); setSearchFocused(false)
    setView("check")
  }

  const resetShelf = () => {
    if (!shelfKey) return
    if (!window.confirm("Reset lượt kiểm hôm nay của kệ này? Các tem đã xác nhận ĐÃ THÁO vẫn được giữ.")) return
    const target = items.filter(item => item.shelf_key === shelfKey)
    const nextProgress = resetProgressForItems(progress, target)
    const nextRemoval = resetRemovalTodayForItems(removalProgress, target)
    persistProgress(nextProgress); persistRemoval(nextRemoval)
    setIndex(Math.max(0, firstUncheckedIndex(target, nextProgress, 0, nextRemoval)))
    setShowProgressMenu(false); setView("check")
  }

  const resetToday = () => {
    if (!window.confirm("Reset toàn bộ tiến độ kiểm HÔM NAY? Lịch sử ĐÃ THÁO và các báo cáo tem dư vẫn được giữ.")) return
    const nextRemoval = resetRemovalToday(removalProgress)
    persistProgress({}); persistRemoval(nextRemoval)
    setShowProgressMenu(false); setView("shelves")
  }

  const clearAllForWorkbook = () => {
    if (!window.confirm("XÓA TOÀN BỘ tiến độ của file này? Bao gồm xác nhận ĐÃ THÁO cho các action trong file và báo cáo tem dư. Không thể hoàn tác.")) return
    const currentRemovalKeys = new Set(items.filter(item => item.expected_action === "thao_tem").map(item => item.removal_key))
    const keptRemoval = Object.fromEntries(Object.entries(removalProgress).filter(([key]) => !currentRemovalKeys.has(key)))
    try { localStorage.removeItem(progressKey); localStorage.removeItem(extraKey) } catch {}
    persistRemoval(keptRemoval)
    setProgress({}); setExtraTags([]); setShowProgressMenu(false); setView("shelves")
  }

  const openExtraReport = (preferredShelf = "") => {
    setExtraDraft({item_id:"",item_name:"",shelf_key:preferredShelf,note:""})
    setExtraError(""); setShowProgressMenu(false); setView("extra")
  }

  const saveExtraReport = () => {
    const itemId = String(extraDraft.item_id || "").trim().toUpperCase()
    let itemName = String(extraDraft.item_name || "").trim()
    let targetShelfKey = String(extraDraft.shelf_key || "").trim()
    const known = itemId ? items.find(item => String(item.item_id || "").trim().toUpperCase() === itemId) : null
    if (!itemName && known?.item_name) itemName = String(known.item_name)
    if (!targetShelfKey && known?.shelf_key) targetShelfKey = known.shelf_key
    if (!itemId && !itemName) { setExtraError("Nhập ITEMID hoặc tên sản phẩm để ghi nhận tem dư."); return }
    const shelf = shelves.find(row => row.shelf_key === targetShelfKey)
    const record = {
      id:`extra_${Date.now()}_${Math.random().toString(36).slice(2,8)}`,
      item_id:itemId,
      item_name:itemName,
      shelf_key:targetShelfKey,
      shelf_label:shelf?.shelf_label || "Chưa xác định kệ",
      note:String(extraDraft.note || "").trim(),
      checkedAt:new Date().toISOString(),
      resolved:false,
    }
    persistExtras([...extraTags, record])
    setExtraError(""); setView("errors")
  }

  if (loading) return <><style>{styles}</style><ProductNav current="shelf"/><div className="shelf-shell"><div className="shelf-loading">Đang mở Kiểm toàn kệ…</div></div></>

  if (!session) return <><style>{styles}</style><ProductNav current="shelf"/><div className="shelf-shell">
    <header className="shelf-head"><div><span className="shelf-kicker">CTKM · VẬN HÀNH CỬA HÀNG</span><h1>Kiểm toàn kệ</h1><p>Kiểm tem đang chạy, tháo tem hết hạn và lưu tiến độ ngay trên thiết bị.</p></div></header>
    <main className="shelf-upload-card">
      <div className="shelf-upload-icon">▤</div><h2>Tải workbook CTKM</h2>
      <p>Không cần tài khoản Admin. Phiên kiểm kệ tách riêng khỏi cấu hình Admin.</p>
      <label className="shelf-upload-button">Chọn file .xlsx<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event=>uploadWorkbook(event.target.files?.[0])} /></label>
      {error && <div className="shelf-error">{error}</div>}
      <a className="shelf-subtle-link" href="/">← Chức năng khác</a>
    </main>
  </div></>

  return <><style>{styles}</style><ProductNav current="shelf"/><div className="shelf-shell">
    <header className="shelf-sticky">
      <div className="shelf-topline">
        <button onClick={()=>{setView("shelves");setSearchFocused(false);setShowProgressMenu(false)}}>☰ Kệ</button>
        <strong>Kiểm toàn kệ</strong>
        <div className="shelf-head-actions"><button onClick={()=>openExtraReport(shelfKey)}>+ Tem dư</button><button onClick={()=>setShowProgressMenu(value=>!value)}>⋮ Tiến độ</button><button onClick={()=>{setView("errors");setSearchFocused(false);setShowProgressMenu(false)}}>Sai & Review <b>{issueCount}</b></button></div>
      </div>
      <ProgressBar stats={overall} />
      {showProgressMenu && <div className="shelf-progress-menu">
        {shelfKey && <button onClick={resetShelf}>↺ Reset kệ hiện tại <small>Giữ các tem đã tháo</small></button>}
        <button onClick={resetToday}>↺ Reset tiến độ hôm nay <small>Giữ lịch sử đã tháo + tem dư</small></button>
        <button className="danger" onClick={clearAllForWorkbook}>🗑 Xóa toàn bộ tiến độ file này <small>Bao gồm xác nhận đã tháo trong file</small></button>
      </div>}
    </header>

    {view === "shelves" && <main className="shelf-main">
      <section className="shelf-mission">
        <div className="shelf-mission-copy">
          <span>KIỂM KỆ HÔM NAY</span>
          <h1>Đi theo kệ, xử lý từng việc một</h1>
          <p>Ưu tiên kệ cần tháo hoặc cần quay lại. Tiến độ lưu ngay trên thiết bị, không phụ thuộc camera.</p>
        </div>
        <div className="shelf-mission-cute" aria-hidden="true">
          <div className="shelf-chibi"><i>•ᴗ•</i><b>✓</b></div>
          <small>Camera chỉ là Beta ✦</small>
        </div>
      </section>
      <div className="shelf-summary-row five">
        <div className="remove"><span>Cần tháo</span><strong>{overall.removePending}</strong></div>
        <div><span>Đã tháo</span><strong>{overall.removed}</strong></div>
        <div><span>Đúng</span><strong>{activePass}</strong></div>
        <div><span>Sai/Review</span><strong>{overall.fail + overall.review + unresolvedExtraCount}</strong></div>
        <div><span>Còn lượt</span><strong>{overall.remaining}</strong></div>
      </div>
      <div className="shelf-section-title"><div><h2>Tìm hoặc chọn kệ</h2><p>POG là nhóm chính; vị trí bên trong chỉ là mốc dẫn đường. Bấm ô tìm để hệ thống tự gợi ý.</p></div><label className="shelf-change-file">Đổi file<input type="file" accept=".xlsx" onChange={event=>uploadWorkbook(event.target.files?.[0])} /></label></div>

      {nextShelf && !searchFocused && <button className={`shelf-continue ${getShelfStats(nextShelf.shelf_key).removePending ? "remove" : ""}`} onClick={()=>openShelf(nextShelf.shelf_key)}>
        <span>{getShelfStats(nextShelf.shelf_key).removePending ? "🔴 Ưu tiên tháo" : "▶ Tiếp tục nhanh"}</span><strong>{nextShelf.shelf_label}</strong><small>{getShelfStats(nextShelf.shelf_key).removePending ? `${getShelfStats(nextShelf.shelf_key).removePending} tem cần tháo` : `${getShelfStats(nextShelf.shelf_key).checked}/${getShelfStats(nextShelf.shelf_key).total} action · còn ${getShelfStats(nextShelf.shelf_key).remaining}`}</small>
      </button>}

      <div className={`shelf-search-box ${searchFocused ? "focused" : ""}`}>
        <span>⌕</span><input value={shelfQuery} onFocus={()=>setSearchFocused(true)} onKeyDown={event=>{if(event.key === "Escape") setSearchFocused(false)}} onChange={event=>{setShelfQuery(event.target.value);setShelfLimit(INITIAL_SHELF_LIMIT)}} placeholder="Bấm để xem gợi ý, hoặc gõ P25860, tên SP, POG, kệ…" aria-expanded={searchFocused} />
        {shelfQuery ? <button onClick={()=>setShelfQuery("")} aria-label="Xóa tìm kiếm">×</button> : searchFocused ? <button onClick={()=>setSearchFocused(false)} aria-label="Đóng gợi ý">⌃</button> : null}
      </div>

      {searchFocused && !shelfQuery && <section className="shelf-suggest-panel">
        <div className="shelf-suggest-head"><div><strong>Gợi ý cho bạn</strong><span>Dựa trên tiến độ và tem cần tháo ngay lúc này</span></div><b>{suggestions.length}</b></div>
        {!suggestions.length ? <div className="shelf-suggest-empty">Không còn kệ cần gợi ý.</div> : <div className="shelf-suggest-list">{suggestions.map(({shelf,stats,kind,label,reason,unresolvedIssues}) => <button key={`${kind}:${shelf.shelf_key}`} className={`shelf-suggest-item ${suggestionTone(kind)}`} onClick={()=>openShelf(shelf.shelf_key)}>
          <div className="shelf-suggest-copy"><span>{label}</span><strong>{shelf.shelf_label}</strong><small>{reason}</small></div>
          <div className="shelf-suggest-side"><b>{kind === "remove" ? stats.removePending : stats.remaining}</b><small>{kind === "remove" ? "cần tháo" : "còn"}</small>{unresolvedIssues ? <em>{unresolvedIssues} lỗi</em> : null}</div>
        </button>)}</div>}
      </section>}

      <div className="shelf-filter-row shelf-status-tabs">{SHELF_FILTERS.map(option => <button key={option.key} className={shelfFilter===option.key?"active":""} onClick={()=>{setShelfFilter(option.key);setShelfLimit(INITIAL_SHELF_LIMIT)}}>{option.label}</button>)}</div>
      <div className="shelf-list-caption">{shelfQuery ? `${smartList.totalMatches} kệ khớp · hiện tối đa 8 kết quả tốt nhất` : `${smartList.totalMatches} kệ phù hợp${smartList.totalMatches > smartList.rows.length ? ` · đang hiện ${smartList.rows.length}` : ""}`}</div>

      {!smartList.rows.length ? <div className="shelf-empty">Không tìm thấy kệ phù hợp. Thử ITEMID, tên sản phẩm, POG hoặc vị trí kệ.</div> : <div className="shelf-grid">{smartList.rows.map(({shelf,stats,status,matchHint}) => {
        const done = status === "done"
        const remove = stats.removePending > 0
        return <button key={shelf.shelf_key} className={`shelf-card ${done ? "done" : ""} ${status === "issues" ? "issue" : ""} ${remove ? "remove" : ""}`} onClick={()=>openShelf(shelf.shelf_key)}>
          <div className="shelf-card-top"><strong>{shelf.shelf_label}</strong><span>{remove ? `🔴 ${stats.removePending} cần tháo` : done ? "✓ Hoàn tất" : status === "issues" ? "↺ Cần quay lại" : stats.checked ? "▶ Đang kiểm" : "Chưa kiểm"}</span></div>
          <div className="shelf-card-count"><b>{stats.checked}/{stats.total}</b> action · {shelf.sku_count} SKU · {shelf.location_count || 0} vị trí</div>
          {shelf.shelf_group_mode === "pog" && shelf.locations?.length ? <div className="shelf-locations">{shelf.locations.slice(0,4).join(" · ")}{shelf.locations.length > 4 ? ` · +${shelf.locations.length-4}` : ""}</div> : null}
          {shelfQuery && matchHint ? <div className="shelf-match-hint">{matchHint}</div> : null}
          <div className="shelf-mini-track"><i style={{width:`${stats.total ? Math.round(stats.checked*100/stats.total) : 0}%`}} /></div>
          {(stats.fail || stats.review) ? <div className="shelf-card-warn">Sai {stats.fail} · Review {stats.review}</div> : null}
        </button>
      })}</div>}
      {!shelfQuery && smartList.totalMatches > smartList.rows.length && <button className="shelf-more" onClick={()=>setShelfLimit(value=>value+12)}>Xem thêm {Math.min(12,smartList.totalMatches-smartList.rows.length)} kệ</button>}
    </main>}

    {view === "check" && current && <main className="shelf-check-main">
      <div className="shelf-check-head"><button onClick={()=>setView("shelves")}>← Danh sách kệ</button><div><strong>{current.shelf_label}</strong><span>{index+1} / {shelfItems.length}</span></div></div>
      <div className="shelf-location-banner">📍 {current.location_id ? `Vị trí ${current.location_id}` : "Chưa có vị trí"}{current.facing ? ` · Facing ${current.facing}` : ""}</div>
      <article className={`shelf-product-card ${current.expected_action === "thao_tem" ? "remove" : ""}`}>
        <div className="shelf-id-row"><strong>{current.item_id || "—"}</strong><span>{current.promo_uom || ""}</span></div>
        <h2>{current.item_name || "Tên sản phẩm chưa có"}</h2>
        <div className="shelf-promo-name">{current.campaign_name || current.campaign_detail || "CTKM"}</div>
        {current.campaign_detail && current.campaign_name && <div className="shelf-detail">{current.campaign_detail}</div>}
        {current.expected_action === "thao_tem" ? <div className="shelf-remove-box"><span>🔴 TEM HẾT HẠN — CẦN THÁO</span><strong>Hết CTKM {formatDate(current.promo_to)}</strong><small>Giá trên tem: {formatMoney(current.promo_price)}</small></div> : <div className="shelf-expected"><span>Tem cần thấy</span><strong>{formatMoney(current.promo_price)}</strong><b>{formatDate(current.promo_from)} → {formatDate(current.promo_to)}</b></div>}
        <div className="shelf-meta">{[current.key_channel,current.channel].filter(Boolean).join(" · ") || ""}</div>
      </article>

      {current.expected_action === "thao_tem" ? <div className="shelf-removal-actions">
        <textarea value={note} onChange={event=>setNote(event.target.value)} placeholder="Ghi chú nếu cần…" rows="2" />
        <button className="shelf-pass" onClick={()=>decideRemoval("removed")}>✓ ĐÃ THÁO</button>
        <button className="shelf-fail" onClick={()=>decideRemoval("still_present")}>✕ VẪN CÒN TEM</button>
        <button className="shelf-review" onClick={()=>decideRemoval("not_found")}>? KHÔNG TÌM THẤY</button>
      </div> : !showReasons ? <div className="shelf-actions">
        <button className="shelf-pass" onClick={()=>decide("pass")}>✓ ĐÚNG</button>
        <button className="shelf-fail" onClick={()=>setShowReasons(true)}>✕ SAI</button>
        <button className="shelf-review" onClick={()=>decide("review","Không chắc")}>? Không chắc / Review</button>
      </div> : <div className="shelf-reasons">
        <div className="shelf-reason-head"><strong>Sai vì lý do gì?</strong><button onClick={()=>{setShowReasons(false);setNote("")}}>Đóng</button></div>
        <textarea value={note} onChange={event=>setNote(event.target.value)} placeholder="Ghi chú nếu cần…" rows="2" />
        <div className="shelf-reason-grid">{SHELF_FAIL_REASONS.map(reason=><button key={reason} onClick={()=>decide("fail",reason)}>{reason}</button>)}</div>
      </div>}
      <div className="shelf-current-state">{current.expected_action === "thao_tem" ? `Trạng thái: ${removalLabel(currentRemoval?.state)}` : progress[current.check_key] ? `Đã lưu: ${progress[current.check_key].state === "pass" ? "Đúng" : progress[current.check_key].reason || "Review"}` : "Chưa kiểm"}</div>
      <a className="shelf-camera-beta" href={buildShelfCameraUrl(current?.shelf_key, current?.item_id, current?.check_key)}>📷 Quét nhanh (Beta) · chỉ hỗ trợ tìm/đọc tem</a>
    </main>}

    {view === "shelfDone" && <main className="shelf-done">
      {(() => { const stats=shelfStats(items,progress,shelfKey,removalProgress); const pending=stats.removePending>0; return <>
        <div className={`shelf-done-icon ${pending ? "warn" : ""}`}>{pending ? "!" : "✓"}</div><h2>{pending ? "Đã kiểm xong lượt" : "Đã kiểm xong kệ"}</h2><h3>{shelfItems[0]?.shelf_label || ""}</h3>
        <p>{stats.total} action · Đúng/Đã tháo {stats.pass} · Sai {stats.fail} · Review {stats.review}{pending ? ` · còn ${stats.removePending} tem phải tháo` : ""}</p>
        {nextAfterCurrent ? <button className="shelf-primary" onClick={()=>openShelf(nextAfterCurrent)}>Qua kệ ưu tiên tiếp theo →</button> : <button className="shelf-primary" onClick={()=>setView("shelves")}>Về danh sách kệ</button>}
        {pending && <button className="shelf-secondary" onClick={()=>setView("errors")}>Xem tem chưa tháo</button>}
        <button className="shelf-secondary" onClick={()=>setView("errors")}>Xem Sai & Review</button>
      </> })()}
    </main>}

    {view === "extra" && <main className="shelf-main narrow">
      <div className="shelf-section-title"><div><h2>+ Báo tem dư</h2><p>Dùng khi thấy một tem CTKM trên kệ nhưng tem đó không thuộc action cần giữ hiện tại.</p></div></div>
      <div className="shelf-extra-form">
        <label>ITEMID<input value={extraDraft.item_id} onChange={event=>setExtraDraft({...extraDraft,item_id:event.target.value})} placeholder="P25860" /></label>
        <label>Tên sản phẩm<input value={extraDraft.item_name} onChange={event=>setExtraDraft({...extraDraft,item_name:event.target.value})} placeholder="Tên sản phẩm nếu biết" /></label>
        <label>Kệ / POG<select value={extraDraft.shelf_key} onChange={event=>setExtraDraft({...extraDraft,shelf_key:event.target.value})}><option value="">Chưa xác định kệ</option>{shelves.map(shelf=><option key={shelf.shelf_key} value={shelf.shelf_key}>{shelf.shelf_label}</option>)}</select></label>
        <label>Ghi chú<textarea rows="3" value={extraDraft.note} onChange={event=>setExtraDraft({...extraDraft,note:event.target.value})} placeholder="Ví dụ: còn tem cũ GIẢM 15%" /></label>
        {extraError && <div className="shelf-error">{extraError}</div>}
        <button className="shelf-primary" onClick={saveExtraReport}>Lưu tem dư vào Sai & Review</button>
        <button className="shelf-secondary" onClick={()=>setView(shelfKey?"check":"shelves")}>Hủy</button>
      </div>
    </main>}

    {view === "errors" && <main className="shelf-main">
      <div className="shelf-section-title"><div><h2>Sai & Review</h2><p>{issueCount} mục chưa xử lý · gồm sai tem, tem cần tháo chưa xong và tem dư.</p></div><button className="shelf-inline-add" onClick={()=>openExtraReport()}>+ Báo tem dư</button></div>
      {!taskFailures.length && !extraTags.length ? <div className="shelf-empty">Chưa có Sai/Review hoặc tem dư.</div> : <div className="shelf-error-list">
        {taskFailures.map(({item,state,kind}) => <article key={`${kind}:${item.task_key}`} className={`shelf-error-item ${kind === "check" && state.resolved ? "resolved" : ""}`}>
          <div className="shelf-error-item-top"><div><span>{item.shelf_label}{item.location_id ? ` · ${item.location_id}` : ""}</span><strong>{item.item_id} · {item.item_name || ""}</strong></div><b>{kind === "remove" ? removalLabel(state.state) : state.state === "review" ? "Review" : state.reason || "Sai"}</b></div>
          <div className="shelf-error-expected">{kind === "remove" ? `Cần tháo tem hết hạn ${formatDate(item.promo_to)}` : `Chuẩn: ${formatMoney(item.promo_price)} · ${formatDate(item.promo_from)}–${formatDate(item.promo_to)}`}</div>
          {state.note && <div className="shelf-error-note">{state.note}</div>}
          <div className="shelf-error-buttons"><button onClick={()=>reopenFailure(item)}>Kiểm lại</button>{kind === "remove" ? <button onClick={()=>persistRemoval(recordRemovalDecision(removalProgress,item.removal_key,"removed","Đánh dấu đã tháo từ Sai & Review"))}>✓ Đã tháo</button> : <button onClick={()=>persistProgress(markResolved(progress,item.check_key,!state.resolved))}>{state.resolved ? "Đánh dấu chưa sửa" : "✓ Đã sửa"}</button>}</div>
        </article>)}
        {extraTags.map(row => <article key={row.id} className={`shelf-error-item extra ${row.resolved ? "resolved" : ""}`}>
          <div className="shelf-error-item-top"><div><span>{row.shelf_label}</span><strong>{[row.item_id,row.item_name].filter(Boolean).join(" · ") || "Tem dư"}</strong></div><b>Dư tem</b></div>
          <div className="shelf-error-expected">Tem CTKM không thuộc action cần giữ hiện tại.</div>
          {row.note && <div className="shelf-error-note">{row.note}</div>}
          <div className="shelf-error-buttons">{row.shelf_key ? <button onClick={()=>openShelf(row.shelf_key)}>Mở kệ</button> : <button disabled>Chưa có kệ</button>}<button onClick={()=>persistExtras(markExtraResolved(extraTags,row.id,!row.resolved))}>{row.resolved ? "Đánh dấu chưa xử lý" : "✓ Đã xử lý"}</button></div>
        </article>)}
      </div>}
    </main>}
  </div></>
}

const styles = `
:root{--shelf-blue:#1769ff;--shelf-green:#12a86b;--shelf-purple:#8b4de8;--shelf-pink:#fff3f8}
.shelf-mission{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;margin:4px 0 14px;padding:18px 20px;border:1px solid #dfe8f4;border-radius:20px;background:
radial-gradient(circle at 90% 10%,rgba(255,200,225,.42),transparent 28%),
linear-gradient(135deg,#fff,#f7fbff 58%,#fff8fb);box-shadow:0 10px 28px rgba(36,75,125,.05)}
.shelf-mission-copy>span{font-size:8px;letter-spacing:.12em;font-weight:950;color:#8b4de8}.shelf-mission h1{margin:4px 0 4px;font-size:22px;letter-spacing:-.45px}.shelf-mission p{margin:0;max-width:650px;color:#7a8da7;font-size:10px;line-height:1.55}
.shelf-mission-cute{display:flex;flex-direction:column;align-items:center;gap:5px;min-width:100px}.shelf-chibi{position:relative;width:68px;height:68px;border-radius:24px 24px 28px 28px;background:linear-gradient(145deg,#fff,#edf4ff);border:1px solid #d7e4f6;display:grid;place-items:center;box-shadow:0 8px 20px rgba(48,82,128,.10)}.shelf-chibi:before{content:"";position:absolute;left:9px;right:9px;top:7px;height:21px;border-radius:17px 17px 9px 9px;background:linear-gradient(180deg,#314760,#22354f)}.shelf-chibi i{position:relative;margin-top:10px;font-style:normal;font-size:14px;font-weight:900;color:#3d526e;letter-spacing:1px}.shelf-chibi b{position:absolute;right:-6px;top:-6px;width:23px;height:23px;border-radius:50%;display:grid;place-items:center;background:#12a86b;color:#fff;border:2px solid #fff;font-size:10px}.shelf-mission-cute small{font-size:8px;color:#8293aa;font-weight:800}
.shelf-status-tabs{padding:5px;margin-top:12px;border:1px solid #e0e8f4;border-radius:14px;background:#fff;box-shadow:0 6px 18px rgba(36,75,125,.035)}
.shelf-status-tabs button{border:0!important;background:transparent!important;border-radius:10px!important;padding:8px 11px!important}.shelf-status-tabs button.active{background:linear-gradient(145deg,#1769ff,#5c7cff)!important;color:#fff!important;box-shadow:0 5px 12px rgba(23,105,255,.18)}
.shelf-card-top span{font-size:9px!important;font-weight:900!important;padding:5px 7px;border-radius:999px;background:#f2f5f9;color:#6f819a}.shelf-card.issue .shelf-card-top span{background:#fff0f3;color:#c74361}.shelf-card.done .shelf-card-top span{background:#eafaf2;color:#168b5f}.shelf-card.remove .shelf-card-top span{background:#fff0ec;color:#c84b3e}
.shelf-card-count{margin-top:7px!important;color:#70839d!important}.shelf-card-count b{font-size:14px;color:#253b58}
.shelf-card{min-height:126px!important;padding:14px!important}.shelf-card-warn{margin-top:8px;display:inline-flex;padding:4px 6px;border-radius:999px;background:#fff0f3;color:#c74361;font-size:8px;font-weight:900}
.shelf-check-main{max-width:760px!important}.shelf-check-head{margin-top:8px}.shelf-product-card h2{font-size:22px!important;letter-spacing:-.35px}.shelf-current-state{margin-top:10px;padding:9px 11px;border-radius:10px;background:#f7faff;color:#60758f;font-size:9px;font-weight:800;text-align:center}
@media(max-width:700px){.shelf-mission{grid-template-columns:1fr;padding:14px}.shelf-mission-cute{display:none}.shelf-mission h1{font-size:18px}.shelf-status-tabs{overflow-x:auto;display:flex;gap:4px;scrollbar-width:none}.shelf-status-tabs::-webkit-scrollbar{display:none}.shelf-status-tabs button{flex:0 0 auto}.shelf-grid{grid-template-columns:1fr!important}.shelf-card{min-height:116px!important}.shelf-product-card h2{font-size:19px!important}}

.shelf-shell{background:linear-gradient(180deg,#f8fbff 0%,#f4f8ff 58%,#fff9fc 100%)!important}
.shelf-sticky{background:rgba(255,255,255,.96)!important;backdrop-filter:blur(14px);box-shadow:0 6px 20px rgba(36,75,125,.06)}
.shelf-topline{max-width:1080px!important}.shelf-progress-wrap{max-width:1080px!important}.shelf-main{max-width:1080px!important}
.shelf-summary-row div{border-color:#e2eaf5!important;border-radius:15px!important;box-shadow:0 7px 20px rgba(36,75,125,.04)}.shelf-summary-row div:nth-child(2){background:#f1fff8}.shelf-summary-row div:nth-child(3){background:#f0f6ff}.shelf-summary-row div:nth-child(4){background:#fff6fa}.shelf-summary-row div:nth-child(5){background:#fffaf0}
.shelf-search-box{border-color:#d9e6f7!important;border-radius:15px!important;box-shadow:0 6px 18px rgba(36,75,125,.04)}.shelf-search-box.focused{border-color:#8bb7ff!important;box-shadow:0 0 0 3px rgba(23,105,255,.10)!important}
.shelf-filter-row button{border-color:#dde7f3!important}.shelf-filter-row button.active{background:#1769ff!important;border-color:#1769ff!important}
.shelf-grid{gap:11px!important}.shelf-card{border-color:#dfe8f4!important;border-radius:17px!important;box-shadow:0 8px 22px rgba(36,75,125,.045);transition:transform .14s ease,box-shadow .14s ease}.shelf-card:hover{transform:translateY(-1px);box-shadow:0 12px 28px rgba(36,75,125,.08)}.shelf-card.done{background:linear-gradient(145deg,#f1fff8,#fff)!important}.shelf-card.issue{background:linear-gradient(145deg,#fff4f7,#fff)!important}.shelf-card.remove{background:linear-gradient(145deg,#fff5f2,#fff)!important}
.shelf-mini-track{background:#edf2f8!important;height:8px!important}.shelf-mini-track i{background:linear-gradient(90deg,#31c981,#12a86b)!important}
.shelf-product-card{border-color:#e0e8f3!important;border-radius:20px!important;box-shadow:0 14px 36px rgba(36,75,125,.07)!important}.shelf-location-banner{background:linear-gradient(90deg,#eef5ff,#f7f2ff)!important;border-color:#d4e2ff!important;color:#365a91!important}.shelf-id-row strong{color:#1769ff!important}
.shelf-actions button,.shelf-removal-actions button{min-height:56px;box-shadow:0 6px 16px rgba(36,75,125,.07)}.shelf-pass{background:linear-gradient(145deg,#26c77d,#0fa66a)!important}.shelf-fail{background:linear-gradient(145deg,#ff6f78,#df3e4b)!important}.shelf-review{background:#fff2df!important;color:#b76b11!important}
.shelf-camera-beta{display:block;margin-top:12px;padding:11px 13px;border:1px solid #d9e6f7;border-radius:12px;background:linear-gradient(90deg,#f6f9ff,#fff7fb);color:#5c7191;text-align:center;text-decoration:none;font-size:10px;font-weight:850}.shelf-camera-beta:hover{border-color:#a9c8fb;color:#1769ff}
.shelf-upload-card{border-color:#e0e9f5!important;background:linear-gradient(145deg,#fff,#fbfdff)!important}.shelf-upload-icon{width:64px;height:64px;margin:0 auto;display:grid;place-items:center;border-radius:20px;background:linear-gradient(145deg,#eaf3ff,#f5edff)}
@media(max-width:700px){.shelf-shell{padding-bottom:74px}.shelf-sticky{top:54px}.shelf-main,.shelf-check-main{padding-left:10px!important;padding-right:10px!important}.shelf-summary-row div{padding:9px 6px!important}.shelf-summary-row strong{font-size:17px!important}.shelf-actions button,.shelf-removal-actions button{min-height:54px}}
*{box-sizing:border-box}.shelf-shell{min-height:100vh;background:#f5f7fb;color:#17202a;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}.shelf-loading{padding:80px 20px;text-align:center;font-weight:750}.shelf-head{max-width:760px;margin:auto;padding:40px 18px 12px}.shelf-kicker{font-size:11px;letter-spacing:.12em;color:#1570ef;font-weight:850}.shelf-head h1{margin:5px 0 8px;font-size:32px}.shelf-head p{margin:0;color:#667085;line-height:1.5}.shelf-upload-card{max-width:620px;margin:18px auto;padding:34px 24px;background:#fff;border:1px solid #e4e7ec;border-radius:20px;text-align:center;box-shadow:0 12px 32px #1018280f}.shelf-upload-icon{font-size:42px}.shelf-upload-card h2{margin:8px 0}.shelf-upload-card p{color:#667085;line-height:1.5}.shelf-upload-button,.shelf-change-file{cursor:pointer}.shelf-upload-button{display:inline-block;margin-top:12px;background:#1570ef;color:#fff;padding:13px 22px;border-radius:12px;font-weight:800}.shelf-upload-button input,.shelf-change-file input{display:none}.shelf-subtle-link{display:block;margin-top:22px;color:#475467}.shelf-error{margin-top:12px;color:#b42318;background:#fef3f2;padding:10px;border-radius:10px}.shelf-sticky{position:sticky;top:0;z-index:7;background:#fff;border-bottom:1px solid #eaecf0;padding:10px 14px}.shelf-topline{max-width:900px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:8px}.shelf-topline button,.shelf-check-head button{border:0;background:#f2f4f7;border-radius:9px;padding:8px 10px;font-weight:750;cursor:pointer}.shelf-head-actions{display:flex;gap:6px;align-items:center}.shelf-topline button b{background:#d92d20;color:#fff;border-radius:99px;padding:2px 6px;font-size:10px}.shelf-progress-wrap{max-width:900px;margin:8px auto 0}.shelf-progress-label{display:flex;justify-content:space-between;font-size:11px;color:#667085}.shelf-progress-track,.shelf-mini-track{height:7px;background:#eaecf0;border-radius:99px;overflow:hidden;margin-top:5px}.shelf-progress-fill,.shelf-mini-track i{display:block;height:100%;background:#12b76a}.shelf-progress-menu{position:absolute;right:14px;top:54px;width:min(340px,calc(100vw - 28px));background:#fff;border:1px solid #d0d5dd;border-radius:14px;padding:8px;box-shadow:0 18px 40px #10182826;z-index:10}.shelf-progress-menu button{width:100%;text-align:left;border:0;background:#fff;border-radius:10px;padding:11px;font-weight:800;cursor:pointer}.shelf-progress-menu button:hover{background:#f9fafb}.shelf-progress-menu button small{display:block;color:#667085;font-weight:500;margin-top:2px}.shelf-progress-menu .danger{color:#b42318}.shelf-main{max-width:900px;margin:auto;padding:18px 14px 80px}.shelf-main.narrow{max-width:620px}.shelf-summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.shelf-summary-row.five{grid-template-columns:repeat(5,1fr)}.shelf-summary-row div{background:#fff;border:1px solid #eaecf0;border-radius:12px;padding:11px;text-align:center}.shelf-summary-row div.remove{border-color:#fda29b;background:#fff5f5}.shelf-summary-row span{display:block;font-size:10px;color:#667085}.shelf-summary-row strong{font-size:20px}.shelf-summary-row .remove strong{color:#b42318}.shelf-section-title{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:24px 2px 12px}.shelf-section-title h2{margin:0;font-size:19px}.shelf-section-title p{margin:4px 0 0;color:#667085;font-size:12px}.shelf-change-file{white-space:nowrap;color:#1570ef;font-size:12px;font-weight:800}.shelf-continue{width:100%;border:1px solid #84caff;background:#eff8ff;border-radius:14px;padding:13px 15px;text-align:left;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;color:#175cd3;cursor:pointer}.shelf-continue.remove{border-color:#fda29b;background:#fff5f5;color:#b42318}.shelf-continue span{font-size:11px;font-weight:850}.shelf-continue strong{color:#17202a}.shelf-continue small{color:#475467}.shelf-search-box{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #b2ddff;border-radius:13px;padding:0 11px;margin-top:12px;transition:.15s ease}.shelf-search-box.focused{border-color:#1570ef;box-shadow:0 0 0 3px #1570ef18}.shelf-search-box span{font-size:22px;color:#667085}.shelf-search-box input{flex:1;min-width:0;border:0;outline:0;padding:13px 0;font-size:14px;background:transparent}.shelf-search-box button{border:0;background:#f2f4f7;border-radius:50%;width:28px;height:28px;font-size:18px;color:#667085;cursor:pointer}.shelf-suggest-panel{margin-top:8px;background:#fff;border:1px solid #b2ddff;border-radius:16px;padding:10px;box-shadow:0 12px 30px #10182812}.shelf-suggest-head{display:flex;align-items:center;justify-content:space-between;padding:3px 5px 9px}.shelf-suggest-head div strong,.shelf-suggest-head div span{display:block}.shelf-suggest-head div strong{font-size:14px}.shelf-suggest-head div span{font-size:10px;color:#667085;margin-top:2px}.shelf-suggest-head>b{font-size:11px;background:#eff8ff;color:#175cd3;border-radius:999px;padding:4px 7px}.shelf-suggest-list{display:grid;gap:7px}.shelf-suggest-item{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #eaecf0;background:#fff;border-radius:12px;padding:10px 11px;text-align:left;cursor:pointer}.shelf-suggest-item.remove{border-color:#fda29b;background:#fff5f5}.shelf-suggest-item.resume{border-color:#84caff;background:#f5fbff}.shelf-suggest-item.issue{border-color:#fda29b;background:#fffafa}.shelf-suggest-item.almost{border-color:#fedf89;background:#fffcf5}.shelf-suggest-copy span,.shelf-suggest-copy strong,.shelf-suggest-copy small{display:block}.shelf-suggest-copy span{font-size:10px;font-weight:900;color:#175cd3}.shelf-suggest-item.remove .shelf-suggest-copy span{color:#b42318}.shelf-suggest-copy strong{font-size:13px;margin:2px 0}.shelf-suggest-copy small{font-size:10px;color:#667085}.shelf-suggest-side{text-align:center;min-width:48px}.shelf-suggest-side b,.shelf-suggest-side small{display:block}.shelf-suggest-side b{font-size:18px}.shelf-suggest-side small{font-size:9px;color:#667085}.shelf-suggest-side em{display:block;margin-top:3px;font-style:normal;font-size:9px;color:#b42318}.shelf-suggest-empty{padding:18px;text-align:center;color:#667085}.shelf-filter-row{display:flex;gap:7px;overflow:auto;padding:10px 1px 3px}.shelf-filter-row button{white-space:nowrap;border:1px solid #d0d5dd;background:#fff;border-radius:999px;padding:8px 11px;font-size:11px;font-weight:800;color:#475467;cursor:pointer}.shelf-filter-row button.active{background:#175cd3;color:#fff;border-color:#175cd3}.shelf-list-caption{font-size:10px;color:#667085;margin:7px 2px}.shelf-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.shelf-card{width:100%;text-align:left;background:#fff;border:1px solid #d0d5dd;border-radius:14px;padding:13px;cursor:pointer;min-height:112px}.shelf-card.done{border-color:#abefc6;background:#f6fef9}.shelf-card.issue{border-color:#fda29b;background:#fffafa}.shelf-card.remove{border-color:#fda29b;background:#fff5f5}.shelf-card-top{display:flex;justify-content:space-between;gap:10px}.shelf-card-top strong{font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shelf-card-top span{font-size:10px;color:#667085;font-weight:800;white-space:nowrap}.shelf-card.remove .shelf-card-top span,.shelf-card.issue .shelf-card-top span{color:#b42318}.shelf-card-count,.shelf-locations{margin-top:6px;color:#475467;font-size:11px}.shelf-locations{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#667085}.shelf-match-hint{margin-top:7px;background:#eff8ff;color:#175cd3;border-radius:8px;padding:6px 8px;font-size:10px;font-weight:800}.shelf-card-warn{margin-top:7px;color:#b42318;font-size:11px;font-weight:800}.shelf-more{display:block;width:100%;border:1px solid #d0d5dd;background:#fff;border-radius:12px;padding:11px;margin-top:10px;font-weight:800;color:#344054}.shelf-check-main{max-width:620px;margin:auto;padding:18px 14px 70px}.shelf-check-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.shelf-check-head div{text-align:right}.shelf-check-head div strong,.shelf-check-head div span{display:block}.shelf-check-head div span{font-size:11px;color:#667085}.shelf-location-banner{background:#eef4ff;border:1px solid #c7d7fe;color:#3538cd;border-radius:10px;padding:9px 11px;margin-bottom:9px;font-weight:800;font-size:12px}.shelf-product-card{background:#fff;border:1px solid #e4e7ec;border-radius:18px;padding:20px;box-shadow:0 10px 28px #1018280c}.shelf-product-card.remove{border-color:#fda29b}.shelf-id-row{display:flex;justify-content:space-between;align-items:center}.shelf-id-row strong{font-size:25px;color:#175cd3}.shelf-id-row span{font-size:11px;color:#667085}.shelf-product-card h2{font-size:18px;line-height:1.35;margin:8px 0}.shelf-promo-name{font-size:14px;font-weight:850;color:#b54708}.shelf-detail{font-size:12px;color:#667085;margin-top:4px}.shelf-expected,.shelf-remove-box{margin-top:18px;padding:17px;border-radius:14px;text-align:center}.shelf-expected{background:#eff8ff}.shelf-remove-box{background:#fff1f3;border:1px solid #fda29b}.shelf-expected span,.shelf-remove-box span{display:block;font-size:11px;color:#475467;font-weight:800}.shelf-remove-box span{color:#b42318}.shelf-expected strong{display:block;font-size:34px;color:#175cd3;margin:2px 0}.shelf-remove-box strong{display:block;font-size:22px;color:#b42318;margin:5px 0}.shelf-remove-box small{color:#667085}.shelf-expected b{font-size:16px}.shelf-meta{text-align:center;color:#667085;font-size:11px;margin-top:10px}.shelf-actions,.shelf-removal-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.shelf-actions button,.shelf-removal-actions button{border:0;border-radius:14px;padding:18px 10px;font-weight:900;font-size:17px}.shelf-removal-actions textarea{grid-column:1/-1;width:100%;padding:10px;border:1px solid #d0d5dd;border-radius:9px;resize:vertical}.shelf-pass{background:#12b76a;color:#fff}.shelf-fail{background:#d92d20;color:#fff}.shelf-review{grid-column:1/-1;background:#fff3e0;color:#b54708!important;font-size:13px!important;padding:12px!important}.shelf-reasons{margin-top:14px;background:#fff;border:1px solid #fecdca;border-radius:16px;padding:14px}.shelf-reason-head{display:flex;justify-content:space-between}.shelf-reason-head button{border:0;background:none;color:#667085}.shelf-reasons textarea{width:100%;margin:10px 0;padding:10px;border:1px solid #d0d5dd;border-radius:9px;resize:vertical}.shelf-reason-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.shelf-reason-grid button{border:1px solid #fecdca;background:#fef3f2;color:#b42318;border-radius:10px;padding:12px 8px;font-weight:800}.shelf-current-state{text-align:center;margin-top:10px;color:#667085;font-size:11px}.shelf-done{max-width:560px;margin:60px auto;text-align:center;padding:24px}.shelf-done-icon{margin:auto;width:70px;height:70px;border-radius:50%;background:#dcfae6;color:#067647;display:grid;place-items:center;font-size:34px;font-weight:900}.shelf-done-icon.warn{background:#fff1f3;color:#b42318}.shelf-done h2{margin-bottom:2px}.shelf-done h3{margin:0;color:#475467}.shelf-done p{color:#667085}.shelf-primary,.shelf-secondary{display:block;width:100%;border:0;border-radius:12px;padding:13px;margin-top:9px;font-weight:850;cursor:pointer}.shelf-primary{background:#1570ef;color:#fff}.shelf-secondary{background:#fff;border:1px solid #d0d5dd}.shelf-empty{text-align:center;background:#fff;border:1px dashed #d0d5dd;padding:35px;border-radius:14px;color:#667085}.shelf-inline-add{border:0;background:#1570ef;color:#fff;border-radius:10px;padding:9px 12px;font-weight:800}.shelf-error-list{display:grid;gap:10px}.shelf-error-item{background:#fff;border:1px solid #fecdca;border-radius:14px;padding:14px}.shelf-error-item.extra{border-color:#fedf89}.shelf-error-item.resolved{opacity:.58;border-color:#abefc6}.shelf-error-item-top{display:flex;justify-content:space-between;gap:10px}.shelf-error-item-top span,.shelf-error-item-top strong{display:block}.shelf-error-item-top span{font-size:10px;color:#667085}.shelf-error-item-top b{color:#b42318;font-size:12px}.shelf-error-expected{font-size:12px;color:#475467;margin-top:7px}.shelf-error-note{font-size:12px;background:#f9fafb;padding:7px;margin-top:7px;border-radius:7px}.shelf-error-buttons{display:flex;gap:8px;margin-top:10px}.shelf-error-buttons button{flex:1;border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:9px;font-weight:750}.shelf-extra-form{background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:16px}.shelf-extra-form label{display:block;font-size:11px;font-weight:800;color:#475467;margin-bottom:12px}.shelf-extra-form input,.shelf-extra-form select,.shelf-extra-form textarea{display:block;width:100%;margin-top:5px;border:1px solid #d0d5dd;border-radius:10px;padding:11px;font:inherit;background:#fff}.shelf-extra-form textarea{resize:vertical}@media(max-width:700px){.shelf-summary-row.five{grid-template-columns:repeat(2,1fr)}.shelf-summary-row.five div:last-child{grid-column:1/-1}.shelf-grid{grid-template-columns:1fr}.shelf-topline>strong{display:none}.shelf-head-actions{gap:3px}.shelf-head-actions button{font-size:10px;padding:7px}.shelf-topline>button{font-size:10px}.shelf-continue{grid-template-columns:1fr}.shelf-progress-label{font-size:9px;gap:10px}.shelf-section-title{align-items:start}.shelf-section-title p{max-width:260px}.shelf-card{min-height:0}.shelf-expected strong{font-size:31px}}`
