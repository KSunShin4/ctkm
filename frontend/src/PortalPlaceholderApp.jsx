import React from "react"
import ProductNav from "./ProductNav.jsx"

const css=`
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#17202a;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.portal-page{min-height:calc(100vh - 44px);padding:34px 18px}
.portal-card{max-width:860px;margin:0 auto;background:#fff;border:1px solid #e4e7ec;border-radius:18px;padding:28px;box-shadow:0 4px 20px rgba(16,24,40,.05)}
.portal-kicker{font-size:11px;font-weight:850;color:#175cd3;text-transform:uppercase;letter-spacing:.08em}
.portal-card h1{margin:8px 0 8px;font-size:28px;letter-spacing:-.7px}
.portal-card p{margin:0;color:#667085;font-size:13px;line-height:1.7}
.portal-status{margin-top:20px;border:1px solid #b2ddff;background:#f5fbff;border-radius:12px;padding:12px 14px;color:#175cd3;font-size:12px;font-weight:700}
@media(max-width:640px){.portal-page{padding:16px 10px}.portal-card{padding:20px 16px;border-radius:14px}.portal-card h1{font-size:23px}}
`

export default function PortalPlaceholderApp({module}){
  const guide=module==="guide"
  return <><ProductNav current={module}/><main className="portal-page"><style>{css}</style><section className="portal-card">
    <div className="portal-kicker">{guide?"Module hướng dẫn":"Module trợ lý"}</div>
    <h1>{guide?"Hướng dẫn sử dụng":"Trợ lý vận hành"}</h1>
    <p>{guide
      ?"Khung module đã sẵn sàng. Phần tiếp theo sẽ đưa quick start, FAQ và hướng dẫn theo ngữ cảnh vào đây."
      :"Khung module đã sẵn sàng. Phần trợ lý anime và gợi ý theo từng nghiệp vụ sẽ được tách thành checkpoint riêng."}</p>
    <div className="portal-status">✓ Module độc lập — có thể phát triển, thay đổi hoặc gỡ mà không ảnh hưởng CTKM và Xếp lịch.</div>
  </section></main></>
}
