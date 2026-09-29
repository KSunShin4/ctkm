import React,{useState} from "react"

export const PORTAL_MODULES=[
  {id:"overview",label:"Tổng quan",short:"Trang chủ",href:"/overview",icon:"⌂"},
  {id:"ctkm",label:"CTKM",short:"CTKM",href:"/?module=ctkm",icon:"✦"},
  {id:"shelf",label:"Kiểm kệ",short:"Kiểm kệ",href:"/scan-tem?mode=shelf",icon:"✓"},
  {id:"temr",label:"Tem R",short:"Tem R",href:"/?module=temr",icon:"◇"},
  {id:"inventory",label:"Kiểm tồn kho",short:"Kiểm tồn",href:"/?module=inventory",icon:"▣"},
  {id:"expiration",label:"Kiểm hạn dùng",short:"Hạn dùng",href:"/?module=expiration",icon:"◷"},
]
export const PORTAL_MORE=[
  {id:"schedule",label:"Xếp lịch",href:"/schedule",icon:"▦"},
  {id:"guide",label:"Hướng dẫn",href:"/guide",icon:"?"},
  {id:"settings",label:"Cài đặt",href:"/settings",icon:"⚙"},
]

const css=[
":root{--ops-blue:#1769ff;--ops-ink:#173052;--ops-line:#e4ebf5}",
"body{padding-left:88px}",
".portal-nav{position:fixed;inset:0 auto 0 0;width:88px;z-index:100;background:linear-gradient(180deg,#fff 0%,#f7fbff 72%,#f1f7ff 100%);border-right:1px solid var(--ops-line);display:flex;flex-direction:column;align-items:center;padding:14px 8px 16px;box-shadow:8px 0 28px rgba(31,79,140,.06)}",
".portal-nav-brand{width:68px;display:flex;flex-direction:column;align-items:center;gap:5px;color:var(--ops-ink);text-decoration:none;white-space:nowrap;margin-bottom:12px}",
".portal-brand-mark{width:44px;height:44px;border-radius:15px;background:linear-gradient(145deg,#e8f1ff,#fff);border:1px solid #d8e6ff;color:var(--ops-blue);display:grid;place-items:center;font-size:24px;font-weight:950;box-shadow:0 7px 18px rgba(23,105,255,.12)}",
".portal-brand-name{font-size:9px;font-weight:950;letter-spacing:-.02em}.portal-brand-name span{color:#61b846}",
".portal-nav-links{display:flex;flex-direction:column;gap:4px;width:100%;overflow-y:auto;scrollbar-width:none}.portal-nav-links::-webkit-scrollbar{display:none}",
".portal-nav-link,.portal-more-button{position:relative;border:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:58px;width:100%;padding:7px 4px;border-radius:14px;color:#5b6f8f;text-decoration:none;font:800 9px/1.15 Inter,ui-sans-serif,system-ui;background:transparent;text-align:center;cursor:pointer}",
".portal-nav-link:hover,.portal-more-button:hover{background:#f0f6ff;color:#1d4f91}.portal-nav-link.active,.portal-more-button.active{background:linear-gradient(145deg,#e8f2ff,#f4f8ff);color:var(--ops-blue);box-shadow:inset 3px 0 0 var(--ops-blue)}",
".portal-nav-icon{font-size:20px;line-height:1}.portal-nav-spacer{flex:1}",
".portal-more-wrap{position:relative;width:100%}.portal-more-menu{position:absolute;left:76px;bottom:0;width:185px;background:#fff;border:1px solid #e0e8f3;border-radius:15px;padding:7px;box-shadow:0 16px 42px rgba(37,74,124,.16)}.portal-more-item{display:flex;align-items:center;gap:9px;padding:10px;border-radius:10px;color:#526b8c;text-decoration:none;font-size:10px;font-weight:800}.portal-more-item:hover{background:#f1f6ff;color:#1769ff}.portal-more-item span{font-size:17px}",
".portal-mobile-nav{display:none}.portal-mobile-more{display:none}",
"@media(max-width:760px){body{padding-left:0;padding-bottom:72px}.portal-nav{position:sticky;top:0;inset:auto;width:100%;height:54px;flex-direction:row;padding:7px 12px;border-right:0;border-bottom:1px solid var(--ops-line);box-shadow:0 4px 18px rgba(31,79,140,.06)}.portal-nav-brand{width:auto;flex-direction:row;margin:0}.portal-brand-mark{width:35px;height:35px;border-radius:12px;font-size:19px}.portal-brand-name{font-size:13px}.portal-nav-links,.portal-more-wrap{display:none}.portal-mobile-nav{position:fixed;display:grid;grid-template-columns:repeat(5,1fr);left:0;right:0;bottom:0;z-index:110;background:rgba(255,255,255,.98);border-top:1px solid var(--ops-line);padding:6px 4px calc(6px + env(safe-area-inset-bottom));box-shadow:0 -7px 24px rgba(31,79,140,.10);backdrop-filter:blur(12px)}.portal-mobile-link{border:0;background:transparent;min-width:0;display:flex;flex-direction:column;align-items:center;gap:3px;padding:4px 1px;color:#7486a2;text-decoration:none;font:850 8px Inter,ui-sans-serif,system-ui;white-space:nowrap}.portal-mobile-link .portal-nav-icon{font-size:18px}.portal-mobile-link.active{color:var(--ops-blue)}.portal-mobile-more{display:block;position:fixed;z-index:109;left:10px;right:10px;bottom:68px;background:rgba(255,255,255,.99);border:1px solid #dfe8f4;border-radius:18px;padding:8px;box-shadow:0 -10px 36px rgba(37,74,124,.16)}.portal-mobile-more-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.portal-mobile-more a{display:flex;align-items:center;gap:10px;padding:12px;border-radius:12px;background:#f8fbff;color:#4e688b;text-decoration:none;font-size:10px;font-weight:850}.portal-mobile-more a span{font-size:19px}.portal-mobile-more .inventory{background:#fff8ef}.portal-mobile-more .expiration{background:#eefbfc}}"
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
  const [moreOpen,setMoreOpen]=useState(false)
  const moreActive=["inventory","expiration","schedule","guide","settings"].includes(active)
  const primary=PORTAL_MODULES.filter(x=>["overview","ctkm","shelf","temr"].includes(x.id))
  return <>
    <style>{css}</style>
    <nav className="portal-nav" aria-label="Điều hướng vận hành">
      <a className="portal-nav-brand" href="/overview"><span className="portal-brand-mark">✚</span><span className="portal-brand-name">Pharma<span>city</span></span></a>
      <div className="portal-nav-links">{PORTAL_MODULES.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-nav-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.label}</span></a>)}</div>
      <div className="portal-nav-spacer"/>
      <div className="portal-more-wrap">
        <button className={"portal-more-button "+(moreActive?"active":"")} onClick={()=>setMoreOpen(v=>!v)} aria-expanded={moreOpen}><span className="portal-nav-icon">•••</span><span>Thêm</span></button>
        {moreOpen&&<div className="portal-more-menu">{PORTAL_MORE.map(x=><a key={x.id} className="portal-more-item" href={x.href}><span>{x.icon}</span>{x.label}</a>)}</div>}
      </div>
    </nav>
    {moreOpen&&<div className="portal-mobile-more"><div className="portal-mobile-more-grid">
      <a className="inventory" href="/?module=inventory"><span>▣</span>Kiểm tồn kho</a>
      <a className="expiration" href="/?module=expiration"><span>◷</span>Kiểm hạn dùng</a>
      {PORTAL_MORE.map(x=><a key={x.id} href={x.href}><span>{x.icon}</span>{x.label}</a>)}
    </div></div>}
    <nav className="portal-mobile-nav" aria-label="Điều hướng chính trên điện thoại">
      {primary.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-mobile-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.short}</span></a>)}
      <button className={"portal-mobile-link "+(moreActive?"active":"")} onClick={()=>setMoreOpen(v=>!v)} aria-expanded={moreOpen}><span className="portal-nav-icon">•••</span><span>Thêm</span></button>
    </nav>
  </>
}
