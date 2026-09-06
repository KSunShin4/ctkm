import React, { useEffect, useState } from "react"
import ReactDOM from "react-dom/client"
import TagAudit from "./TagAudit.jsx"
import TagAuditPerceptionFeedback from "./TagAuditPerceptionFeedback.jsx"

const nativeFetch = window.fetch.bind(window)

function emitUploadStatus(detail) {
  window.dispatchEvent(new CustomEvent("ctkm:tag-audit-upload-status", { detail }))
}

function emitPerceptionResult(detail) {
  window.dispatchEvent(new CustomEvent("ctkm:tag-audit-perception-result", { detail }))
}

window.fetch = async (...args) => {
  const requestUrl = String(args[0] instanceof Request ? args[0].url : args[0] || "")
  const method = String(args[1]?.method || (args[0] instanceof Request ? args[0].method : "GET") || "GET").toUpperCase()
  const isWorkbookUpload = method === "POST" && requestUrl.includes("/api/tag-audit/context")
  const isTagCheck = method === "POST" && requestUrl.includes("/api/tag-audit/check")

  try {
    const response = await nativeFetch(...args)

    if (isTagCheck) {
      let payload = null
      try { payload = await response.clone().json() } catch {}
      if (response.ok && payload && typeof payload === "object") emitPerceptionResult(payload)
    }

    if (!isWorkbookUpload) return response

    let payload = {}
    try { payload = await response.clone().json() } catch {}
    if (response.ok && payload?.ready) {
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

function TagAuditEntry() {
  return <>
    <UploadStatusBanner />
    <PerceptionStatusBanner />
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
