import React, { useEffect, useMemo, useState } from "react"
import { cacheUploadedWorkbook, readCachedWorkbook } from "./tag-audit-context-cache.js"
import {
  SHELF_FAIL_REASONS,
  firstUncheckedIndex,
  markResolved,
  normalizeProgress,
  progressStats,
  progressStorageKey,
  recordDecision,
  shelfStats,
} from "./tag-audit-shelf-progress.js"
import { SHELF_FILTERS, nextShelfKey, smartShelfList } from "./tag-audit-shelf-list.js"

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

function readProgress(contextId) {
  if (!contextId) return {}
  try {
    return normalizeProgress(JSON.parse(localStorage.getItem(progressStorageKey(contextId)) || "{}"))
  } catch {
    return {}
  }
}

function writeProgress(contextId, value) {
  if (!contextId) return
  try { localStorage.setItem(progressStorageKey(contextId), JSON.stringify(value)) } catch {}
}

function ProgressBar({ stats }) {
  const percent = stats.total ? Math.round(stats.checked * 100 / stats.total) : 0
  return <div className="shelf-progress-wrap">
    <div className="shelf-progress-label"><strong>{stats.checked} / {stats.total} action</strong><span>Còn {stats.remaining} · {percent}%</span></div>
    <div className="shelf-progress-track"><div className="shelf-progress-fill" style={{width:`${percent}%`}} /></div>
  </div>
}

