export const BUSINESS_DATE_EVENT = "ctkm:tag-audit-business-date"

function contextFromPayload(payload) {
  if (!payload || typeof payload !== "object") return null
  if (payload.context && typeof payload.context === "object") return payload.context
  if (Object.prototype.hasOwnProperty.call(payload, "business_date_stale")) return payload
  return null
}

export function businessDateState(payload) {
  const context = contextFromPayload(payload)
  if (!context) return null
  return {
    stale: context.business_date_stale === true,
    businessDate: String(context.business_date || "").trim(),
    scannerBusinessDate: String(context.scanner_business_date || "").trim(),
    reportMonth: String(context.report_month || context.month || "").trim(),
  }
}

export function emitBusinessDateState(payload, target = window) {
  const state = businessDateState(payload)
  if (!state) return null
  target.dispatchEvent(new CustomEvent(BUSINESS_DATE_EVENT, { detail: state }))
  return state
}

export function formatBusinessDate(value) {
  const text = String(value || "").trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : text
}

export function staleBusinessDateMessage(state) {
  if (!state?.stale) return ""
  const report = formatBusinessDate(state.businessDate) || "không rõ"
  const today = formatBusinessDate(state.scannerBusinessDate) || "hôm nay"
  return `Workbook kiểm tem đang theo ngày ${report}; ngày kiểm hiện tại là ${today}. Hãy chạy hoặc tải workbook CTKM mới trước khi kiểm tem.`
}
