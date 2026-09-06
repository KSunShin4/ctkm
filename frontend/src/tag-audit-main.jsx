import React, { useEffect, useState } from "react"
import ReactDOM from "react-dom/client"
import TagAudit from "./TagAudit.jsx"
import TagAuditQuickCamera from "./TagAuditQuickCamera.jsx"
import TagAuditPerceptionFeedback from "./TagAuditPerceptionFeedback.jsx"
import {
  cacheUploadedWorkbook,
  restoreTagAuditContext,
  workbookFromRequestBody,
} from "./tag-audit-context-cache.js"
import {
  BUSINESS_DATE_EVENT,
  emitBusinessDateState,
  staleBusinessDateMessage,
} from "./tag-audit-business-date-ui.js"

const nativeFetch = window.fetch.bind(window)

function emitUploadStatus(detail) {
  window.dispatchEvent(new CustomEvent("ctkm:tag-audit-upload-status", { detail }))
}

function emitPerceptionResult(detail) {
  window.dispatchEvent(new CustomEvent("ctkm:tag-audit-perception-result", { detail }))
}

window.fetch = async (...args) => {
  const request = args[0]
  const options = args[1] || {}
  const requestUrl = String(request instanceof Request ? request.url : request || "")
  const method = String(options.method || (request instanceof Request ? request.method : "GET") || "GET").toUpperCase()
  const isContextUrl = requestUrl.includes("/api/tag-audit/context")
  const isWorkbookUpload = method === "POST" && isContextUrl
  const isContextRead = method === "GET" && isContextUrl
  const isChecklistRead = method === "GET" && requestUrl.includes("/api/tag-audit/checklist")
  const isTagCheck = method === "POST" && requestUrl.includes("/api/tag-audit/check")

  try {
    let response = await nativeFetch(...args)

    // Cloud Run context is process-local. If a scale-to-zero/restart erased it,
    // transparently restore the last workbook explicitly uploaded on this device.
    // Never mask auth/validation failures: only the known no-context 409 path may restore.
    if (isContextRead && response.status === 409) {
      const restoreOptions = request instanceof Request ? { headers: request.headers } : options
      const restored = await restoreTagAuditContext(nativeFetch, restoreOptions)
      if (restored) {
        response = restored
        let restoredPayload = null
        try { restoredPayload = await restored.clone().json() } catch {}
        if (restoredPayload) emitBusinessDateState(restoredPayload)
        emitUploadStatus({
          kind: "success",
          message: `Đã tự khôi phục workbook trên thiết bị — ${restoredPayload?.item_count || 0} SKU / ${restoredPayload?.row_count || 0} dòng hành động.`,
        })
      }
    }

    // Business-date safety is owned by the backend. Mirror its context metadata in
    // the UI so a stale workbook is visible before a store user starts the camera.
    if (response.ok && (isContextRead || isWorkbookUpload || isChecklistRead || isTagCheck)) {
      let scannerPayload = null
      try { scannerPayload = await response.clone().json() } catch {}
      if (scannerPayload) emitBusinessDateState(scannerPayload)
    }

    if (isTagCheck) {
      let payload = null
      try { payload = await response.clone().json() } catch {}
      if (response.ok && payload && typeof payload === "object") emitPerceptionResult(payload)
    }

    if (!isWorkbookUpload) return response

    let payload = {}
    try { payload = await response.clone().json() } catch {}
    if (response.ok && payload?.ready) {
      const workbook = workbookFromRequestBody(options.body)
      if (workbook) await cacheUploadedWorkbook(workbook)
      emitUploadStatus({
        kind: "success",
        message: `Đã đọc được workbook — ${payload.item_count || 0} SKU / ${payload.row_count || 0} dòng hành động.`,
      })
    } else {
      const reason = typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`
      emitUploadStatus({ kind: "error", message: `Không đọc được workbook — ${reason}` })
    }
    return response
  } catch (error) {
    if (isWorkbookUpload) {
      emitUploadStatus({
        kind: "error",
        message: `Không đọc được workbook — ${error?.message || "Lỗi kết nối máy chủ"}`,
      })
    }
    throw error
  }
}

function UploadStatusBanner() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    const handler = event => setStatus(event.detail || null)
    window.addEventListener("ctkm:tag-audit-upload-status", handler)
    return () => window.removeEventListener("ctkm:tag-audit-upload-status", handler)
  }, [])

  if (!status) return null
  const success = status.kind === "success"
  return <div role="status" aria-live="polite" style={{
    maxWidth: 720,
    margin: "12px auto -2px",
    padding: "11px 14px",
    borderRadius: 12,
    border: `1px solid ${success ? "#abefc6" : "#fecdca"}`,
    background: success ? "#ecfdf3" : "#fef3f2",
    color: success ? "#067647" : "#b42318",
    font: "600 12px/1.45 Inter, ui-sans-serif, sans-serif",
  }}>
    {success ? "✓ " : "✕ "}{status.message}
  </div>
}

function PerceptionStatusBanner() {
  const [result, setResult] = useState(null)

  useEffect(() => {
    const handler = event => setResult(event.detail || null)
    window.addEventListener("ctkm:tag-audit-perception-result", handler)
    return () => window.removeEventListener("ctkm:tag-audit-perception-result", handler)
  }, [])

  return <TagAuditPerceptionFeedback result={result} />
}

function BusinessDateBanner({ state, quickMode = false }) {
  const message = staleBusinessDateMessage(state)
  if (!message) return null
  return <div role="alert" style={{
    maxWidth: 720,
    margin: "12px auto -2px",
    padding: "13px 14px",
    borderRadius: 12,
    border: "1px solid #fecdca",
    background: "#fef3f2",
    color: "#b42318",
    font: "650 12px/1.5 Inter, ui-sans-serif, sans-serif",
  }}>
    <strong>Không dùng workbook cũ để kiểm tem.</strong><br />
    {message}
    {quickMode && <div style={{marginTop:10}}>
      <a href="/scan-tem" style={{color:"#b42318",fontWeight:800}}>← Về Kiểm tem để tải workbook mới</a>
    </div>}
  </div>
}

function QuickModeLink() {
  return <div style={{maxWidth:720,margin:"12px auto -2px",padding:"0 14px"}}>
    <a href="/scan-tem?mode=quick" style={{display:"block",textAlign:"center",padding:"11px 14px",borderRadius:12,background:"#17202a",color:"#fff",textDecoration:"none",font:"750 13px/1.3 Inter, ui-sans-serif, sans-serif"}}>⚡ Quét nhanh · giữ camera mở</a>
  </div>
}

function TagAuditEntry() {
  const quickMode = new URLSearchParams(window.location.search).get("mode") === "quick"
  const [businessDate, setBusinessDate] = useState(null)

  useEffect(() => {
    const handler = event => setBusinessDate(event.detail || null)
    window.addEventListener(BUSINESS_DATE_EVENT, handler)
    return () => window.removeEventListener(BUSINESS_DATE_EVENT, handler)
  }, [])

  if (quickMode) return <>
    <UploadStatusBanner />
    <PerceptionStatusBanner />
    <BusinessDateBanner state={businessDate} quickMode />
    {!businessDate?.stale && <TagAuditQuickCamera />}
  </>

  return <>
    <UploadStatusBanner />
    <PerceptionStatusBanner />
    <BusinessDateBanner state={businessDate} />
    {!businessDate?.stale && <QuickModeLink />}
    <TagAudit />
    <aside style={{
      maxWidth: 720,
      margin: "-28px auto 28px",
      padding: "0 14px",
      color: "#667085",
      font: "11px/1.5 Inter, ui-sans-serif, sans-serif",
      textAlign: "center",
    }}>
      Nếu Gemini OCR được bật, ảnh tem được gửi tới Gemini chỉ để đọc chữ; dữ liệu CTKM chuẩn không được gửi kèm. Barcode chỉ là tín hiệu hỗ trợ.
    </aside>
  </>
}

ReactDOM.createRoot(document.getElementById("root")).render(<TagAuditEntry />)
