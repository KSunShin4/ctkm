import { confidencePercent, perceptionSummary } from "./tag-audit-perception.js"

export default function TagAuditPerceptionFeedback({ result, browserBarcode = "" }) {
  if (!result) return null
  const feedback = perceptionSummary(result, browserBarcode)
  const confidence = confidencePercent(feedback.confidence)
  const hasDetails = feedback.engine || confidence !== null || feedback.barcodeSource || feedback.warnings.length || feedback.barcodeWarning
  if (!hasDetails) return null

  return <div className="perception-box">
    <div className="perception-head">
      <strong>Chất lượng nhận diện</strong>
      <span>{feedback.warnings.length ? "Nên xem lại ảnh" : "Ảnh dùng được"}</span>
    </div>
    <div className="perception-meta">
      <span>OCR: <strong>{feedback.engine}</strong></span>
      {confidence !== null && <span>Độ tin cậy: <strong>{confidence}%</strong></span>}
      {feedback.barcodeSource && <span>Barcode: <strong>{feedback.barcodeSource}</strong></span>}
    </div>
    {feedback.warnings.length > 0 && <div className="perception-warnings">
      {feedback.warnings.map((warning, index) => <div className="perception-warning" key={`${warning.code}-${index}`}>⚠ {warning.message}</div>)}
    </div>}
    {feedback.barcodeWarning && <div className="perception-note">Barcode fallback: {feedback.barcodeWarning}</div>}
    {feedback.barcodeCandidates.length > 1 && <div className="perception-note">Đọc được nhiều barcode: {feedback.barcodeCandidates.join(" · ")}. Hệ thống không tự chọn.</div>}
  </div>
}
