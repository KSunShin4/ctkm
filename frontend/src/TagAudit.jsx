import { useEffect, useMemo, useState } from "react"
import { chooseBarcodeCandidate } from "./tag-audit-barcode.js"

const API = import.meta.env.VITE_API_BASE_URL || ""

const styles = `
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f7f9;color:#17202a}button,input{font:inherit}.tag-shell{min-height:100vh}.tag-top{position:sticky;top:0;z-index:4;background:#fff;border-bottom:1px solid #e6e9ed;padding:14px 16px;display:flex;align-items:center;gap:12px}.tag-back{border:0;background:#f2f4f7;border-radius:10px;padding:8px 10px;cursor:pointer}.tag-brand{font-weight:800;font-size:17px}.tag-brand span{color:#087f5b}.tag-sub{font-size:11px;color:#667085}.tag-main{max-width:720px;margin:0 auto;padding:16px 14px 40px}.panel{background:#fff;border:1px solid #e6e9ed;border-radius:16px;padding:16px;margin-bottom:14px;box-shadow:0 1px 2px rgba(16,24,40,.04)}.panel-title{font-weight:750;font-size:15px;margin-bottom:5px}.muted{color:#667085;font-size:12px}.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:700}.pill.ok{background:#ecfdf3;color:#067647}.pill.warn{background:#fffaeb;color:#b54708}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field{display:flex;flex-direction:column;gap:5px;margin-top:10px}.field label{font-size:11px;color:#475467;font-weight:650}.field input{width:100%;border:1px solid #d0d5dd;border-radius:10px;padding:10px 11px;outline:none;background:#fff}.btn{width:100%;border:0;border-radius:12px;padding:12px 14px;font-weight:750;cursor:pointer}.btn.primary{background:#087f5b;color:#fff}.btn.secondary{background:#f2f4f7;color:#17202a;border:1px solid #e4e7ec}.btn:disabled{opacity:.45;cursor:not-allowed}.small-actions{display:flex;gap:8px;margin-top:10px}.small-actions .btn{padding:9px 10px;font-size:12px}.camera-box{position:relative;border:1px dashed #98a2b3;border-radius:16px;background:#0f1115;min-height:240px;display:flex;align-items:center;justify-content:center;overflow:hidden}.camera-box img{display:block;width:100%;max-height:520px;object-fit:contain}.camera-empty{color:#fff;text-align:center;padding:28px}.camera-empty strong{display:block;font-size:18px;margin-bottom:6px}.capture{position:absolute;inset:0;opacity:0;cursor:pointer}.scan-line{position:absolute;left:10%;right:10%;top:50%;border-top:2px solid #44d7a8;box-shadow:0 0 8px #44d7a8;pointer-events:none}.result{border-radius:16px;padding:16px;border:1px solid;margin-bottom:14px}.result.success{background:#ecfdf3;border-color:#abefc6}.result.warning{background:#fffaeb;border-color:#fedf89}.result.error{background:#fef3f2;border-color:#fecdca}.result h2{font-size:22px;margin:0 0 4px}.result p{font-size:13px;margin:0;color:#475467}.facts{display:grid;grid-template-columns:130px 1fr;gap:7px 12px;margin-top:14px;font-size:12px}.facts dt{color:#667085}.facts dd{margin:0;font-weight:650;word-break:break-word}.compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.compare-card{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:12px;padding:12px}.compare-card h4{margin:0 0 8px;font-size:12px;color:#667085}.big-price{font-weight:800;font-size:20px}.error-text{color:#b42318;font-size:12px;margin-top:8px}.loader{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-3px}@keyframes spin{to{transform:rotate(360deg)}}.login{max-width:420px;margin:60px auto;padding:20px}.context-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.context-meta{font-size:11px;color:#667085;margin-top:4px}.barcode-note{margin-top:8px;background:#f8fafc;border-radius:9px;padding:8px 10px;color:#475467;font-size:11px}.advanced{margin-top:12px}.advanced summary{cursor:pointer;color:#475467;font-size:12px;font-weight:650}.observed-raw{white-space:pre-wrap;font-size:11px;color:#667085;background:#f8fafc;border-radius:10px;padding:10px;margin-top:10px;max-height:140px;overflow:auto}.footer-note{text-align:center;color:#98a2b3;font-size:10px;margin-top:16px}.progress-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}.progress-big{font-size:30px;font-weight:850;letter-spacing:-1px}.progress-big span{font-size:14px;color:#667085;font-weight:650;letter-spacing:0}.progress-track{height:12px;background:#eef2f4;border-radius:999px;overflow:hidden;margin:12px 0 10px}.progress-fill{height:100%;background:#087f5b;border-radius:999px;transition:width .25s ease}.progress-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.progress-stat{background:#f8fafc;border-radius:10px;padding:9px;text-align:center;font-size:11px;color:#667085}.progress-stat strong{display:block;font-size:17px;color:#17202a}.remaining-list{margin-top:12px;border-top:1px solid #eef2f4}.remaining-row{padding:11px 0;border-bottom:1px solid #eef2f4}.remaining-id{font-weight:800;font-size:13px}.remaining-name{font-size:12px;margin-top:2px}.remaining-meta{font-size:10px;color:#667085;margin-top:4px}.search-row{display:flex;gap:8px;margin-top:10px}.search-row input{flex:1;border:1px solid #d0d5dd;border-radius:10px;padding:9px 10px}.search-row button{width:auto;padding:9px 12px}.progress-note{font-size:10px;color:#667085;margin-top:8px}@media(max-width:560px){.grid2,.compare{grid-template-columns:1fr}.facts{grid-template-columns:105px 1fr}.tag-main{padding:12px 10px 32px}.panel{border-radius:14px;padding:14px}.tag-top{padding:11px 12px}.camera-box{min-height:300px}.progress-stats{grid-template-columns:repeat(3,1fr)}}
`

