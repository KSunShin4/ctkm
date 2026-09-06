import { useEffect, useMemo, useRef, useState } from "react"

const API = import.meta.env.VITE_API_BASE_URL || ""

const styles = `
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1115;color:#fff}.quick{min-height:100vh;background:#0f1115}.quick-top{position:sticky;top:0;z-index:4;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;background:rgba(15,17,21,.96);border-bottom:1px solid #252a32}.quick-back{border:0;border-radius:10px;padding:9px 11px;background:#252a32;color:#fff;font-weight:700}.quick-progress{font-size:13px;text-align:right}.quick-progress strong{display:block;font-size:18px}.quick-main{max-width:720px;margin:0 auto;padding:12px}.quick-camera{position:relative;overflow:hidden;border-radius:18px;background:#000;min-height:56vh;display:flex;align-items:center;justify-content:center}.quick-camera video{width:100%;max-height:70vh;object-fit:cover}.quick-frame{position:absolute;inset:15% 8%;border:2px solid rgba(68,215,168,.9);border-radius:14px;box-shadow:0 0 0 999px rgba(0,0,0,.18);pointer-events:none}.quick-hint{position:absolute;left:16px;right:16px;bottom:16px;padding:9px 10px;background:rgba(0,0,0,.65);border-radius:10px;font-size:12px;text-align:center}.quick-panel{margin-top:12px;border-radius:16px;background:#181c22;border:1px solid #292f38;padding:14px}.quick-btn{width:100%;border:0;border-radius:14px;padding:15px 16px;background:#0b8f68;color:#fff;font-size:16px;font-weight:850}.quick-btn:disabled{opacity:.45}.quick-result{margin-top:12px;border-radius:14px;padding:13px;background:#222831}.quick-result.ok{border:1px solid #32d583}.quick-result.bad{border:1px solid #f97066}.quick-result.warn{border:1px solid #fdb022}.quick-result h2{font-size:20px;margin:0 0 5px}.quick-result p{font-size:12px;color:#c7ced8;margin:0}.quick-facts{display:grid;grid-template-columns:100px 1fr;gap:5px 10px;margin-top:10px;font-size:12px}.quick-facts span:nth-child(odd){color:#98a2b3}.quick-error{margin-top:10px;color:#fda29b;font-size:12px}.quick-note{margin-top:9px;color:#98a2b3;font-size:11px;line-height:1.45}.quick-login{max-width:520px;margin:60px auto;padding:18px}.quick-link{display:block;text-align:center;margin-top:12px;color:#8ce5c7;font-size:12px}.spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-3px;margin-right:7px}@keyframes spin{to{transform:rotate(360deg)}}
`

function authHeaders(token) { return token ? { Authorization: `Bearer ${token}` } : {} }

