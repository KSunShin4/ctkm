export function normalizeBarcodeValue(rawValue) {
  const digits = String(rawValue ?? "").replace(/\D/g, "")
  return /^\d{8,14}$/.test(digits) ? digits : ""
}

export function chooseBarcodeCandidate(values) {
  if (!Array.isArray(values)) return ""
  for (const item of values) {
    const candidate = normalizeBarcodeValue(item?.rawValue)
    if (candidate) return candidate
  }
  return ""
}