function authHeaders(token) { return token ? { Authorization: `Bearer ${token}` } : {} }

async function apiJson(url, options = {}) {
  const response = await fetch(`${API}${url}`, options)
  let body = null
  try { body = await response.json() } catch { body = {} }
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`
    const error = new Error(detail); error.status = response.status; throw error
  }
  return body
}

function money(value) {
  if (value === null || value === undefined || value === "") return "—"
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toLocaleString("vi-VN")} đ` : String(value)
}
function dateText(value) {
  if (!value) return "—"
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value)
}
function severityClass(severity) { return severity === "success" ? "success" : severity === "error" ? "error" : "warning" }
function localDay() {
  const d = new Date(); const y = d.getFullYear(); const m = String(d.getMonth()+1).padStart(2,"0"); const day = String(d.getDate()).padStart(2,"0")
  return `${y}-${m}-${day}`
}
function progressStorageKey(contextId) { return contextId ? `ctkm.tag-progress.v1:${localDay()}:${contextId}` : "" }
function readProgress(contextId) {
  const key = progressStorageKey(contextId); if (!key) return {}
  try { const value = JSON.parse(localStorage.getItem(key) || "{}"); return value && typeof value === "object" ? value : {} } catch { return {} }
}
function writeProgress(contextId, value) {
  const key = progressStorageKey(contextId); if (!key) return
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

async function detectBarcode(file) {
  if (!("BarcodeDetector" in window)) return ""
  try {
    const supported = await window.BarcodeDetector.getSupportedFormats()
    const preferred = ["ean_13","ean_8","upc_a","upc_e","code_128","code_39"].filter(x => supported.includes(x))
    if (!preferred.length) return ""
    const detector = new window.BarcodeDetector({ formats: preferred }); const bitmap = await createImageBitmap(file)
    try { const values = await detector.detect(bitmap); return chooseBarcodeCandidate(values) } finally { bitmap.close?.() }
  } catch { return "" }
}

export default function TagAudit() {
  const [token,setToken] = useState(() => sessionStorage.getItem("ctkm.admin.token") || "")
  const [username,setUsername] = useState("admin"), [password,setPassword] = useState(""), [authError,setAuthError] = useState("")
  const [context,setContext] = useState(null), [contextError,setContextError] = useState(""), [contextLoading,setContextLoading] = useState(false)
  const [checklist,setChecklist] = useState([]), [progress,setProgress] = useState({}), [showRemaining,setShowRemaining] = useState(false), [search,setSearch] = useState("")
  const [imageFile,setImageFile] = useState(null), [imageUrl,setImageUrl] = useState(""), [barcodeHint,setBarcodeHint] = useState("")
  const [manualItemId,setManualItemId] = useState(""), [manualPrice,setManualPrice] = useState(""), [manualNormalPrice,setManualNormalPrice] = useState("")
  const [manualFrom,setManualFrom] = useState(""), [manualTo,setManualTo] = useState(""), [manualPromoText,setManualPromoText] = useState("")
  const [checking,setChecking] = useState(false), [result,setResult] = useState(null), [checkError,setCheckError] = useState("")

  const ready = Boolean(context?.ready)
  const contextLabel = useMemo(() => !context?.ready ? "Chưa có dữ liệu CTKM" : context.source === "latest-job" ? `Job ${context.job_id || "gần nhất"}${context.month ? ` · ${context.month}` : ""}` : `Workbook đã tải · ${context.item_count || 0} SKU`, [context])
  const completedKeys = useMemo(() => new Set(Object.keys(progress).filter(key => checklist.some(item => item.check_key === key))), [progress,checklist])
  const checked = completedKeys.size, total = checklist.length, remaining = Math.max(0,total-checked), percent = total ? Math.round(checked*100/total) : 0
  const stateCounts = useMemo(() => {
    const counts = {pass:0,fail:0,review:0}; completedKeys.forEach(key => { const state = progress[key]?.state; if (counts[state] !== undefined) counts[state] += 1 }); return counts
  }, [completedKeys,progress])
  const remainingItems = useMemo(() => {
    const q = search.trim().toLowerCase()
    return checklist.filter(item => !completedKeys.has(item.check_key)).filter(item => !q || [item.item_id,item.item_name,item.pog_code,item.location_id,item.campaign_name,item.campaign_detail].some(v => String(v || "").toLowerCase().includes(q)))
  }, [checklist,completedKeys,search])

  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl) }, [imageUrl])
  useEffect(() => { if (context?.context_id) setProgress(readProgress(context.context_id)); else setProgress({}) }, [context?.context_id])

  const loadChecklist = async () => {
    const data = await apiJson("/api/tag-audit/checklist", { headers: authHeaders(token) })
    setChecklist(Array.isArray(data.items) ? data.items : [])
    if (data.context) setContext(data.context)
  }
  const loadContext = async () => {
    setContextLoading(true); setContextError("")
    try { const data = await apiJson("/api/tag-audit/context", { headers: authHeaders(token) }); setContext(data); await loadChecklist() }
    catch (error) { if (error.status === 401) { sessionStorage.removeItem("ctkm.admin.token"); setToken("") } else setContextError(error.message) }
    finally { setContextLoading(false) }
  }
  useEffect(() => { loadContext() }, [token])

  const login = async event => {
    event.preventDefault(); setAuthError("")
    const form = new FormData(); form.append("username",username); form.append("password",password)
    try { const data = await apiJson("/api/auth/login", {method:"POST",body:form}); sessionStorage.setItem("ctkm.admin.token",data.access_token); setToken(data.access_token); setPassword("") }
    catch (error) { setAuthError(error.message) }
  }
  const uploadContext = async file => {
    if (!file) return
    setContextLoading(true); setContextError("")
    const form = new FormData(); form.append("workbook",file)
    try { const data = await apiJson("/api/tag-audit/context", {method:"POST",headers:authHeaders(token),body:form}); setContext(data); const checklistData = await apiJson("/api/tag-audit/checklist", {headers:authHeaders(token)}); setChecklist(checklistData.items || []) }
    catch (error) { setContextError(error.message) } finally { setContextLoading(false) }
  }
  const chooseImage = async file => {
    if (!file) return
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageFile(file); setImageUrl(URL.createObjectURL(file)); setResult(null); setCheckError(""); setBarcodeHint(await detectBarcode(file))
  }
  const recordProgress = data => {
    if (!context?.context_id || !data?.progress_eligible || !data?.check_key) return
    setProgress(current => {
      const next = {...current, [data.check_key]: {state:data.progress_state || "review", verdict:data.verdict?.code || "", item_id:data.expected?.item_id || "", at:new Date().toISOString()}}
      writeProgress(context.context_id,next); return next
    })
  }
  const runCheck = async () => {
    if (!imageFile || !ready) return
    setChecking(true); setCheckError(""); setResult(null)
    const form = new FormData(); form.append("image",imageFile); form.append("manual_item_id",manualItemId.trim()); form.append("barcode_hint",barcodeHint.trim()); form.append("manual_promo_price",manualPrice.trim()); form.append("manual_normal_price",manualNormalPrice.trim()); form.append("manual_promo_from",manualFrom.trim()); form.append("manual_promo_to",manualTo.trim()); form.append("manual_promo_text",manualPromoText.trim())
    try { const data = await apiJson("/api/tag-audit/check", {method:"POST",headers:authHeaders(token),body:form}); setResult(data); recordProgress(data); if (!manualItemId && data.observed?.item_id) setManualItemId(data.observed.item_id); if (!barcodeHint && data.observed?.barcode) setBarcodeHint(data.observed.barcode) }
    catch (error) { setCheckError(error.message) } finally { setChecking(false) }
  }
  const resetScan = () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageFile(null); setImageUrl(""); setBarcodeHint(""); setManualItemId(""); setManualPrice(""); setManualNormalPrice(""); setManualFrom(""); setManualTo(""); setManualPromoText(""); setResult(null); setCheckError("")
  }

  return <><style>{styles}</style><div className="tag-shell"><header className="tag-top"><button className="tag-back" onClick={()=>location.href="/"}>←</button><div><div className="tag-brand">CTKM <span>Kiểm tem</span></div><div className="tag-sub">ITEMID ưu tiên · barcode chỉ hỗ trợ</div></div></header><main className="tag-main">
    <section className="panel"><div className="context-row"><div><div className="panel-title">1. Dữ liệu chuẩn</div><div className="muted">{contextLabel}</div></div>{context?.ready?<span className="pill ok">● Sẵn sàng</span>:<span className="pill warn">● Cần dữ liệu</span>}</div>{contextError&&<div className="error-text">{contextError}</div>}{!context?.ready&&<div className="field"><label>Tải workbook kết quả CTKM</label><input type="file" accept=".xlsx" onChange={e=>uploadContext(e.target.files?.[0])}/></div>}<div className="small-actions"><button className="btn secondary" disabled={contextLoading} onClick={loadContext}>{contextLoading?"Đang nạp…":"Dùng job CTKM gần nhất"}</button>{context?.ready&&<label className="btn secondary" style={{cursor:"pointer"}}>Đổi workbook<input type="file" accept=".xlsx" hidden onChange={e=>uploadContext(e.target.files?.[0])}/></label>}</div></section>

    {context?.ready&&<section className="panel"><div className="progress-head"><div><div className="panel-title">Tiến độ hôm nay</div><div className="progress-big">{checked} / {total} <span>{percent}%</span></div></div><span className={remaining===0?"pill ok":"pill warn"}>{remaining===0?"✓ Đã kiểm đủ":`Còn ${remaining}`}</span></div><div className="progress-track"><div className="progress-fill" style={{width:`${percent}%`}}/></div><div className="progress-stats"><div className="progress-stat"><strong>{stateCounts.pass}</strong>Đúng</div><div className="progress-stat"><strong>{stateCounts.fail}</strong>Sai</div><div className="progress-stat"><strong>{stateCounts.review}</strong>Review</div></div><button className="btn secondary" style={{marginTop:10}} onClick={()=>setShowRemaining(v=>!v)}>{showRemaining?"Ẩn danh sách còn lại":`Xem ${remaining} mục chưa kiểm`}</button><div className="progress-note">Tiến độ lưu trên thiết bị này theo ngày + workbook. V1 đếm promotion cần gắn tem, không giả định từng vị trí POG khi cùng promotion có nhiều vị trí.</div>{showRemaining&&<><div className="search-row"><input placeholder="Tìm ITEMID / tên / POG / vị trí" value={search} onChange={e=>setSearch(e.target.value)}/><button className="btn secondary" onClick={()=>setSearch("")}>Xóa</button></div><div className="remaining-list">{remainingItems.slice(0,100).map(item=><div className="remaining-row" key={item.check_key}><div className="remaining-id">{item.item_id||"—"}</div><div className="remaining-name">{item.item_name||item.campaign_detail||item.campaign_name||"—"}</div><div className="remaining-meta">{[item.pog_code,item.location_id,item.campaign_name].filter(Boolean).join(" · ")}</div></div>)}{remainingItems.length===0&&<div className="muted" style={{paddingTop:12}}>Không còn mục phù hợp.</div>}{remainingItems.length>100&&<div className="muted" style={{paddingTop:10}}>Đang hiện 100/{remainingItems.length} mục. Hãy tìm theo ITEMID hoặc POG để thu hẹp.</div>}</div></>}</section>}

    <section className="panel"><div className="panel-title">2. Chụp một tem</div><div className="muted">Đưa tem vào gần camera, ưu tiên thấy rõ mã Pxxxxx, giá và ngày KM.</div><div className="camera-box" style={{marginTop:12}}>{imageUrl?<><img src={imageUrl} alt="Tem cần kiểm"/><div className="scan-line"/></>:<div className="camera-empty"><strong>Chạm để chụp tem</strong><span>Pxxxxx · giá · ngày KM cần rõ</span></div>}<input className="capture" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e=>chooseImage(e.target.files?.[0])}/></div>{barcodeHint&&<div className="barcode-note">Barcode: <strong>{barcodeHint}</strong> · chỉ hỗ trợ.</div>}<div className="field"><label>Mã sản phẩm (nếu OCR khó đọc)</label><input placeholder="Ví dụ P30766" value={manualItemId} onChange={e=>setManualItemId(e.target.value.toUpperCase())}/></div><details className="advanced"><summary>Nhập tay khi ảnh khó đọc</summary><div className="grid2"><div className="field"><label>Giá KM</label><input inputMode="numeric" value={manualPrice} onChange={e=>setManualPrice(e.target.value)}/></div><div className="field"><label>Giá thường</label><input inputMode="numeric" value={manualNormalPrice} onChange={e=>setManualNormalPrice(e.target.value)}/></div><div className="field"><label>Từ ngày</label><input type="date" value={manualFrom} onChange={e=>setManualFrom(e.target.value)}/></div><div className="field"><label>Đến ngày</label><input type="date" value={manualTo} onChange={e=>setManualTo(e.target.value)}/></div></div><div className="field"><label>Nội dung KM</label><input value={manualPromoText} onChange={e=>setManualPromoText(e.target.value)}/></div></details><button className="btn primary" disabled={!imageFile||!ready||checking} style={{marginTop:14}} onClick={runCheck}>{checking?<><span className="loader"/> Đang đọc và đối chiếu…</>:"Kiểm tra tem"}</button>{checkError&&<div className="error-text">{checkError}</div>}</section>

    {result&&<section className={`result ${severityClass(result.verdict?.severity)}`}><h2>{result.verdict?.title}</h2><p>{result.verdict?.detail}</p>{result.progress_eligible&&<div className="barcode-note"><strong>Tiến độ: {checked} / {total}</strong> · còn {remaining}. Quét lại cùng mục không cộng thêm.</div>}{result.observed?.item_id_candidates?.length > 1 && <div className="barcode-note" style={{color:"#b54708",background:"#fffaeb",border:"1px solid #fedf89",marginTop:8}}>⚠ Đọc được {result.observed.item_id_candidates.length} mã trong ảnh: <strong>{result.observed.item_id_candidates.join(", ")}</strong>. Chọn mã cần kiểm:<div style={{display:"flex",gap:6,marginTop:6,flexWrap:"wrap"}}>{result.observed.item_id_candidates.map(id => <button key={id} type="button" className="pill ok" style={{cursor:"pointer",border:"1px solid #abefc6"}} onClick={()=>{ setManualItemId(id); }}>Chọn {id}</button>)}</div></div>}<div className="compare"><div className="compare-card"><h4>TRÊN TEM</h4><div className="big-price">{money(result.observed?.promo_price)}</div><dl className="facts"><dt>Mã đọc được</dt><dd>{result.observed?.item_id||"—"}</dd><dt>Barcode</dt><dd>{result.observed?.barcode||"—"}</dd><dt>Từ</dt><dd>{dateText(result.observed?.promo_from)}</dd><dt>Đến</dt><dd>{dateText(result.observed?.promo_to)}</dd><dt>KM</dt><dd>{result.observed?.promo_text||"—"}</dd></dl></div><div className="compare-card"><h4>THEO CTKM</h4><div className="big-price">{money(result.expected?.promo_price)}</div><dl className="facts"><dt>ITEMID</dt><dd>{result.expected?.item_id||"—"}</dd><dt>Tên</dt><dd>{result.expected?.item_name||"—"}</dd><dt>Từ</dt><dd>{dateText(result.expected?.promo_from)}</dd><dt>Đến</dt><dd>{dateText(result.expected?.promo_to)}</dd><dt>Campaign</dt><dd>{result.expected?.campaign_detail||result.expected?.campaign_name||"—"}</dd><dt>Vị trí</dt><dd>{[result.expected?.pog_code,result.expected?.location_id].filter(Boolean).join(" · ")||"—"}</dd></dl></div></div>{result.vision_warning&&<div className="barcode-note">OCR ảnh: {result.vision_warning}</div>}{result.observed?.raw_text&&<div className="observed-raw">{result.observed.raw_text}</div>}<div className="small-actions"><button className="btn primary" onClick={resetScan}>Quét tem tiếp theo</button><button className="btn secondary" onClick={runCheck}>Kiểm lại</button></div></section>}
    <div className="footer-note">Nguồn quyết định: CTKM hiện tại. OCR và barcode chỉ hỗ trợ đọc tem thực tế.</div>
  </main></div></>
}
