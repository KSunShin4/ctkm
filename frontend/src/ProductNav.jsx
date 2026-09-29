import React from "react"

export const PORTAL_MODULES=[
  {id:"overview",label:"Tổng quan",short:"Trang chủ",href:"/overview",icon:"⌂"},
  {id:"ctkm",label:"CTKM",short:"CTKM",href:"/?module=ctkm",icon:"✦"},
  {id:"shelf",label:"Kiểm kệ",short:"Kiểm kệ",href:"/scan-tem?mode=shelf",icon:"✓"},
  {id:"temr",label:"Tem R",short:"Tem R",href:"/?module=temr",icon:"◇"},
  {id:"inventory",label:"Kiểm tồn kho",short:"Kiểm tồn",href:"/?module=inventory",icon:"▣"},
  {id:"expiration",label:"Kiểm hạn dùng",short:"Hạn dùng",href:"/?module=expiration",icon:"◷"},
  {id:"schedule",label:"Xếp lịch",short:"Lịch",href:"/schedule",icon:"▦"},
  {id:"guide",label:"Hướng dẫn",short:"Hướng dẫn",href:"/guide",icon:"?"},
  {id:"settings",label:"Cài đặt",short:"Cài đặt",href:"/settings",icon:"⚙"},
]

const css=[
":root{--ops-blue:#1769ff;--ops-ink:#173052;--ops-line:#e4ebf5}",
"body{padding-left:88px}",
".portal-nav{position:fixed;inset:0 auto 0 0;width:88px;z-index:100;background:linear-gradient(180deg,#fff 0%,#f7fbff 72%,#f1f7ff 100%);border-right:1px solid var(--ops-line);display:flex;flex-direction:column;align-items:center;padding:14px 8px 16px;box-shadow:8px 0 28px rgba(31,79,140,.06)}",
".portal-nav-brand{width:68px;display:flex;flex-direction:column;align-items:center;gap:5px;color:var(--ops-ink);text-decoration:none;white-space:nowrap;margin-bottom:12px}",
".portal-brand-mark{width:44px;height:44px;border-radius:15px;background:linear-gradient(145deg,#e8f1ff,#fff);border:1px solid #d8e6ff;color:var(--ops-blue);display:grid;place-items:center;font-size:24px;font-weight:950;box-shadow:0 7px 18px rgba(23,105,255,.12)}",
".portal-brand-name{font-size:9px;font-weight:950;letter-spacing:-.02em}.portal-brand-name span{color:#61b846}",
".portal-nav-links{display:flex;flex-direction:column;gap:4px;width:100%;overflow-y:auto;scrollbar-width:none}.portal-nav-links::-webkit-scrollbar{display:none}",
".portal-nav-link{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:58px;padding:7px 4px;border-radius:14px;color:#5b6f8f;text-decoration:none;font-size:9px;font-weight:800;text-align:center;line-height:1.15}",
".portal-nav-link:hover{background:#f0f6ff;color:#1d4f91}.portal-nav-link.active{background:linear-gradient(145deg,#e8f2ff,#f4f8ff);color:var(--ops-blue);box-shadow:inset 3px 0 0 var(--ops-blue)}",
".portal-nav-icon{font-size:20px;line-height:1}.portal-nav-spacer{flex:1}",
".portal-nav-cute{width:60px;padding:8px 5px;border-radius:15px;background:linear-gradient(145deg,#eef8ff,#fff7fb);border:1px solid #e6edf8;text-align:center;color:#7990ad;font-size:8px;line-height:1.3}.portal-nav-cute b{display:block;font-size:20px;margin-bottom:3px}",
".portal-mobile-nav{display:none}",
"@media(max-width:760px){body{padding-left:0;padding-bottom:72px}.portal-nav{position:sticky;top:0;inset:auto;width:100%;height:54px;flex-direction:row;padding:7px 12px;border-right:0;border-bottom:1px solid var(--ops-line);box-shadow:0 4px 18px rgba(31,79,140,.06)}.portal-nav-brand{width:auto;flex-direction:row;margin:0}.portal-brand-mark{width:35px;height:35px;border-radius:12px;font-size:19px}.portal-brand-name{font-size:13px}.portal-nav-links,.portal-nav-cute{display:none}.portal-mobile-nav{position:fixed;display:grid;grid-template-columns:repeat(5,1fr);left:0;right:0;bottom:0;z-index:110;background:rgba(255,255,255,.98);border-top:1px solid var(--ops-line);padding:6px 4px calc(6px + env(safe-area-inset-bottom));box-shadow:0 -7px 24px rgba(31,79,140,.10);backdrop-filter:blur(12px)}.portal-mobile-link{min-width:0;display:flex;flex-direction:column;align-items:center;gap:3px;padding:4px 1px;color:#7486a2;text-decoration:none;font-size:8px;font-weight:850;white-space:nowrap}.portal-mobile-link .portal-nav-icon{font-size:18px}.portal-mobile-link.active{color:var(--ops-blue)}}"
].join("")

export function currentPortalModule(pathname=window.location.pathname,search=window.location.search){
  const p=String(pathname||"/")
  const q=new URLSearchParams(search||"")
  if(p.startsWith("/overview"))return"overview"
  if(p.startsWith("/scan-tem")&&q.get("mode")==="shelf")return"shelf"
  if(p.startsWith("/schedule"))return"schedule"
  if(p.startsWith("/guide"))return"guide"
  if(p.startsWith("/settings"))return"settings"
  if(p==="/"){
    const module=q.get("module")
    if(module==="temr")return"temr"
    if(module==="inventory")return"inventory"
    if(module==="expiration")return"expiration"
    return"ctkm"
  }
  return"ctkm"
}

export default function ProductNav({current}){
  const active=current||currentPortalModule()
  const mobile=PORTAL_MODULES.filter(x=>["overview","ctkm","shelf","temr","expiration"].includes(x.id))
  return <>
    <style>{css}</style>
    <nav className="portal-nav" aria-label="Điều hướng vận hành">
      <a className="portal-nav-brand" href="/overview"><span className="portal-brand-mark">✚</span><span className="portal-brand-name">Pharma<span>city</span></span></a>
      <div className="portal-nav-links">{PORTAL_MODULES.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-nav-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.label}</span></a>)}</div>
      <div className="portal-nav-spacer"/>
      <div className="portal-nav-cute" aria-hidden="true"><b>💊</b>Hôm nay<br/>cố lên nhé ✨</div>
    </nav>
    <nav className="portal-mobile-nav" aria-label="Điều hướng chính trên điện thoại">{mobile.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-mobile-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.short}</span></a>)}</nav>
  </>
}