async function apiJson(url, options = {}) {
  const response = await fetch(`${API}${url}`, options)
  let body = {}
  try { body = await response.json() } catch {}
  if (!response.ok) {
    const error = new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`)
    error.status = response.status
    throw error
  }
  return body
}

function localDay() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`
}
function progressKey(contextId) { return contextId ? `ctkm.tag-progress.v1:${localDay()}:${contextId}` : "" }
function readProgress(contextId) {
  const key = progressKey(contextId); if (!key) return {}
  try { const value = JSON.parse(localStorage.getItem(key) || "{}"); return value && typeof value === "object" ? value : {} } catch { return {} }
}
function writeProgress(contextId, value) {
  const key = progressKey(contextId); if (!key) return
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}
function money(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toLocaleString("vi-VN")} đ` : "—"
}
function resultClass(severity) { return severity === "success" ? "ok" : severity === "error" ? "bad" : "warn" }

async function frameToBlob(video) {
  if (!video?.videoWidth || !video?.videoHeight) throw new Error("Camera chưa sẵn sàng")
  const canvas = document.createElement("canvas")
  const maxWidth = 1600
  const scale = Math.min(1, maxWidth / video.videoWidth)
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale))
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale))
  const ctx = canvas.getContext("2d", { alpha: false })
  if (!ctx) throw new Error("Không tạo được ảnh camera")
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  return await new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Không chụp được ảnh camera")), "image/jpeg", .92))
}

export default function TagAuditQuickCamera() {
  const token = sessionStorage.getItem("ctkm.admin.token") || ""
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [context,setContext] = useState(null), [checklist,setChecklist] = useState([]), [progress,setProgress] = useState({})
  const [cameraReady,setCameraReady] = useState(false), [loading,setLoading] = useState(false), [result,setResult] = useState(null)
  const [error,setError] = useState("")

  const completed = useMemo(() => new Set(Object.keys(progress).filter(key => checklist.some(item => item.check_key === key))), [progress,checklist])
  const checked = completed.size, total = checklist.length, remaining = Math.max(0,total-checked)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    ;(async () => {
      try {
        const ctx = await apiJson("/api/tag-audit/context", {headers:authHeaders(token)})
        const list = await apiJson("/api/tag-audit/checklist", {headers:authHeaders(token)})
        if (cancelled) return
        const resolvedContext = list.context || ctx
        setContext(resolvedContext)
        setChecklist(Array.isArray(list.items) ? list.items : [])
        setProgress(readProgress(resolvedContext?.context_id))
      } catch (exc) {
        if (!cancelled) setError(exc.message)
      }
    })()
    return () => { cancelled = true }
  }, [token])

  useEffect(() => {
    if (!token || !context?.ready) return
    let cancelled = false
    ;(async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Trình duyệt không hỗ trợ camera trực tiếp")
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        })
        if (cancelled) { stream.getTracks().forEach(track => track.stop()); return }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
          setCameraReady(true)
        }
      } catch (exc) {
        if (!cancelled) setError(`Không mở được camera: ${exc.message}`)
      }
    })()
    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }, [token,context?.context_id])

  const scan = async () => {
    if (!cameraReady || loading || !context?.ready) return
    setLoading(true); setError("")
    try {
      const blob = await frameToBlob(videoRef.current)
      const form = new FormData()
      form.append("image", new File([blob], `tag-${Date.now()}.jpg`, {type:"image/jpeg"}))
      form.append("manual_item_id", "")
      form.append("barcode_hint", "")
      form.append("manual_promo_price", "")
      form.append("manual_normal_price", "")
      form.append("manual_promo_from", "")
      form.append("manual_promo_to", "")
      form.append("manual_promo_text", "")
      const data = await apiJson("/api/tag-audit/check", {method:"POST",headers:authHeaders(token),body:form})
      setResult(data)
      if (data.progress_eligible && data.check_key && context?.context_id) {
        setProgress(current => {
          const next = {...current,[data.check_key]:{state:data.progress_state||"review",verdict:data.verdict?.code||"",item_id:data.expected?.item_id||"",at:new Date().toISOString()}}
          writeProgress(context.context_id,next)
          return next
        })
      }
      if (navigator.vibrate) {
        const severity = data.verdict?.severity
        navigator.vibrate(severity === "success" ? 70 : severity === "error" ? [130,70,130] : [70,60,70])
      }
    } catch (exc) {
      setError(exc.message)
    } finally { setLoading(false) }
  }

  if (!token) return <><style>{styles}</style><div className="quick"><div className="quick-login"><h2>Cần đăng nhập</h2><p>Quét nhanh dùng cùng phiên đăng nhập của Kiểm tem.</p><a className="quick-link" href="/scan-tem">← Về Kiểm tem để đăng nhập</a></div></div></>

  return <><style>{styles}</style><div className="quick">
    <header className="quick-top"><button className="quick-back" onClick={()=>location.href="/scan-tem"}>← Thường</button><div className="quick-progress"><span>Đã kiểm</span><strong>{checked} / {total}</strong><span>Còn {remaining}</span></div></header>
    <main className="quick-main">
      <div className="quick-camera"><video ref={videoRef} autoPlay playsInline muted/><div className="quick-frame"/><div className="quick-hint">Đưa một tem vào khung · thấy rõ Pxxxxx, giá và ngày KM</div></div>
      <section className="quick-panel"><button className="quick-btn" disabled={!cameraReady||loading||!context?.ready} onClick={scan}>{loading?<><span className="spinner"/>Đang đọc tem…</>:cameraReady?"QUÉT TEM NÀY":"Đang mở camera…"}</button>
        {error&&<div className="quick-error">{error}</div>}
        {!context?.ready&&<div className="quick-note">Chưa có workbook CTKM. Về chế độ thường để tải workbook; nếu thiết bị đã cache workbook, hệ thống sẽ thử tự khôi phục.</div>}
        {result&&<div className={`quick-result ${resultClass(result.verdict?.severity)}`}><h2>{result.verdict?.title||"Kết quả"}</h2><p>{result.verdict?.detail||""}</p><div className="quick-facts"><span>ITEMID</span><strong>{result.observed?.item_id||result.expected?.item_id||"—"}</strong><span>Giá tem</span><strong>{money(result.observed?.promo_price)}</strong><span>Giá chuẩn</span><strong>{money(result.expected?.promo_price)}</strong><span>Tiến độ</span><strong>{checked} / {total} · còn {remaining}</strong></div>{!result.progress_eligible&&<div className="quick-note">Lần quét này chưa được cộng tiến độ vì chưa xác định chắc task/ITEMID. Có thể chuyển về chế độ thường để nhập tay.</div>}</div>}
        <div className="quick-note">Camera được giữ mở giữa các lần quét. Mỗi lần bấm vẫn gửi đúng một ảnh tới backend deterministic hiện tại; chưa bật auto-capture.</div>
      </section>
    </main>
  </div></>
}
