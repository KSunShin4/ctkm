import { useState, useCallback, useRef, useEffect } from "react"
import ProductNav from "./ProductNav.jsx"

const API = import.meta.env.VITE_API_BASE_URL || ""  // relative /api by default; override in production if needed

// ─── Design tokens ────────────────────────────────────────────────────────────
// Clean pharmacy/operations UI, optimized for desktop and phone camera use.
const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #fafafa;
    --surface:   #ffffff;
    --surface2:  #f6f6f6;
    --border:    #e8e8e8;
    --border2:   #d4d4d4;
    --text:      #171717;
    --text2:     #525252;
    --text3:     #8a8a8a;
    --accent:    #171717;
    --accent2:   #000000;
    --green:     #087f5b;
    --red:       #d92d20;
    --blue:      #2563eb;
    --font:      Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --mono:      'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    --radius:    8px;
    --radius-lg: 12px;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }

  /* Layout */
  .shell     { display: flex; flex-direction: column; min-height: 100vh; }
  .topbar    { border-bottom: 1px solid var(--border); padding: 0 32px;
               display: flex; align-items: center; gap: 12px; height: 68px;
               background: rgba(255,255,255,.96); z-index: 5; }
  .topbar-logo { font-size: 19px; font-weight: 750; letter-spacing: -0.5px; color: var(--text); }
  .topbar-logo span { color: var(--green); }
  .topbar-sub  { font-size: 12px; color: var(--text3); margin-left: 4px; }
  .module-nav { display: flex; gap: 4px; margin-left: 22px; padding: 3px;
                background: var(--surface2); border-radius: 9px; }
  .module-nav button { border: 0; background: transparent; color: var(--text2); padding: 7px 12px;
                       border-radius: 8px; font-family: var(--font); font-size: 12px;
                       font-weight: 650; cursor: pointer; transition: .15s ease; }
  .module-nav button:hover { color: var(--text); }
  .module-nav button.active { color: var(--text); background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
  .backend-status { margin-left: auto; display: flex; align-items: center; gap: 7px;
                    font-size: 11px; color: var(--text3); font-family: var(--mono); }
  .auth-actions { display:flex; align-items:center; gap:8px; }
  .auth-input { width:118px; border:1px solid var(--border2); border-radius:7px;
                padding:7px 9px; font:12px var(--font); outline:none; }
  .auth-input:focus { border-color:var(--accent); }
  .auth-button { border:1px solid var(--border2); background:#fff; border-radius:7px;
                 padding:7px 10px; font:600 11px var(--font); cursor:pointer; }
  .auth-error { color:var(--red); font-size:11px; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.ok   { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .status-dot.warn { background: var(--accent); }
  .status-dot.err  { background: var(--red); }
  .main      { flex: 1; display: grid; grid-template-columns: 340px minmax(0, 1fr);
               gap: 0; height: calc(100vh - 68px); overflow: hidden; }
  .sidebar   { border-right: 1px solid var(--border); overflow-y: auto;
               padding: 24px 20px; display: flex; flex-direction: column; gap: 16px;
               background: #fff; }
  .content   { overflow-y: auto; padding: 28px 32px 48px; }
  .main.expiration-mode { grid-template-columns: 1fr; }
  .main.expiration-mode .sidebar { display: none; }
  .main.expiration-mode .content { width: 100%; max-width: 1120px; margin: 0 auto; }
  .main.expiration-mode .content > :not(.expiration-card) { display: none; }
  .main.ctkm-mode .expiration-card { display: none; }
  .main.ctkm-mode .tem-r-card { display: none; }
  .main.temr-mode { display: block; height: calc(100vh - 68px); overflow-y: auto; }
  .main.temr-mode .content { display: none; }
  .main.temr-mode .sidebar { width: 100%; max-width: 620px; margin: 0 auto; border: 0;
                            background: transparent; overflow: visible; padding: 32px 20px; }
  .main.temr-mode .sidebar > :not(.tem-r-card) { display: none; }

  /* Cards */
  .card      { background: var(--surface); border: 1px solid var(--border);
               border-radius: var(--radius-lg); padding: 20px; box-shadow: none; }
  .card-title { font-size: 13px; font-weight: 650; letter-spacing: -.01em;
                color: var(--text2); margin-bottom: 16px; }

  /* File drop zone */
  .dropzone  { border: 1px dashed var(--border2); border-radius: var(--radius);
               padding: 20px 16px; text-align: center; cursor: pointer;
               transition: all .15s; background: var(--surface2); }
  .dropzone:hover, .dropzone.over { border-color: var(--text); background: #fafafa; }
  .dropzone.filled { border-style: solid; border-color: var(--green); }
  .dropzone-icon { font-size: 24px; margin-bottom: 6px; }
  .dropzone-label { font-size: 13px; font-weight: 500; color: var(--text); }
  .dropzone-sub   { font-size: 11px; color: var(--text3); margin-top: 3px; }
  .dropzone-file  { font-size: 12px; color: var(--green); font-family: var(--mono);
                    margin-top: 6px; word-break: break-all; }

  /* Month picker */
  .month-input { width: 100%; background: var(--surface2); border: 1px solid var(--border2);
                 border-radius: var(--radius); padding: 9px 12px; color: var(--text);
                 font-family: var(--mono); font-size: 14px; outline: none;
                 transition: border-color .15s; }
  .month-input:focus { border-color: var(--accent); }
  .entry-input { width: 100%; min-height: 132px; resize: vertical; background: var(--surface2);
                 border: 1px solid var(--border2); border-radius: var(--radius); padding: 11px 12px;
                 color: var(--text); font-family: var(--mono); font-size: 13px; outline: none;
                 line-height: 1.65; }
  .entry-input:focus { border-color: var(--accent); }
  .expiration-grid { display: grid; grid-template-columns: minmax(250px, .75fr) minmax(340px, 1.25fr);
                     gap: 16px; align-items: start; }
  .result-status { display: inline-flex; padding: 2px 8px; border-radius: 999px;
                   font-size: 11px; font-weight: 600; white-space: nowrap; }
  .result-status.matched { color: #067647; background: #ecfdf3; }
  .result-status.related { color: #1d4ed8; background: #eff6ff; }
  .result-status.invalid, .result-status.not_found,
  .result-status.batch_mismatch, .result-status.date_mismatch { color: #b42318; background: #fef3f2; }
  .camera-wrap { position: relative; overflow: hidden; border: 1px solid var(--border2);
                 border-radius: var(--radius); background: #050608; margin-top: 10px; }
  .camera-video { display: block; width: 100%; max-height: 320px; object-fit: cover; }
  .camera-guide { position: absolute; inset: 22% 10%; border: 2px solid var(--accent);
                  border-radius: 10px; box-shadow: 0 0 0 999px rgba(0,0,0,.3); pointer-events: none; }
  .camera-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }

  .sheet-select {
    width: 100%; background: var(--surface2); border: 1px solid var(--border2);
    border-radius: var(--radius); padding: 9px 12px; color: var(--text);
    font-family: var(--font); font-size: 13px; outline: none;
    transition: border-color .15s; margin-top: 10px;
  }
  .sheet-select:focus { border-color: var(--accent); }
  .mapping-row { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 10px;
                 align-items: center; margin-bottom: 8px; }
  .mapping-field { color: var(--text2); font-size: 12px; }
  .mapping-row .sheet-select { width: 100%; min-width: 0; }
  .sheet-hint { font-size: 11px; color: var(--text3); margin-top: 6px; }

  /* Button */
  .btn { display: flex; align-items: center; justify-content: center; gap: 8px;
         width: 100%; min-height: 44px; padding: 11px 14px; border-radius: var(--radius); border: none;
         font-family: var(--font); font-size: 14px; font-weight: 600;
         cursor: pointer; transition: all .15s; }
  .btn-primary { background: var(--accent); color: #fff; box-shadow: none; }
  .btn-primary:hover:not(:disabled) { background: var(--accent2); }
  .btn-primary:disabled { opacity: .4; cursor: not-allowed; }
  .btn-ghost { background: var(--surface2); color: var(--text);
               border: 1px solid var(--border2); }
  .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }

  /* Spinner */
  .spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.35);
             border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Status strip */
  .status-strip { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
                  border-radius: var(--radius); font-size: 13px; font-weight: 500; }
  .status-strip.info    { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
  .status-strip.success { background: #ecfdf3; color: #067647; border: 1px solid #abefc6; }
  .status-strip.warn    { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
  .status-strip.error   { background: #fef3f2; color: #b42318; border: 1px solid #fecdca; }
  .expiration-card { padding: 20px 0; border: 0; background: transparent; box-shadow: none; }
  .expiration-header { display: flex; align-items: flex-start; justify-content: space-between;
                       gap: 16px; margin-bottom: 22px; }
  .expiration-kicker { color: var(--green); font-size: 11px; font-weight: 750;
                       letter-spacing: .08em; text-transform: uppercase; margin-bottom: 5px; }
  .expiration-title { font-size: 30px; line-height: 1.15; letter-spacing: -.8px; font-weight: 720; }
  .expiration-subtitle { margin-top: 7px; color: var(--text2); font-size: 13px; }
  .format-pill { padding: 7px 10px; border-radius: 7px; border: 1px solid var(--border);
                 background: #fff; color: var(--text2); font-family: var(--mono); font-size: 11px; white-space: nowrap; }
  .ctkm-mode .sidebar .card { border: 0; border-bottom: 1px solid var(--border);
                              border-radius: 0; padding: 16px 2px 22px; background: transparent; }
  .advanced-card.hidden { display: none !important; }
  .advanced-toggle { background: transparent; border: 0; color: var(--text2); font-family: var(--font);
                     font-size: 12px; font-weight: 650; cursor: pointer; text-align: left;
                     padding: 2px 2px 10px; }
  .advanced-toggle:hover { color: var(--text); }

  /* Summary grid */
  .summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .stat-box { background: var(--surface2); border: 1px solid var(--border);
              border-radius: var(--radius); padding: 14px 16px; }
  .stat-num  { font-size: 26px; font-weight: 600; font-family: var(--mono);
               color: var(--accent); letter-spacing: -1px; line-height: 1; }
  .stat-label { font-size: 11px; color: var(--text2); margin-top: 4px; }
  .stat-sub   { font-size: 10px; color: var(--text3); margin-top: 2px; }

  /* Tab bar */
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border);
          margin-bottom: 20px; overflow-x: auto; }
  .tab  { padding: 9px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
          border-bottom: 2px solid transparent; color: var(--text2); white-space: nowrap;
          background: none; border-top: none; border-left: none; border-right: none;
          font-family: var(--font); transition: all .12s; }
  .tab:hover  { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-badge  { display: inline-flex; align-items: center; justify-content: center;
                background: var(--border2); color: var(--text2); border-radius: 10px;
                font-size: 10px; padding: 1px 6px; margin-left: 6px; font-family: var(--mono); }
  .tab.active .tab-badge { background: var(--accent); color: #0f1117; }

  /* Table */
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }
  table { border-collapse: collapse; width: 100%; min-width: 600px; font-size: 12.5px; }
  thead th { background: var(--surface2); padding: 9px 12px; text-align: left;
             font-size: 11px; font-weight: 600; color: var(--text2); white-space: nowrap;
             border-bottom: 1px solid var(--border2); letter-spacing: .04em; }
  tbody td { padding: 8px 12px; border-bottom: 1px solid var(--border);
             color: var(--text); max-width: 220px; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono);
             font-size: 12px; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: var(--surface2); }

  /* Warnings */
  .warn-list { display: flex; flex-direction: column; gap: 8px; }
  .warn-item { background: var(--surface2); border-left: 3px solid var(--accent);
               border-radius: 0 var(--radius) var(--radius) 0;
               padding: 10px 14px; font-size: 12.5px; color: var(--text2); }

  /* Empty */
  .empty { text-align: center; padding: 60px 20px; color: var(--text3); }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-title { font-size: 15px; font-weight: 500; color: var(--text2); margin-bottom: 6px; }

  /* Download bar */
  .download-bar { display: flex; align-items: center; gap: 12px; padding: 14px 18px;
                  background: var(--surface); border: 1px solid var(--border);
                  border-radius: var(--radius-lg); margin-bottom: 24px; }
  .download-info { flex: 1; }
  .download-name { font-size: 13px; font-weight: 600; color: var(--text); }
  .download-meta { font-size: 11px; color: var(--text3); margin-top: 2px; font-family: var(--mono); }

  /* Progress */
  .progress-wrap { margin: 16px 0; }
  .progress-bar  { height: 3px; background: var(--border); border-radius: 99px; overflow: hidden; }
  .progress-fill { height: 100%; background: var(--accent);
                   animation: progress-pulse 1.5s ease-in-out infinite; }
  @keyframes progress-pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  .progress-label { font-size: 11px; color: var(--text3); margin-top: 6px; font-family: var(--mono); }

  /* Section title */
  .section-title { font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text); }
  .section-title span { color: var(--text3); font-weight: 400; font-size: 13px; margin-left: 8px; }

  /* Row count */
  .row-count { font-size: 11px; color: var(--text3); margin-bottom: 10px; font-family: var(--mono); }

  .output-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }

  /* Responsive */
  @media (max-width: 768px) {
    body { font-size: 13px; }
    .topbar { height: auto; min-height: 56px; padding: 10px 16px; flex-wrap: wrap; }
    .topbar-logo { font-size: 16px; }
    .topbar-sub { display: none; }
    .module-nav { order: 3; width: 100%; margin: 2px 0 0; }
    .module-nav button { flex: 1; min-height: 38px; }
    .backend-status { font-size: 10px; }
    .main { display: flex; flex-direction: column; height: auto; overflow: visible; }
    .sidebar { border-right: none; border-bottom: 1px solid var(--border);
               max-height: none; overflow: visible; padding: 16px 12px; gap: 16px; order: 2; }
    .content { overflow: visible; padding: 16px 12px 28px; order: 1; }
    .card { padding: 16px 12px; border-radius: 10px; }
    .expiration-card { padding: 20px 16px; border-radius: 16px; }
    .expiration-header { display: block; margin-bottom: 18px; }
    .expiration-title { font-size: 21px; }
    .format-pill { display: inline-flex; margin-top: 12px; }
    .summary-grid, .output-field-grid { grid-template-columns: 1fr; }
    .download-bar { align-items: stretch; flex-direction: column; }
    .download-bar .btn { width: 100% !important; }
    .empty { padding: 36px 12px; }

    /* Mapping is a form on mobile, so cards are easier to use than a wide table. */
    .mapping-table { overflow: visible !important; max-height: none !important; border: 0; }
    .mapping-table table,
    .mapping-table tbody,
    .mapping-table tr,
    .mapping-table td { display: block; width: 100%; min-width: 0; }
    .mapping-table thead { display: none; }
    .mapping-table tbody { display: grid; gap: 10px; }
    .mapping-table tr { padding: 12px; background: var(--surface2);
                        border: 1px solid var(--border); border-radius: var(--radius); }
    .mapping-table tbody td { max-width: none; white-space: normal; overflow: visible;
                              border: 0; padding: 3px 0; font-family: var(--font); }
    .mapping-table tbody td:first-child { font-family: var(--mono); font-weight: 600;
                                          overflow-wrap: anywhere; color: var(--text); }
    .mapping-table tbody td:nth-child(2),
    .mapping-table tbody td:nth-child(3) { display: inline; color: var(--text2); font-size: 11px; }
    .mapping-table tbody td:nth-child(2)::before { content: "Gợi ý: "; color: var(--text3); }
    .mapping-table tbody td:nth-child(3)::before { content: " · Tin cậy: "; color: var(--text3); }
    .mapping-table tbody td:last-child { margin-top: 8px; }
    .mapping-table .sheet-select { min-width: 0 !important; width: 100%; min-height: 44px; }
    .mapping-row { grid-template-columns: 1fr; gap: 5px; padding: 8px 0; }
  }

  @media (max-width: 380px) {
    .topbar { align-items: flex-start; }
    .backend-status { width: 100%; margin-left: 0; }
    .stat-num { font-size: 22px; }
  }
  @media (max-width: 900px) { .expiration-grid { grid-template-columns: 1fr; } }
`

// ─── Helpers ──────────────────────────────────────────────────────────────────
function useDropzone(onFile) {
  const [over, setOver] = useState(false)
  const ref = useRef()
  const onDrop = useCallback(e => {
    e.preventDefault(); setOver(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.endsWith(".xlsx")) onFile(f)
  }, [onFile])
  const onDrag = useCallback(e => { e.preventDefault(); setOver(true) }, [])
  const onLeave = useCallback(() => setOver(false), [])
  const onClick = () => ref.current?.click()
  const onChange = e => { const f = e.target.files[0]; if (f) onFile(f) }
  return { ref, over, onDrop, onDrag, onLeave, onClick, onChange }
}

function expirationTime(value) {
  const [day, month, year] = String(value || "").split("/").map(Number)
  return day && month && year ? new Date(year, month - 1, day).getTime() : 0
}

function expirationDisplayRows(result, filter, sort) {
  const rows = (result?.results || []).flatMap(query => {
    if (!query.related_rows?.length) return [{...query, rowKey:`${query.line}-input`, exact:query.status === "matched"}]
    return query.related_rows.map((related, index) => ({
      ...query, ...related,
      rowKey: `${query.line}-${related.batch_number}-${related.exp_date}-${index}`,
      exact: query.status === "matched" && related.batch_number === query.batch_number && related.exp_date === query.exp_date,
      status: query.status === "matched" && related.batch_number === query.batch_number && related.exp_date === query.exp_date ? "matched" : "related",
      message: related.batch_number === query.batch_number && related.exp_date === query.exp_date ? query.message : "Cùng mã P · lô/hạn dùng khác",
    }))
  }).filter(row => filter === "all" || (filter === "matched" ? row.exact : !row.exact))
  return rows.sort((a, b) => {
    if (sort === "expiry_asc") return expirationTime(a.exp_date) - expirationTime(b.exp_date)
    if (sort === "item") return String(a.item_id || "").localeCompare(String(b.item_id || "")) || expirationTime(b.exp_date) - expirationTime(a.exp_date)
    if (sort === "input") return a.line - b.line
    return expirationTime(b.exp_date) - expirationTime(a.exp_date)
  })
}

function fmt(n) { return typeof n === "number" ? n.toLocaleString("vi-VN") : n ?? "—" }

function normalizeColumn(text) {
  return String(text ?? "").trim().toLowerCase().replace(/\s+/g, " ")
}

function buildColumnSignature(columns) {
  return (columns || []).map(normalizeColumn).sort().join("|")
}

function readJsonStorage(key, fallback) {
  try {
    if (typeof window === "undefined") return fallback
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

function writeJsonStorage(key, value) {
  try {
    if (typeof window === "undefined") return
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore storage failures
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function Dropzone({ label, sub, file, onFile }) {
  const dz = useDropzone(onFile)
  return (
    <div
      className={`dropzone${file ? " filled" : ""}${dz.over ? " over" : ""}`}
      onDrop={dz.onDrop}
      onDragOver={dz.onDrag}
      onDragLeave={dz.onLeave}
      onClick={dz.onClick}
    >
      <input ref={dz.ref} type="file" accept=".xlsx" style={{display:"none"}} onChange={dz.onChange} />
      <div className="dropzone-icon">{file ? "✓" : "↑"}</div>
      <div className="dropzone-label">{label}</div>
      <div className="dropzone-sub">{sub}</div>
      {file && <div className="dropzone-file">{file.name}</div>}
    </div>
  )
}

function StatBox({ num, label, sub, accent }) {
  return (
    <div className="stat-box">
      <div className="stat-num" style={accent ? {color: accent} : {}}>{fmt(num)}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function DataTable({ headers, rows, totalRows }) {
  if (!headers?.length) return <p style={{color:"var(--text3)",fontSize:13}}>Không có dữ liệu.</p>
  return (
    <>
      <div className="row-count">
        Hiển thị {rows.length} / {totalRows} dòng
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{headers.map((h,i) => <th key={i} title={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row,ri) => (
              <tr key={ri}>
                {row.map((cell,ci) => <td key={ci} title={cell}>{cell || "—"}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────
const STEPS = { idle: "idle", running: "running", done: "done", error: "error" }
const STEP_LABELS = [
  "Đọc và chuẩn hoá file…",
  "Phân loại sheet CTKM…",
  "Gemini nhận diện cột…",
  "Lọc theo tháng…",
  "Ghép CTKM ↔ POG…",
  "Soát lệch & xuất file…",
]
const FACT_FIELDS = [
  "item_id",
  "item_name",
  "campaign_name",
  "campaign_detail",
  "promo_from",
  "promo_to",
  "channel",
  "normal_price",
  "promo_price",
  "product_type",
]
const POG_FIELDS = [
  "item_id",
  "item_name",
  "store_id",
  "pog_code",
  "location_id",
  "facing",
]
const OUTPUT_FIELDS = [
  "item_id",
  "item_name",
  "campaign_name",
  "campaign_detail",
  "promo_from",
  "promo_to",
  "channel",
  "normal_price",
  "promo_price",
  "product_type",
  "store_id",
  "pog_code",
  "location_id",
  "facing",
]
const OUTPUT_PRESET_KEY = "ctkm.output.columns.v1"
const MAPPING_PRESET_PREFIX = "ctkm.mapping.preset.v1"
const TEM_R_RESULT_KEY = "ctkm.temr.last-result.v1"
const TEM_R_REQUIRED_COLUMNS = ["STOREID", "POGCODE", "FIXELID", "LOCATIONID", "ITEMID", "ITEMNAME"]
const TEM_R_FIELD_LABELS = {
  STOREID:"Mã cửa hàng", POGCODE:"Mã POG", FIXELID:"Mã kệ",
  LOCATIONID:"Vị trí trên kệ", ITEMID:"Mã sản phẩm", ITEMNAME:"Tên sản phẩm",
}

export default function App() {
  const [activeModule, setActiveModule] = useState("expiration")
  const [adminToken, setAdminToken] = useState(() => sessionStorage.getItem("ctkm.admin.token") || "")
  const [adminUsername, setAdminUsername] = useState("admin")
  const [adminPassword, setAdminPassword] = useState("")
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState("")
  const [ctkmAdvanced, setCtkmAdvanced] = useState(false)
  const [ctkmFile, setCtkmFile]   = useState(null)
  const [clearanceFile, setClearanceFile] = useState(null)
  const [pogFile, setPogFile]     = useState(null)
  const [month, setMonth]         = useState(() => {
    const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`
  })
  const [strict, setStrict]       = useState(false)
  const [ctkmSheetOptions, setCtkmSheetOptions] = useState([])
  const [ctkmSheetName, setCtkmSheetName] = useState("")
  const [ctkmSheetLoading, setCtkmSheetLoading] = useState(false)
  const [ctkmSheetError, setCtkmSheetError] = useState("")
  const [pogSnapshotMonth, setPogSnapshotMonth] = useState("")
  const [pogSheetOptions, setPogSheetOptions] = useState([])
  const [pogSheetName, setPogSheetName] = useState("")
  const [pogSheetLoading, setPogSheetLoading] = useState(false)
  const [pogInspectError, setPogInspectError] = useState("")
  const [mappingPreview, setMappingPreview] = useState(null)
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingError, setMappingError] = useState("")
  const [mappingSaving, setMappingSaving] = useState(false)
  const [mappingSaved, setMappingSaved] = useState("")
  const [savedOnly, setSavedOnly] = useState(false)
  const [ctkmMappingOverride, setCtkmMappingOverride] = useState({})
  const [pogMappingOverride, setPogMappingOverride] = useState({})
  const [selectedOutputColumns, setSelectedOutputColumns] = useState([])
  const [savedPresets, setSavedPresets] = useState([])
  const [presetLoading, setPresetLoading] = useState(false)
  const [presetError, setPresetError] = useState("")
  const [temRFile, setTemRFile] = useState(null)
  const [temRLoading, setTemRLoading] = useState(false)
  const [temRResult, setTemRResult] = useState(() => readJsonStorage(TEM_R_RESULT_KEY, null))
  const [temRError, setTemRError] = useState("")
  const [temRColumns, setTemRColumns] = useState([])
  const [temRSheetOptions, setTemRSheetOptions] = useState([])
  const [temRSheetName, setTemRSheetName] = useState("")
  const [temRItemColumn, setTemRItemColumn] = useState("")
  const [temRStockColumn, setTemRStockColumn] = useState("")
  const [temRMaxDistance, setTemRMaxDistance] = useState(1)
  const [temRColumnMapping, setTemRColumnMapping] = useState({})
  const [temRInspecting, setTemRInspecting] = useState(false)
  const [temRInspectInfo, setTemRInspectInfo] = useState(null)
  const [expirationFile, setExpirationFile] = useState(null)
  const [expirationEntries, setExpirationEntries] = useState("")
  const [expirationLoading, setExpirationLoading] = useState(false)
  const [expirationResult, setExpirationResult] = useState(null)
  const [expirationError, setExpirationError] = useState("")
  const [expirationFilter, setExpirationFilter] = useState("all")
  const [expirationSort, setExpirationSort] = useState("expiry_desc")
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraMessage, setCameraMessage] = useState("")
  const [cameraError, setCameraError] = useState("")
  const cameraVideoRef = useRef(null)
  const cameraStreamRef = useRef(null)
  const cameraFrameRef = useRef(null)
  const cameraBusyRef = useRef(false)
  const cameraLastScanRef = useRef({ value: "", at: 0 })
  const healthFailureRef = useRef(0)
  const busyRef = useRef(false)
  const [step, setStep]           = useState(STEPS.idle)
  const [stepIdx, setStepIdx]     = useState(0)
  const [jobId, setJobId]         = useState(null)
  const [result, setResult]       = useState(null)   // {summary, warnings}
  const [preview, setPreview]     = useState(null)   // {sheets:{...}}
  const [activeSheet, setActiveSheet] = useState(null)
  const [error, setError]         = useState(null)
  const [backendStatus, setBackendStatus] = useState("checking") // checking | ok | offline
  const [queueStatus, setQueueStatus] = useState(null)
  const [mappingConfirmation, setMappingConfirmation] = useState(null)
  const [confirmCtkmMapping, setConfirmCtkmMapping] = useState({})
  const [confirmPogMapping, setConfirmPogMapping] = useState({})
  const [mappingConfirmSaving, setMappingConfirmSaving] = useState(false)
