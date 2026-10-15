import { useEffect, useMemo, useRef, useState } from "react"
import {
  AUTO_CAPTURE_CONFIG,
  autoCaptureStatusText,
  createAutoCaptureController,
  createVideoSampler,
  getFrameRoi,
} from "./tag-audit-auto-capture.js"
import { chooseBarcodeCandidate } from "./tag-audit-barcode.js"
import { triggerHapticFeedback } from "./tag-audit-perception.js"
import { buildShelfReturnUrl, parseShelfCameraContext } from "./tag-audit-shelf-progress.js"

const API = import.meta.env.VITE_API_BASE_URL || ""

const styles = `
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1115;color:#fff}.quick{min-height:100vh;background:#0f1115}.quick-top{position:sticky;top:0;z-index:4;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;background:rgba(15,17,21,.96);border-bottom:1px solid #252a32}.quick-back{border:0;border-radius:10px;padding:9px 11px;background:#252a32;color:#fff;font-weight:700}.quick-progress{font-size:13px;text-align:right}.quick-progress strong{display:block;font-size:18px}.quick-main{max-width:720px;margin:0 auto;padding:12px}.quick-camera{position:relative;overflow:hidden;border-radius:18px;background:#000;min-height:56vh;display:flex;align-items:center;justify-content:center}.quick-camera video{width:100%;max-height:70vh;object-fit:cover}.quick-frame{position:absolute;inset:15% 8%;border:2px solid rgba(68,215,168,.9);border-radius:14px;box-shadow:0 0 0 999px rgba(0,0,0,.18);pointer-events:none}.quick-frame.wait{border-color:#fdb022}.quick-frame.locked{border-color:#53b1fd}.quick-hint{position:absolute;left:16px;right:16px;bottom:16px;padding:9px 10px;background:rgba(0,0,0,.72);border-radius:10px;font-size:12px;text-align:center}.quick-panel{margin-top:12px;border-radius:16px;background:#181c22;border:1px solid #292f38;padding:14px}.quick-btn{width:100%;border:0;border-radius:14px;padding:15px 16px;background:#0b8f68;color:#fff;font-size:16px;font-weight:850}.quick-btn:disabled{opacity:.45}.quick-result{margin-top:12px;border-radius:14px;padding:13px;background:#222831}.quick-result.ok{border:1px solid #32d583}.quick-result.bad{border:1px solid #f97066}.quick-result.warn{border:1px solid #fdb022}.quick-result h2{font-size:20px;margin:0 0 5px}.quick-result p{font-size:12px;color:#c7ced8;margin:0}.quick-facts{display:grid;grid-template-columns:100px 1fr;gap:5px 10px;margin-top:10px;font-size:12px}.quick-facts span:nth-child(odd){color:#98a2b3}.quick-error{margin-top:10px;color:#fda29b;font-size:12px}.quick-note{margin-top:9px;color:#98a2b3;font-size:11px;line-height:1.45}.quick-login{max-width:520px;margin:60px auto;padding:18px}.quick-link{display:block;text-align:center;margin-top:12px;color:#8ce5c7;font-size:12px}.spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-3px;margin-right:7px}.auto-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.auto-state{font-size:12px;color:#c7ced8}.auto-toggle{border:1px solid #3a424e;background:#252a32;color:#fff;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:800}.auto-toggle.on{background:#0b8f68;border-color:#0b8f68}.auto-metrics{display:flex;gap:8px;flex-wrap:wrap;margin-top:7px}.auto-chip{font-size:10px;color:#98a2b3;background:#222831;padding:5px 7px;border-radius:999px}.auto-chip.glare-alert{background:#f04438;color:#fff;font-weight:700}.quick-tools-overlay{position:absolute;top:14px;right:14px;z-index:5;display:flex;gap:8px;align-items:center}.quick-tool-btn{border:1px solid rgba(255,255,255,.2);background:rgba(15,17,21,.75);color:#fff;backdrop-filter:blur(8px);border-radius:999px;padding:6px 12px;font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:4px;transition:all .15s ease}.quick-tool-btn:active{transform:scale(.96)}.quick-tool-btn.active{background:#fdb022;color:#101828;border-color:#fdb022;font-weight:800}@keyframes spin{to{transform:rotate(360deg)}}
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

async function detectBarcodeFromCanvas(canvas) {
  if (!("BarcodeDetector" in window) || !canvas) return ""
  try {
    const supported = await window.BarcodeDetector.getSupportedFormats()
    const preferred = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39"].filter(x => supported.includes(x))
    if (!preferred.length) return ""
    const detector = new window.BarcodeDetector({ formats: preferred })
    const values = await detector.detect(canvas)
    return chooseBarcodeCandidate(values)
  } catch {
    return ""
  }
}

async function frameToBlob(video, frameEl) {
  if (!video?.videoWidth || !video?.videoHeight) throw new Error("Camera chưa sẵn sàng")
  const roi = getFrameRoi(video, frameEl)
  const sx = roi ? roi.sx : 0
  const sy = roi ? roi.sy : 0
  const sw = roi ? roi.sw : video.videoWidth
  const sh = roi ? roi.sh : video.videoHeight

  const canvas = document.createElement("canvas")
  const maxDim = 1280
  const scale = Math.min(1, maxDim / Math.max(sw, sh))
  canvas.width = Math.max(1, Math.round(sw * scale))
  canvas.height = Math.max(1, Math.round(sh * scale))
  const ctx = canvas.getContext("2d", { alpha: false })
  if (!ctx) throw new Error("Không tạo được ảnh camera")
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = "high"
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height)

  const barcodePromise = detectBarcodeFromCanvas(canvas)
  const blobPromise = new Promise((resolve, reject) =>
    canvas.toBlob(
      blob => (blob ? resolve(blob) : reject(new Error("Không chụp được ảnh camera"))),
      "image/jpeg",
      0.88
    )
  )

  const [blob, barcode] = await Promise.all([blobPromise, barcodePromise])
  return { blob, barcode }
}

export default function TagAuditQuickCamera() {
  const token = sessionStorage.getItem("ctkm.admin.token") || ""
  const videoRef = useRef(null)
  const frameRef = useRef(null)
  const streamRef = useRef(null)
  const controllerRef = useRef(null)
  const samplerRef = useRef(null)
  const scanRef = useRef(null)
  const loadingRef = useRef(false)
  const [context,setContext] = useState(null), [checklist,setChecklist] = useState([]), [progress,setProgress] = useState({})
  const [cameraReady,setCameraReady] = useState(false), [loading,setLoading] = useState(false), [result,setResult] = useState(null)
  const [error,setError] = useState("")
  const [autoEnabled,setAutoEnabled] = useState(true)
  const [autoDecision,setAutoDecision] = useState(null)
  const [hasTorch,setHasTorch] = useState(false), [torchOn,setTorchOn] = useState(false)
  const [hasZoom,setHasZoom] = useState(false), [zoomLevel,setZoomLevel] = useState(1), [zoomRange,setZoomRange] = useState({min:1,max:1,step:0.1})
  const shelfContext = useMemo(() => {
    if (typeof window === "undefined") return { shelf: "", itemId: "", checkKey: "", hasContext: false }
    return parseShelfCameraContext(window.location.search)
  }, [])

  const completed = useMemo(() => new Set(Object.keys(progress).filter(key => checklist.some(item => item.check_key === key))), [progress,checklist])
  const checked = completed.size, total = checklist.length, remaining = Math.max(0,total-checked)

  useEffect(() => {
    controllerRef.current = createAutoCaptureController()
    try {
      samplerRef.current = createVideoSampler(
        AUTO_CAPTURE_CONFIG,
        video => getFrameRoi(video, frameRef.current)
      )
    } catch (exc) {
      setError(exc.message)
      setAutoEnabled(false)
    }
    return () => { controllerRef.current = null; samplerRef.current = null }
  }, [])

  useEffect(() => {
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
    if (!context?.ready) return
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
        const track = stream.getVideoTracks()[0]
        if (track) {
          try {
            const caps = track.getCapabilities ? track.getCapabilities() : {}
            const adv = []
            if (caps.focusMode && Array.isArray(caps.focusMode) && caps.focusMode.includes("continuous")) {
              adv.push({ focusMode: "continuous" })
            }
            if (adv.length) await track.applyConstraints({ advanced: adv })

            if (caps.torch) {
              setHasTorch(true)
              setTorchOn(false)
            } else {
              setHasTorch(false)
              setTorchOn(false)
            }

            if (caps.zoom) {
              setHasZoom(true)
              const min = caps.zoom.min ?? 1
              const max = caps.zoom.max ?? 1
              const step = caps.zoom.step ?? 0.1
              setZoomRange({ min, max, step })
              const settings = track.getSettings ? track.getSettings() : {}
              setZoomLevel(settings.zoom ?? min)
            } else {
              setHasZoom(false)
              setZoomLevel(1)
            }
          } catch {}
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
          controllerRef.current?.reset()
          setCameraReady(true)
        }
      } catch (exc) {
        if (!cancelled) setError(`Không mở được camera: ${exc.message}`)
      }
    })()
    return () => {
      cancelled = true
      setCameraReady(false)
      setHasTorch(false)
      setTorchOn(false)
      setHasZoom(false)
      setZoomLevel(1)
      streamRef.current?.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }, [token,context?.context_id])

  const scan = async ({ source = "manual" } = {}) => {
    if (!cameraReady || loadingRef.current || !context?.ready) return
    if (source === "manual") controllerRef.current?.lockCurrent()
    loadingRef.current = true
    setLoading(true); setError("")
    try {
      const { blob, barcode } = await frameToBlob(videoRef.current, frameRef.current)
      const form = new FormData()
      form.append("image", new File([blob], `tag-${Date.now()}.jpg`, {type:"image/jpeg"}))
      form.append("manual_item_id", "")
      form.append("barcode_hint", barcode || "")
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
      triggerHapticFeedback(data.verdict || data)
    } catch (exc) {
      setError(exc.message)
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }
  scanRef.current = scan

  useEffect(() => {
    if (!autoEnabled || !cameraReady || !context?.ready || !samplerRef.current || !controllerRef.current) return
    let cancelled = false
    const timer = window.setInterval(() => {
      if (cancelled || loadingRef.current) return
      try {
        const sample = samplerRef.current(videoRef.current)
        const decision = controllerRef.current.inspect(sample)
        setAutoDecision(decision)
        if (decision.trigger) scanRef.current?.({ source: "auto" })
      } catch (exc) {
        setAutoDecision({ status: "camera_not_ready", quality: null, motion: Infinity })
      }
    }, AUTO_CAPTURE_CONFIG.intervalMs)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [autoEnabled,cameraReady,context?.context_id])

  const toggleAuto = () => {
    setAutoEnabled(current => {
      const next = !current
      controllerRef.current?.reset()
      setAutoDecision(null)
      return next
    })
  }

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track || !hasTorch) return
    const next = !torchOn
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] })
      setTorchOn(next)
    } catch (exc) {
      console.warn("Không bật/tắt được đèn flash:", exc)
    }
  }

  const cycleZoom = async () => {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track || !hasZoom) return
    const min = zoomRange.min
    const max = Math.min(zoomRange.max, 3)
    let next = 1
    if (zoomLevel < 1.4 && max >= 1.5) {
      next = 1.5
    } else if (zoomLevel < 1.9 && max >= 2.0) {
      next = 2.0
    } else {
      next = min
    }
    next = Math.max(min, Math.min(max, next))
    try {
      await track.applyConstraints({ advanced: [{ zoom: next }] })
      setZoomLevel(next)
    } catch (exc) {
      console.warn("Không đổi zoom được:", exc)
    }
  }

  const autoText = autoEnabled ? autoCaptureStatusText(autoDecision) : "Auto-capture đang tắt · dùng nút QUÉT TEM NÀY"
  const frameClass = autoEnabled && autoDecision?.status === "move_next" ? "quick-frame locked" : autoEnabled && autoDecision && autoDecision.status !== "capture" && autoDecision.status !== "ready" ? "quick-frame wait" : "quick-frame"

  return <><style>{styles}</style><div className="quick">
    <header className="quick-top">
      <button
        className="quick-back"
        onClick={() => location.href = shelfContext.hasContext ? buildShelfReturnUrl(shelfContext.shelf) : "/scan-tem"}
        title={shelfContext.shelf ? `Quay lại kiểm kệ ${shelfContext.shelf}` : "Quay lại chế độ thường"}
      >
        {shelfContext.shelf ? `← Kệ ${shelfContext.shelf}` : "← Thường"}
      </button>
      <div className="quick-progress"><span>Đã kiểm</span><strong>{checked} / {total}</strong><span>Còn {remaining}</span></div>
    </header>
    <main className="quick-main">
      {shelfContext.hasContext && (
        <div style={{margin:"0 0 10px",padding:"8px 12px",background:"rgba(83,177,253,0.12)",border:"1px solid rgba(83,177,253,0.3)",borderRadius:12,fontSize:11,color:"#8ce5c7",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <span>Đang ưu tiên: <strong>Kệ {shelfContext.shelf || "—"}</strong>{shelfContext.itemId ? ` · SKU ${shelfContext.itemId}` : ""}</span>
          <button type="button" onClick={()=>location.href=buildShelfReturnUrl(shelfContext.shelf)} style={{background:"none",border:0,color:"#fff",fontSize:11,fontWeight:750,cursor:"pointer",textDecoration:"underline"}}>Về kệ</button>
        </div>
      )}
      <div className="quick-camera">
        <video ref={videoRef} autoPlay playsInline muted/>
        <div ref={frameRef} className={frameClass}/>
        {(hasTorch || hasZoom) && (
          <div className="quick-tools-overlay">
            {hasTorch && (
              <button
                type="button"
                className={`quick-tool-btn ${torchOn ? "active" : ""}`}
                onClick={toggleTorch}
                aria-label={torchOn ? "Tắt flash" : "Bật flash"}
                title={torchOn ? "Tắt đèn flash" : "Bật đèn flash"}
              >
                {torchOn ? "⚡ Flash BẬT" : "⚡ Flash TẮT"}
              </button>
            )}
            {hasZoom && (
              <button
                type="button"
                className="quick-tool-btn"
                onClick={cycleZoom}
                aria-label={`Thu phóng ${zoomLevel}x`}
                title="Đổi mức thu phóng (1x · 1.5x · 2x)"
              >
                🔍 {zoomLevel.toFixed(1)}x
              </button>
            )}
          </div>
        )}
        <div className="quick-hint">{autoText}</div>
      </div>
      <section className="quick-panel">
        <div className="auto-row"><div><strong>Auto-capture an toàn</strong><div className="auto-state">{autoEnabled?"Bật · chỉ chụp khi ảnh đủ rõ và đứng yên":"Tắt · quét hoàn toàn bằng nút"}</div></div><button className={`auto-toggle ${autoEnabled?"on":""}`} onClick={toggleAuto}>{autoEnabled?"AUTO BẬT":"AUTO TẮT"}</button></div>
        {autoEnabled&&autoDecision?.quality&&<div className="auto-metrics">
          <span className="auto-chip">Sáng {autoDecision.quality.mean}</span>
          <span className="auto-chip">Tương phản {autoDecision.quality.stdDev}</span>
          <span className="auto-chip">Nét {autoDecision.quality.edgeEnergy}</span>
          <span className="auto-chip">Vùng nét {autoDecision.quality.activeTiles}/9</span>
          {autoDecision.quality.glareRatio > 0 && (
            <span className={`auto-chip ${autoDecision.quality.glareRatio > 0.35 ? "glare-alert" : ""}`}>
              Chói {Math.round(autoDecision.quality.glareRatio * 100)}%
            </span>
          )}
        </div>}
        <button className="quick-btn" disabled={!cameraReady||loading||!context?.ready} onClick={()=>scan({source:"manual"})} style={{marginTop:10}}>{loading?<><span className="spinner"/>Đang đọc tem…</>:cameraReady?"QUÉT TEM NÀY":"Đang mở camera…"}</button>
        {error&&<div className="quick-error">{error}</div>}
        {!context?.ready&&<div className="quick-note">Chưa có workbook CTKM. Về chế độ thường để tải workbook; nếu thiết bị đã cache workbook, hệ thống sẽ thử tự khôi phục.</div>}
        {result&&<div className={`quick-result ${resultClass(result.verdict?.severity)}`}>
          <h2>{result.verdict?.title||"Kết quả"}</h2>
          <p>{result.verdict?.detail||""}</p>
          <div className="quick-facts">
            <span>ITEMID</span><strong>{result.observed?.item_id||result.expected?.item_id||"—"}</strong>
            <span>Giá tem</span><strong>{money(result.observed?.promo_price)}</strong>
            <span>Giá chuẩn</span><strong>{money(result.expected?.promo_price)}</strong>
            <span>Tiến độ</span><strong>{checked} / {total} · còn {remaining}</strong>
          </div>
          {shelfContext.itemId && (result.observed?.item_id === shelfContext.itemId || result.expected?.item_id === shelfContext.itemId) && (
            <div style={{marginTop:8,color:"#32d583",fontSize:11,background:"rgba(50,213,131,0.12)",border:"1px solid rgba(50,213,131,0.3)",padding:"6px 10px",borderRadius:8}}>
              ✓ Đã đọc đúng SKU <strong>{shelfContext.itemId}</strong> đang kiểm trên kệ {shelfContext.shelf}
            </div>
          )}
          {result.observed?.item_id_candidates?.length > 1 && (
            <div style={{marginTop:8,color:"#fdb022",fontSize:11,background:"rgba(253,176,34,0.12)",padding:"6px 8px",borderRadius:8}}>
              ⚠ Nhận diện được {result.observed.item_id_candidates.length} mã: <strong>{result.observed.item_id_candidates.join(", ")}</strong>. Hãy đưa camera lại gần hơn để khung xanh chỉ chứa đúng 1 tem.
            </div>
          )}
          {result.vision_warning && (
            <div style={{marginTop:8,color:"#fda29b",fontSize:11,background:"rgba(249,112,102,0.12)",padding:"6px 8px",borderRadius:8}}>
              ⚠ Thông báo OCR: {result.vision_warning}
            </div>
          )}
          {result.observed?.ocr_warning && (
            <div style={{marginTop:8,color:"#fda29b",fontSize:11,background:"rgba(249,112,102,0.12)",padding:"6px 8px",borderRadius:8}}>
              ⚠ Cảnh báo: {result.observed.ocr_warning}
            </div>
          )}
          {result.observed?.raw_text && (
            <details style={{marginTop:10,background:"#16191f",border:"1px solid #292f38",borderRadius:8,padding:"7px 10px"}}>
              <summary style={{cursor:"pointer",fontSize:11,color:"#98a2b3"}}>
                Xem chữ đọc được trên tem ({result.observed.raw_text.length} ký tự)
              </summary>
              <pre style={{whiteSpace:"pre-wrap",fontSize:11,color:"#8ce5c7",margin:"6px 0 0",maxHeight:120,overflow:"auto",fontFamily:"monospace"}}>
                {result.observed.raw_text}
              </pre>
            </details>
          )}
          {!result.progress_eligible&&<div className="quick-note">Lần quét này chưa được cộng tiến độ vì chưa xác định chắc task/ITEMID. Có thể chuyển về chế độ thường để nhập tay.</div>}
        </div>}
        <div className="quick-note">Mẹo: Giữ camera cách tem khoảng 20cm, căn đúng 1 tem vào khung xanh và tránh ánh đèn chiếu trực tiếp làm lóa tem. Auto-capture chỉ chụp khi ảnh đủ rõ và đứng yên.</div>
      </section>
    </main>
  </div></>
}
