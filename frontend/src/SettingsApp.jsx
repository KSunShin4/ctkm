import React,{useEffect,useState} from "react"
import ProductNav from "./ProductNav.jsx"
import {HelpTip,helpTipCss} from "./help-foundation.jsx"
import {AssistantCard,Mascot,assistantComponentCss} from "./assistant-components.jsx"
import {DEFAULT_UI_PREFERENCES,readUiPreferences,writeUiPreferences} from "./ui-preferences.js"

// Preferences persist through the shared localStorage contract in ui-preferences.js.
const css=`
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f6f9ff 0%,#f5f8ff 56%,#fff9fc 100%);color:#173052;font-family:Inter,ui-sans-serif,sans-serif}
.settings{max-width:1020px;margin:0 auto;padding:22px 22px 88px}
.settings-hero{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;padding:19px 21px;border:1px solid #dfe8f4;border-radius:22px;background:radial-gradient(circle at 94% 8%,rgba(255,203,228,.38),transparent 28%),linear-gradient(135deg,#fff,#f8fbff 64%,#fff8fb);box-shadow:0 14px 38px rgba(44,75,118,.07)}
.settings-hero-copy{display:flex;align-items:center;gap:13px}.settings-hero .mascot-avatar{width:56px;height:56px;border-radius:19px}.settings-kicker{font-size:8px;font-weight:950;color:#7b5bd6;text-transform:uppercase;letter-spacing:.12em}.settings h1{margin:3px 0 4px;font-size:24px;letter-spacing:-.45px}.settings-sub{margin:0;max-width:680px;color:#7588a0;font-size:9.5px;line-height:1.55}.settings-local{padding:7px 9px;border:1px solid #e1e8f2;border-radius:999px;background:rgba(255,255,255,.86);color:#7689a1;font-size:8px;font-weight:900;white-space:nowrap}
.settings-card{margin-top:11px;background:#fff;border:1px solid #e2e9f3;border-radius:18px;padding:15px;box-shadow:0 9px 26px rgba(42,75,118,.04)}.settings-card-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:5px}.settings-card h2{font-size:13px;margin:0;color:#2e455f}.settings-card-head span{font-size:8px;color:#8a9ab0}
.settings-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:9px}.setting-row{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:12px;border:1px solid #e7edf5;border-radius:13px;background:linear-gradient(145deg,#fff,#fbfdff)}.setting-title{display:flex;align-items:center;gap:5px;font-size:9.5px;font-weight:900;color:#38506d}.setting-copy{margin-top:4px;color:#7e90a7;font-size:8.5px;line-height:1.5}
.toggle{border:1px solid #d3ddea;border-radius:999px;background:#eef2f7;width:44px;height:25px;padding:2px;cursor:pointer;transition:.15s}.toggle span{display:block;width:19px;height:19px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(16,24,40,.18);transition:.15s}.toggle.on{background:linear-gradient(135deg,#1769ff,#6a77ec);border-color:#5b78dc}.toggle.on span{transform:translateX(17px)}
.settings-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:11px}.settings-note{color:#8b9bb0;font-size:8px}.reset{border:1px solid #d8e2ee;border-radius:10px;background:#fff;padding:8px 11px;font:900 8.5px inherit;color:#5d728d;cursor:pointer}.reset:hover{background:#f7faff;border-color:#bfd1ea}
.settings-assistant{margin-top:10px}
@media(max-width:760px){.settings{padding:12px 10px 86px}.settings-hero{grid-template-columns:1fr;padding:14px;border-radius:17px}.settings-hero-copy{align-items:flex-start}.settings-hero .mascot-avatar{width:46px;height:46px;border-radius:15px}.settings h1{font-size:20px}.settings-local{justify-self:start}.settings-grid{grid-template-columns:1fr}.settings-actions{align-items:flex-start;flex-direction:column-reverse}.reset{width:100%}}
`

export default function SettingsApp(){
  const [prefs,setPrefs]=useState(readUiPreferences)
  useEffect(()=>{writeUiPreferences(prefs)},[prefs])
  const toggle=k=>setPrefs(p=>({...p,[k]:!p[k]}))
  return <><ProductNav current="settings"/><main className="settings"><style>{css}</style><style>{helpTipCss}</style><style>{assistantComponentCss}</style>
    <section className="settings-hero">
      <div className="settings-hero-copy"><Mascot state="guide"/><div><div className="settings-kicker">Cài đặt</div><h1>Trải nghiệm giao diện</h1><p className="settings-sub">Các tùy chọn ở đây chỉ lưu trên trình duyệt này. Không thay đổi rule CTKM, mapping, solver hay dữ liệu nguồn.</p></div></div>
      <span className="settings-local">Thiết bị này בלבד · localStorage</span>
    </section>
    <section className="settings-card">
      <div className="settings-card-head"><h2>Hiển thị</h2><span>3 tùy chọn an toàn</span></div>
      <div className="settings-grid">
        <div className="setting-row"><div><div className="setting-title">Giao diện gọn <HelpTip title="Giao diện gọn" text="Lưu lựa chọn hiển thị để các màn hình có thể dùng khi hỗ trợ compact mode; không đổi dữ liệu."/></div><div className="setting-copy">Ưu tiên mật độ thông tin cao hơn trên màn hình nhỏ.</div></div><button className={`toggle ${prefs.compact?"on":""}`} aria-pressed={prefs.compact} onClick={()=>toggle("compact")}><span/></button></div>
        <div className="setting-row"><div><div className="setting-title">Hiện trợ lý</div><div className="setting-copy">Cho phép các màn hình dùng mascot và thẻ giải thích khi có hỗ trợ.</div></div><button className={`toggle ${prefs.assistant?"on":""}`} aria-pressed={prefs.assistant} onClick={()=>toggle("assistant")}><span/></button></div>
        <div className="setting-row"><div><div className="setting-title">Hiện trợ giúp ngữ cảnh</div><div className="setting-copy">Cho phép hiển thị nút ? tại các khái niệm cần giải thích.</div></div><button className={`toggle ${prefs.help?"on":""}`} aria-pressed={prefs.help} onClick={()=>toggle("help")}><span/></button></div>
      </div>
      <div className="settings-actions"><div className="settings-note">Không có setting business rule trong checkpoint này.</div><button className="reset" type="button" onClick={()=>setPrefs(DEFAULT_UI_PREFERENCES)}>Khôi phục mặc định</button></div>
    </section>
    <div className="settings-assistant"><AssistantCard state="guide" title="Cài đặt an toàn">Business rules vẫn thuộc backend/workflow tương ứng. Trang này chỉ quản lý preference giao diện cục bộ.</AssistantCard></div>
  </main></>
}