export default function TagAuditShelfCheck() {
  const [session, setSession] = useState(null)
  const [progress, setProgress] = useState({})
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

  const items = Array.isArray(session?.items) ? session.items : []
  const shelves = Array.isArray(session?.shelves) ? session.shelves : []
  const overall = useMemo(() => progressStats(items, progress), [items, progress])
  const shelfItems = useMemo(
    () => items.filter(item => item.shelf_key === shelfKey),
    [items, shelfKey],
  )
  const current = shelfItems[index] || null
  const failures = useMemo(
    () => items.filter(item => ["fail", "review"].includes(progress[item.check_key]?.state)),
    [items, progress],
  )
  const shelfStatsByKey = useMemo(() => {
    const result = new Map()
    for (const shelf of shelves) result.set(shelf.shelf_key, shelfStats(items, progress, shelf.shelf_key))
    return result
  }, [shelves, items, progress])
  const getShelfStats = key => shelfStatsByKey.get(key) || {total:0,checked:0,remaining:0,pass:0,fail:0,review:0}
  const nextKey = useMemo(() => nextShelfKey(shelves, getShelfStats), [shelves, shelfStatsByKey])
  const nextShelf = shelves.find(shelf => shelf.shelf_key === nextKey) || null
  const smartList = useMemo(
    () => smartShelfList(shelves, items, getShelfStats, {query:shelfQuery, filter:shelfFilter, limit:shelfLimit}),
    [shelves, items, shelfStatsByKey, shelfQuery, shelfFilter, shelfLimit],
  )

  const acceptSession = data => {
    setSession(data)
    setProgress(readProgress(data?.context_id))
    if (data?.session_id) localStorage.setItem(SESSION_KEY, data.session_id)
    setShelfQuery(""); setShelfFilter("todo"); setShelfLimit(INITIAL_SHELF_LIMIT)
    setError("")
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

  const persist = next => {
    setProgress(next)
    writeProgress(session?.context_id, next)
  }

  const openShelf = key => {
    const target = items.filter(item => item.shelf_key === key)
    const resume = firstUncheckedIndex(target, progress)
    setShelfKey(key)
    setIndex(resume >= 0 ? resume : 0)
    setShowReasons(false); setNote("")
    setView("check")
  }

  const advanceAfter = nextProgress => {
    const next = firstUncheckedIndex(shelfItems, nextProgress, index + 1)
    setShowReasons(false); setNote("")
    if (next >= 0) setIndex(next)
    else setView("shelfDone")
  }

  const decide = (state, reason = "") => {
    if (!current) return
    const next = recordDecision(progress, current.check_key, state, reason, note)
    persist(next)
    advanceAfter(next)
  }

  const reopenFailure = item => {
    const target = items.filter(row => row.shelf_key === item.shelf_key)
    const targetIndex = Math.max(0, target.findIndex(row => row.check_key === item.check_key))
    setShelfKey(item.shelf_key); setIndex(targetIndex); setShowReasons(false); setNote("")
    setView("check")
  }

  if (loading) return <><style>{styles}</style><div className="shelf-shell"><div className="shelf-loading">Đang mở Kiểm toàn kệ…</div></div></>

  if (!session) return <><style>{styles}</style><div className="shelf-shell">
    <header className="shelf-head"><div><span className="shelf-kicker">CTKM · VẬN HÀNH CỬA HÀNG</span><h1>Kiểm toàn kệ</h1><p>Không cần tài khoản Admin. Tải workbook action rồi kiểm Đúng/Sai từng sản phẩm theo vị trí kệ.</p></div></header>
    <main className="shelf-upload-card">
      <div className="shelf-upload-icon">▤</div><h2>Tải workbook CTKM</h2>
      <p>Hệ thống chỉ tạo một phiên kiểm kệ tạm thời trên thiết bị này; không thay đổi context Admin.</p>
      <label className="shelf-upload-button">Chọn file .xlsx<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event=>uploadWorkbook(event.target.files?.[0])} /></label>
      {error && <div className="shelf-error">{error}</div>}
      <a className="shelf-subtle-link" href="/scan-tem">← Về Kiểm tem camera</a>
    </main>
  </div></>

  return <><style>{styles}</style><div className="shelf-shell">
    <header className="shelf-sticky">
      <div className="shelf-topline"><button onClick={()=>setView("shelves")}>☰ Kệ</button><strong>Kiểm toàn kệ</strong><button onClick={()=>setView("errors")}>Sai & Review <b>{failures.length}</b></button></div>
      <ProgressBar stats={overall} />
    </header>

    {view === "shelves" && <main className="shelf-main">
      <div className="shelf-summary-row"><div><span>Đúng</span><strong>{overall.pass}</strong></div><div><span>Sai</span><strong>{overall.fail}</strong></div><div><span>Review</span><strong>{overall.review}</strong></div><div><span>Kệ</span><strong>{shelves.length}</strong></div></div>
      <div className="shelf-section-title"><div><h2>Chọn kệ để kiểm</h2><p>Tìm theo POG, vị trí, ITEMID hoặc tên sản phẩm. Mặc định chỉ ưu tiên kệ còn việc.</p></div><label className="shelf-change-file">Đổi file<input type="file" accept=".xlsx" onChange={event=>uploadWorkbook(event.target.files?.[0])} /></label></div>

      {nextShelf && <button className="shelf-continue" onClick={()=>openShelf(nextShelf.shelf_key)}>
        <span>▶ Tiếp tục nhanh</span><strong>{nextShelf.shelf_label}</strong><small>{getShelfStats(nextShelf.shelf_key).checked}/{getShelfStats(nextShelf.shelf_key).total} action · còn {getShelfStats(nextShelf.shelf_key).remaining}</small>
      </button>}

      <div className="shelf-search-box">
        <span>⌕</span><input value={shelfQuery} onChange={event=>{setShelfQuery(event.target.value);setShelfLimit(INITIAL_SHELF_LIMIT)}} placeholder="Tìm kệ, POG, vị trí, P25860, tên sản phẩm…" />
        {shelfQuery && <button onClick={()=>setShelfQuery("")} aria-label="Xóa tìm kiếm">×</button>}
      </div>
      <div className="shelf-filter-row">{SHELF_FILTERS.map(option => <button key={option.key} className={shelfFilter===option.key?"active":""} onClick={()=>{setShelfFilter(option.key);setShelfLimit(INITIAL_SHELF_LIMIT)}}>{option.label}</button>)}</div>
      <div className="shelf-list-caption">{smartList.totalMatches} kệ phù hợp{!shelfQuery && smartList.totalMatches > smartList.rows.length ? ` · đang hiện ${smartList.rows.length}` : ""}</div>

      {!smartList.rows.length ? <div className="shelf-empty">Không tìm thấy kệ phù hợp. Thử đổi từ khóa hoặc chọn “Tất cả”.</div> : <div className="shelf-grid">{smartList.rows.map(({shelf,stats,status}) => {
        const done = status === "done"
        return <button key={shelf.shelf_key} className={`shelf-card ${done ? "done" : ""} ${status === "issues" ? "issue" : ""}`} onClick={()=>openShelf(shelf.shelf_key)}>
          <div className="shelf-card-top"><strong>{shelf.shelf_label}</strong><span>{done ? "✓ Xong" : status === "issues" ? "Có lỗi" : stats.checked ? "▶ Đang kiểm" : "Chưa kiểm"}</span></div>
          <div className="shelf-card-count"><b>{stats.checked}/{stats.total}</b> action · {shelf.sku_count} SKU · còn {stats.remaining}</div>
          <div className="shelf-mini-track"><i style={{width:`${stats.total ? Math.round(stats.checked*100/stats.total) : 0}%`}} /></div>
          {(stats.fail || stats.review) ? <div className="shelf-card-warn">Sai {stats.fail} · Review {stats.review}</div> : null}
        </button>
      })}</div>}
      {!shelfQuery && smartList.totalMatches > smartList.rows.length && <button className="shelf-more" onClick={()=>setShelfLimit(value=>value+12)}>Xem thêm {Math.min(12,smartList.totalMatches-smartList.rows.length)} kệ</button>}
    </main>}

    {view === "check" && current && <main className="shelf-check-main">
      <div className="shelf-check-head"><button onClick={()=>setView("shelves")}>← Danh sách kệ</button><div><strong>{current.shelf_label}</strong><span>{index+1} / {shelfItems.length}</span></div></div>
      <article className="shelf-product-card">
        <div className="shelf-id-row"><strong>{current.item_id || "—"}</strong><span>{current.facing ? `Facing ${current.facing}` : ""}</span></div>
        <h2>{current.item_name || "Tên sản phẩm chưa có"}</h2>
        <div className="shelf-promo-name">{current.campaign_name || current.campaign_detail || "CTKM"}</div>
        {current.campaign_detail && current.campaign_name && <div className="shelf-detail">{current.campaign_detail}</div>}
        <div className="shelf-expected"><span>Tem cần thấy</span><strong>{formatMoney(current.promo_price)}</strong><b>{formatDate(current.promo_from)} → {formatDate(current.promo_to)}</b></div>
        <div className="shelf-meta">{[current.key_channel,current.channel].filter(Boolean).join(" · ") || ""}</div>
      </article>

      {!showReasons ? <div className="shelf-actions">
        <button className="shelf-pass" onClick={()=>decide("pass")}>✓ ĐÚNG</button>
        <button className="shelf-fail" onClick={()=>setShowReasons(true)}>✕ SAI</button>
        <button className="shelf-review" onClick={()=>decide("review","Không chắc")}>? Không chắc / Review</button>
      </div> : <div className="shelf-reasons">
        <div className="shelf-reason-head"><strong>Sai vì lý do gì?</strong><button onClick={()=>{setShowReasons(false);setNote("")}}>Đóng</button></div>
        <textarea value={note} onChange={event=>setNote(event.target.value)} placeholder="Ghi chú nếu cần…" rows="2" />
        <div className="shelf-reason-grid">{SHELF_FAIL_REASONS.map(reason=><button key={reason} onClick={()=>decide("fail",reason)}>{reason}</button>)}</div>
      </div>}
      <div className="shelf-current-state">{progress[current.check_key] ? `Đã lưu: ${progress[current.check_key].state === "pass" ? "Đúng" : progress[current.check_key].reason || "Review"}` : "Chưa kiểm"}</div>
    </main>}

    {view === "shelfDone" && <main className="shelf-done">
      <div className="shelf-done-icon">✓</div><h2>Đã kiểm xong kệ</h2><h3>{shelfItems[0]?.shelf_label || ""}</h3>
      {(() => { const stats=shelfStats(items,progress,shelfKey); return <p>{stats.total} action · Đúng {stats.pass} · Sai {stats.fail} · Review {stats.review}</p> })()}
      {nextKey ? <button className="shelf-primary" onClick={()=>openShelf(nextKey)}>Qua kệ tiếp theo →</button> : <button className="shelf-primary" onClick={()=>setView("shelves")}>Về danh sách kệ</button>}
      <button className="shelf-secondary" onClick={()=>setView("errors")}>Xem Sai & Review</button>
    </main>}

    {view === "errors" && <main className="shelf-main">
      <div className="shelf-section-title"><div><h2>Sai & Review</h2><p>{failures.length} action cần xem lại hoặc xử lý.</p></div></div>
      {!failures.length ? <div className="shelf-empty">Chưa có action Sai/Review.</div> : <div className="shelf-error-list">{failures.map(item => {
        const state = progress[item.check_key] || {}
        return <article key={item.check_key} className={`shelf-error-item ${state.resolved ? "resolved" : ""}`}>
          <div className="shelf-error-item-top"><div><span>{item.shelf_label}</span><strong>{item.item_id} · {item.item_name || ""}</strong></div><b>{state.state === "review" ? "Review" : state.reason || "Sai"}</b></div>
          <div className="shelf-error-expected">Chuẩn: {formatMoney(item.promo_price)} · {formatDate(item.promo_from)}–{formatDate(item.promo_to)}</div>
          {state.note && <div className="shelf-error-note">{state.note}</div>}
          <div className="shelf-error-buttons"><button onClick={()=>reopenFailure(item)}>Kiểm lại</button><button onClick={()=>persist(markResolved(progress,item.check_key,!state.resolved))}>{state.resolved ? "Đánh dấu chưa sửa" : "✓ Đã sửa"}</button></div>
        </article>
      })}</div>}
    </main>}
  </div></>
}

