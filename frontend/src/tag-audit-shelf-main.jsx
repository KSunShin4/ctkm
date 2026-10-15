import React from "react"
import ReactDOM from "react-dom/client"
import TagAuditShelfCheck from "./TagAuditShelfCheck.jsx"

function ShelfRoute() {
  return <>
    <TagAuditShelfCheck />
    <a
      href="/"
      aria-label="Thoát soát tem kệ và về các chức năng chính"
      style={{
        position:"fixed",
        left:14,
        bottom:14,
        zIndex:100,
        padding:"11px 14px",
        borderRadius:12,
        background:"#17202a",
        color:"#fff",
        textDecoration:"none",
        boxShadow:"0 8px 24px rgba(16,24,40,.22)",
        font:"800 12px/1.2 Inter,ui-sans-serif,sans-serif",
      }}
    >
      ← Thoát · Chức năng khác
    </a>
  </>
}

ReactDOM.createRoot(document.getElementById("root")).render(<ShelfRoute />)
