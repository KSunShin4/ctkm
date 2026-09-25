import React from "react"

export const PORTAL_MODULES = [
  {id:"ops", label:"CTKM / Tem", href:"/"},
  {id:"schedule", label:"Xếp lịch", href:"/schedule"},
  {id:"guide", label:"Hướng dẫn", href:"/guide"},
  {id:"assistant", label:"Trợ lý", href:"/assistant"},
]

const css=`
.portal-nav{height:44px;display:flex;align-items:center;gap:12px;padding:0 18px;background:#102a43;color:#fff;position:sticky;top:0;z-index:80;border-bottom:1px solid rgba(255,255,255,.12)}
.portal-nav-brand{font-size:13px;font-weight:900;letter-spacing:-.2px;white-space:nowrap}
.portal-nav-brand span{color:#6ee7b7}
.portal-nav-links{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}
.portal-nav-links::-webkit-scrollbar{display:none}
.portal-nav-link{display:inline-flex;align-items:center;min-height:30px;padding:6px 10px;border-radius:8px;color:#dbeafe;text-decoration:none;font-size:11px;font-weight:750;white-space:nowrap}
.portal-nav-link:hover{background:rgba(255,255,255,.09);color:#fff}
.portal-nav-link.active{background:#fff;color:#102a43}
.portal-nav-spacer{flex:1}
.portal-nav-note{font-size:10px;color:#a9c2d9;white-space:nowrap}
@media(max-width:700px){.portal-nav{height:42px;padding:0 10px;gap:8px}.portal-nav-brand{font-size:12px}.portal-nav-note{display:none}.portal-nav-link{padding:6px 9px;font-size:10px}}
`

export function currentPortalModule(pathname=window.location.pathname){
  const path=String(pathname||"/")
  if(path.startsWith("/schedule"))return "schedule"
  if(path.startsWith("/guide"))return "guide"
  if(path.startsWith("/assistant"))return "assistant"
  return "ops"
}

export default function ProductNav({current}){
  const active=current||currentPortalModule()
  return <><style>{css}</style><nav className="portal-nav" aria-label="Điều hướng module">
    <div className="portal-nav-brand">Pharma<span>Ops</span></div>
    <div className="portal-nav-links">
      {PORTAL_MODULES.map(item=><a key={item.id} className={`portal-nav-link ${active===item.id?"active":""}`} href={item.href}>{item.label}</a>)}
    </div>
    <div className="portal-nav-spacer"/>
    <div className="portal-nav-note">Công cụ vận hành cửa hàng</div>
  </nav></>
}
