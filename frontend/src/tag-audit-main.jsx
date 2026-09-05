import React from "react"
import ReactDOM from "react-dom/client"
import TagAudit from "./TagAudit.jsx"

function TagAuditEntry() {
  return <>
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
