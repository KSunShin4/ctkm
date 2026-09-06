import { confidencePercent, perceptionSummary } from "./tag-audit-perception.js"

const boxStyle = {
  maxWidth: 720,
  margin: "12px auto -2px",
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid #fedf89",
  background: "#fffaeb",
  color: "#475467",
  font: "12px/1.45 Inter, ui-sans-serif, sans-serif",
}

export default function TagAuditPerceptionFeedback({ result, browserBarcode = "" }) {
  if (!result) return null
  const feedback = perceptionSummary(result, browserBarcode)
  const confidence = confidencePercent(feedback.confidence)
  const hasDetails = feedback.engine || confidence !== null || feedback.barcodeSource || feedback.warnings.length || feedback.barcodeWarning
  if (!hasDetails) return null

  const warning = feedback.warnings.length > 0
  return <div role="status" aria-live="polite" style={{
    ...boxStyle,
    borderColor: warning ? "#fedf89" : "#abefc6",
    background: warning ? "#fffaeb" : "#ecfdf3",
  }}>
    <div style={{display:"flex",justifyContent:"space-between",gap:10,alignItems:"center"}}>
      <strong style={{color:"#17202a"}}>Chất lượng nhận diện</strong>
      <strong style={{color: warning ? "#b54708" : "#067647"}}>{warning ? "Nên xem lại ảnh" : "Ảnh dùng được"}</strong>
    </div>
    <div style={{display:"flex",flexWrap:"wrap",gap:"4px 12px",marginTop:5}}>
      <span>OCR: <strong>{feedback.engine}</strong></span>
      {confidence !== null && <span>Độ tin cậy: <strong>{confidence}%</strong></span>}
      {feedback.barcodeSource && <span>Barcode: <strong>{feedback.barcodeSource}</strong></span>}
    </div>
    {feedback.warnings.map((item, index) => <div key={`${item.code}-${index}`} style={{marginTop:6,color:"#b54708"}}>⚠ {item.message}</div>)}
    {feedback.barcodeWarning && <div style={{marginTop:6}}>Barcode fallback: {feedback.barcodeWarning}</div>}
    {feedback.barcodeCandidates.length > 1 && <div style={{marginTop:6}}>Đọc được nhiều barcode: {feedback.barcodeCandidates.join(" · ")}. Hệ thống không tự chọn.</div>}
  </div>
}
