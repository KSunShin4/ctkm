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
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return Math.max(0, Math.min(100, Math.round(number * 100)))
}
