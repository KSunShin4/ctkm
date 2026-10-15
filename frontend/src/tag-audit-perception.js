const ENGINE_LABELS = {
  rapidocr: "RapidOCR",
  "rapidocr+gemini": "RapidOCR + Gemini fallback",
  gemini: "Gemini fallback",
}

const BARCODE_SOURCE_LABELS = {
  browser: "Camera trình duyệt",
  ocr: "OCR",
  zxingcpp: "ZXing",
  zxingcpp_ambiguous: "ZXing · nhiều mã",
  zxingcpp_none: "ZXing · không thấy mã",
  zxingcpp_error: "ZXing · lỗi đọc",
}

export function perceptionSummary(result, browserBarcode = "") {
  const observed = result?.observed || {}
  const quality = observed.image_quality || null
  const warnings = Array.isArray(quality?.warnings)
    ? quality.warnings
        .filter(item => item && typeof item.message === "string" && item.message.trim())
        .map(item => ({ code: String(item.code || "image_quality"), message: item.message.trim() }))
    : []

  if (observed.image_quality_warning) {
    warnings.push({
      code: "image_preprocessor_error",
      message: `Tiền xử lý ảnh không dùng được: ${observed.image_quality_warning}`,
    })
  }

  const engine = ENGINE_LABELS[observed.ocr_engine] || String(observed.ocr_engine || "OCR").trim() || "OCR"
  const barcodeSourceKey = browserBarcode
    ? "browser"
    : String(observed.barcode_source || "").trim()
  const barcodeSource = BARCODE_SOURCE_LABELS[barcodeSourceKey] || barcodeSourceKey

  return {
    engine,
    confidence: Number.isFinite(Number(observed.confidence)) ? Number(observed.confidence) : null,
    quality,
    warnings,
    barcodeSource,
    barcodeCandidates: Array.isArray(observed.barcode_candidates) ? observed.barcode_candidates : [],
    barcodeWarning: String(observed.barcode_warning || "").trim(),
  }
}

export function confidencePercent(value) {
  if (value === null || value === undefined || value === "") return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return Math.max(0, Math.min(100, Math.round(number * 100)))
}

export const HAPTIC_PATTERNS = Object.freeze({
  pass: Object.freeze([40]),
  review: Object.freeze([50, 60, 50]),
  ambiguous: Object.freeze([50, 60, 50]),
  fail: Object.freeze([120, 80, 120]),
})

export function resolveHapticPattern(verdict) {
  if (!verdict) return null

  let key = ""
  if (typeof verdict === "object") {
    if (verdict.verdict && typeof verdict.verdict === "object") {
      verdict = verdict.verdict
    }
    const code = String(verdict.code || "").trim().toLowerCase()
    const severity = String(verdict.severity || "").trim().toLowerCase()
    const state = String(verdict.progress_state || "").trim().toLowerCase()
    key = code || severity || state
  } else if (typeof verdict === "string") {
    key = verdict.trim().toLowerCase()
  }

  if (!key) return null

  if (key === "pass" || key === "success" || key === "ok") {
    return HAPTIC_PATTERNS.pass
  }
  if (key === "fail" || key === "error" || key === "bad" || key === "danger") {
    return HAPTIC_PATTERNS.fail
  }
  if (key === "review" || key === "warning" || key === "warn" || key === "ambiguous") {
    return HAPTIC_PATTERNS.review
  }

  return HAPTIC_PATTERNS.review
}

export function triggerHapticFeedback(verdict, options = {}) {
  if (options?.enabled === false) return false
  const nav = options?.navigator !== undefined
    ? options.navigator
    : (typeof navigator !== "undefined" ? navigator : null)
  if (!nav || typeof nav.vibrate !== "function") return false

  const pattern = resolveHapticPattern(verdict)
  if (!pattern) return false

  try {
    const success = nav.vibrate(pattern)
    return Boolean(success !== false)
  } catch {
    return false
  }
}

