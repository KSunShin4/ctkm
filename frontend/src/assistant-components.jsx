import React from "react"
import {useUiPreferences} from "./ui-preferences.js"

export const MASCOT_STATES={
  idle:{label:"Sẵn sàng",face:"•ᴗ•",mark:"✦"},
  thinking:{label:"Đang suy nghĩ",face:"•﹏•",mark:"…"},
  success:{label:"Hoàn tất",face:"ᵔᴗᵔ",mark:"✓"},
  warning:{label:"Cần chú ý",face:"•△•",mark:"!"},
  guide:{label:"Hướng dẫn",face:"•◡•",mark:"?"},
}
export const assistantComponentCss=`
.mascot{display:inline-flex;align-items:center;gap:9px}.mascot-avatar{position:relative;width:54px;height:54px;border-radius:18px 18px 22px 22px;background:linear-gradient(145deg,#fff,#eef4ff);border:1px solid #c7d7fe;display:grid;place-items:center;box-shadow:0 5px 14px rgba(16,24,40,.08)}.mascot-hair{position:absolute;left:7px;right:7px;top:6px;height:16px;border-radius:13px 13px 7px 7px;background:#263b55}.mascot-face{position:relative;margin-top:8px;color:#344054;font-size:12px;font-weight:900;letter-spacing:1px}.mascot-mark{position:absolute;right:-6px;top:-7px;width:21px;height:21px;border-radius:50%;display:grid;place-items:center;background:#087f5b;color:#fff;border:2px solid #fff;font-size:9px;font-weight:900}.mascot-label{font-size:10px;font-weight:800;color:#667085}
.assistant-card{display:grid;grid-template-columns:auto 1fr;gap:13px;padding:16px;border:1px solid #d0d5dd;border-radius:16px;background:#fff;box-shadow:0 3px 12px rgba(16,24,40,.05)}.assistant-card h3{margin:0 0 4px;font-size:14px}.assistant-card p{margin:0;color:#667085;font-size:11px;line-height:1.55}.assistant-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}.assistant-actions button,.assistant-actions a{border:1px solid #d0d5dd;border-radius:9px;background:#fff;padding:7px 10px;color:#344054;text-decoration:none;font:800 10px inherit;cursor:pointer}.assistant-actions .primary{background:#087f5b;border-color:#087f5b;color:#fff}
.guide-bubble{position:relative;padding:12px 14px;border:1px solid #b2ddff;border-radius:14px;background:#eff8ff;color:#1849a9;font-size:11px;line-height:1.55}.guide-bubble:before{content:"";position:absolute;left:18px;top:-6px;width:10px;height:10px;background:#eff8ff;border-left:1px solid #b2ddff;border-top:1px solid #b2ddff;transform:rotate(45deg)}
.assistant-empty{padding:28px 18px;border:1px dashed #cfd4dc;border-radius:16px;text-align:center;background:#fafbfc}.assistant-empty .mascot{justify-content:center}.assistant-empty h3{margin:12px 0 4px;font-size:14px}.assistant-empty p{margin:0 auto;max-width:460px;color:#667085;font-size:11px;line-height:1.55}
@media(max-width:760px){.mascot-avatar{width:46px;height:46px;border-radius:15px}.assistant-card{grid-template-columns:1fr;padding:14px}.assistant-card>.mascot{align-items:center}.assistant-actions>*{flex:1;text-align:center}.assistant-empty{padding:20px 12px}}
`
export function Mascot({state="idle",showLabel=false}){const prefs=useUiPreferences();if(!prefs.assistant)return null;const x=MASCOT_STATES[state]||MASCOT_STATES.idle;return <span className="mascot" data-state={state}><span className="mascot-avatar" aria-hidden="true"><span className="mascot-hair"/><span className="mascot-face">{x.face}</span><span className="mascot-mark">{x.mark}</span></span>{showLabel&&<span className="mascot-label">{x.label}</span>}</span>}
export function AssistantCard({state="idle",title,children,actions=[]}){const prefs=useUiPreferences();if(!prefs.assistant)return null;return <section className="assistant-card"><Mascot state={state}/><div><h3>{title}</h3><p>{children}</p>{actions.length>0&&<div className="assistant-actions">{actions.map((a,i)=>a.href?<a key={i} className={a.primary?"primary":""} href={a.href}>{a.label}</a>:<button key={i} type="button" className={a.primary?"primary":""} onClick={a.onClick}>{a.label}</button>)}</div>}</div></section>}
export function GuideBubble({children}){const prefs=useUiPreferences();if(!prefs.assistant)return null;return <div className="guide-bubble">{children}</div>}
export function EmptyState({title="Chưa có dữ liệu",children,state="guide"}){const prefs=useUiPreferences();if(!prefs.assistant)return null;return <section className="assistant-empty"><Mascot state={state}/><h3>{title}</h3><p>{children}</p></section>}