const styles = `
*{box-sizing:border-box}.shelf-shell{min-height:100vh;background:#f5f7fb;color:#17202a;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}.shelf-loading{padding:80px 20px;text-align:center;font-weight:750}.shelf-head{max-width:760px;margin:auto;padding:40px 18px 12px}.shelf-kicker{font-size:11px;letter-spacing:.12em;color:#1570ef;font-weight:850}.shelf-head h1{margin:5px 0 8px;font-size:32px}.shelf-head p{margin:0;color:#667085;line-height:1.5}.shelf-upload-card{max-width:620px;margin:18px auto;padding:34px 24px;background:#fff;border:1px solid #e4e7ec;border-radius:20px;text-align:center;box-shadow:0 12px 32px #1018280f}.shelf-upload-icon{font-size:42px}.shelf-upload-card h2{margin:8px 0}.shelf-upload-card p{color:#667085;line-height:1.5}.shelf-upload-button,.shelf-change-file{cursor:pointer}.shelf-upload-button{display:inline-block;margin-top:12px;background:#1570ef;color:#fff;padding:13px 22px;border-radius:12px;font-weight:800}.shelf-upload-button input,.shelf-change-file input{display:none}.shelf-subtle-link{display:block;margin-top:22px;color:#475467}.shelf-error{margin-top:16px;color:#b42318;background:#fef3f2;padding:10px;border-radius:10px}.shelf-sticky{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #eaecf0;padding:10px 14px}.shelf-topline{max-width:760px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:8px}.shelf-topline button,.shelf-check-head button{border:0;background:#f2f4f7;border-radius:9px;padding:8px 10px;font-weight:750}.shelf-topline button b{background:#d92d20;color:#fff;border-radius:99px;padding:2px 6px;font-size:10px}.shelf-progress-wrap{max-width:760px;margin:8px auto 0}.shelf-progress-label{display:flex;justify-content:space-between;font-size:11px;color:#667085}.shelf-progress-track,.shelf-mini-track{height:7px;background:#eaecf0;border-radius:99px;overflow:hidden;margin-top:5px}.shelf-progress-fill,.shelf-mini-track i{display:block;height:100%;background:#12b76a}.shelf-main{max-width:860px;margin:auto;padding:18px 14px 40px}.shelf-summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.shelf-summary-row div{background:#fff;border:1px solid #eaecf0;border-radius:12px;padding:11px;text-align:center}.shelf-summary-row span{display:block;font-size:10px;color:#667085}.shelf-summary-row strong{font-size:20px}.shelf-section-title{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:24px 2px 12px}.shelf-section-title h2{margin:0;font-size:19px}.shelf-section-title p{margin:4px 0 0;color:#667085;font-size:12px}.shelf-change-file{white-space:nowrap;color:#1570ef;font-size:12px;font-weight:800}.shelf-continue{width:100%;border:1px solid #84caff;background:#eff8ff;border-radius:14px;padding:13px 15px;text-align:left;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;color:#175cd3;cursor:pointer}.shelf-continue span{font-size:11px;font-weight:850}.shelf-continue strong{color:#17202a}.shelf-continue small{color:#475467}.shelf-search-box{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #b2ddff;border-radius:13px;padding:0 11px;margin-top:12px}.shelf-search-box span{font-size:22px;color:#667085}.shelf-search-box input{flex:1;min-width:0;border:0;outline:0;padding:13px 0;font-size:14px;background:transparent}.shelf-search-box button{border:0;background:#f2f4f7;border-radius:50%;width:28px;height:28px;font-size:18px;color:#667085}.shelf-filter-row{display:flex;gap:7px;overflow:auto;padding:10px 1px 3px}.shelf-filter-row button{white-space:nowrap;border:1px solid #d0d5dd;background:#fff;border-radius:999px;padding:8px 11px;font-size:11px;font-weight:800;color:#475467}.shelf-filter-row button.active{background:#175cd3;color:#fff;border-color:#175cd3}.shelf-list-caption{font-size:10px;color:#667085;margin:7px 2px}.shelf-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.shelf-card{width:100%;text-align:left;background:#fff;border:1px solid #d0d5dd;border-radius:14px;padding:13px;cursor:pointer;min-height:104px}.shelf-card.done{border-color:#abefc6;background:#f6fef9}.shelf-card.issue{border-color:#fda29b;background:#fffafa}.shelf-card-top{display:flex;justify-content:space-between;gap:10px}.shelf-card-top strong{font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.shelf-card-top span{font-size:10px;color:#667085;font-weight:800;white-space:nowrap}.shelf-card.issue .shelf-card-top span{color:#b42318}.shelf-card-count{margin-top:6px;color:#475467;font-size:11px}.shelf-card-warn{margin-top:7px;color:#b42318;font-size:11px;font-weight:800}.shelf-more{display:block;width:100%;border:1px solid #d0d5dd;background:#fff;border-radius:12px;padding:11px;margin-top:10px;font-weight:800;color:#344054}.shelf-check-main{max-width:620px;margin:auto;padding:18px 14px 50px}.shelf-check-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.shelf-check-head div{text-align:right}.shelf-check-head div strong,.shelf-check-head div span{display:block}.shelf-check-head div span{font-size:11px;color:#667085}.shelf-product-card{background:#fff;border:1px solid #e4e7ec;border-radius:18px;padding:20px;box-shadow:0 10px 28px #1018280c}.shelf-id-row{display:flex;justify-content:space-between;align-items:center}.shelf-id-row strong{font-size:25px;color:#175cd3}.shelf-id-row span{font-size:11px;color:#667085}.shelf-product-card h2{font-size:18px;line-height:1.35;margin:8px 0}.shelf-promo-name{font-size:14px;font-weight:850;color:#b54708}.shelf-detail{font-size:12px;color:#667085;margin-top:4px}.shelf-expected{margin-top:18px;padding:17px;background:#eff8ff;border-radius:14px;text-align:center}.shelf-expected span{display:block;font-size:11px;color:#475467;font-weight:700}.shelf-expected strong{display:block;font-size:34px;color:#175cd3;margin:2px 0}.shelf-expected b{font-size:16px}.shelf-meta{text-align:center;color:#667085;font-size:11px;margin-top:10px}.shelf-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.shelf-actions button{border:0;border-radius:14px;padding:18px 10px;font-weight:900;font-size:17px}.shelf-pass{background:#12b76a;color:#fff}.shelf-fail{background:#d92d20;color:#fff}.shelf-review{grid-column:1/-1;background:#fff3e0;color:#b54708!important;font-size:13px!important;padding:12px!important}.shelf-reasons{margin-top:14px;background:#fff;border:1px solid #fecdca;border-radius:16px;padding:14px}.shelf-reason-head{display:flex;justify-content:space-between}.shelf-reason-head button{border:0;background:none;color:#667085}.shelf-reasons textarea{width:100%;margin:10px 0;padding:10px;border:1px solid #d0d5dd;border-radius:9px;resize:vertical}.shelf-reason-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.shelf-reason-grid button{border:1px solid #fecdca;background:#fef3f2;color:#b42318;border-radius:10px;padding:12px 8px;font-weight:800}.shelf-current-state{text-align:center;margin-top:10px;color:#667085;font-size:11px}.shelf-done{max-width:560px;margin:60px auto;text-align:center;padding:24px}.shelf-done-icon{margin:auto;width:70px;height:70px;border-radius:50%;background:#dcfae6;color:#067647;display:grid;place-items:center;font-size:34px;font-weight:900}.shelf-done h2{margin-bottom:2px}.shelf-done h3{margin:0;color:#475467}.shelf-done p{color:#667085}.shelf-primary,.shelf-secondary{display:block;width:100%;border:0;border-radius:12px;padding:13px;margin-top:9px;font-weight:850}.shelf-primary{background:#1570ef;color:#fff}.shelf-secondary{background:#fff;border:1px solid #d0d5dd}.shelf-empty{text-align:center;background:#fff;border:1px dashed #d0d5dd;padding:35px;border-radius:14px;color:#667085}.shelf-error-list{display:grid;gap:10px}.shelf-error-item{background:#fff;border:1px solid #fecdca;border-radius:14px;padding:14px}.shelf-error-item.resolved{opacity:.62;border-color:#abefc6}.shelf-error-item-top{display:flex;justify-content:space-between;gap:10px}.shelf-error-item-top span,.shelf-error-item-top strong{display:block}.shelf-error-item-top span{font-size:10px;color:#667085}.shelf-error-item-top b{color:#b42318;font-size:12px}.shelf-error-expected{font-size:12px;color:#475467;margin-top:7px}.shelf-error-note{font-size:12px;background:#f9fafb;padding:7px;margin-top:7px;border-radius:7px}.shelf-error-buttons{display:flex;gap:8px;margin-top:10px}.shelf-error-buttons button{flex:1;border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:9px;font-weight:750}@media(max-width:620px){.shelf-head{padding-top:24px}.shelf-head h1{font-size:28px}.shelf-summary-row{grid-template-columns:repeat(2,1fr)}.shelf-topline>strong{display:none}.shelf-topline button{font-size:11px}.shelf-expected strong{font-size:31px}.shelf-grid{grid-template-columns:1fr}.shelf-continue{grid-template-columns:1fr}.shelf-continue small{margin-top:-5px}.shelf-card{min-height:0}}
`
