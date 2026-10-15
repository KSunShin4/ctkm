import React,{useState} from "react"

export const PORTAL_MODULES=[
  {id:"ctkm",label:"CTKM",short:"CTKM",href:"/?module=ctkm",icon:"✦"},
  {id:"shelf",label:"Soát tem kệ",short:"Soát tem",href:"/scan-tem?mode=shelf",icon:"✓"},
  {id:"temr",label:"Tem R",short:"Tem R",href:"/?module=temr",icon:"◇"},
  {id:"inventory",label:"Kiểm tồn kho",short:"Kiểm tồn",href:"/?module=inventory",icon:"▣"},
  {id:"expiration",label:"Kiểm hạn dùng",short:"Hạn dùng",href:"/?module=expiration",icon:"◷"},
  {id:"schedule",label:"Xếp lịch",short:"Lịch",href:"/schedule",icon:"▦"},
  {id:"guide",label:"Hướng dẫn",short:"Hướng dẫn",href:"/guide",icon:"?"},
]

const css=[
":root{--ops-blue:#1769ff;--ops-ink:#173052;--ops-line:#e4ebf5}",
"body{padding-left:88px}",
".portal-nav{position:fixed;inset:0 auto 0 0;width:88px;z-index:100;background:linear-gradient(180deg,#fff 0%,#f7fbff 72%,#f1f7ff 100%);border-right:1px solid var(--ops-line);display:flex;flex-direction:column;align-items:center;padding:14px 8px 16px;box-shadow:8px 0 28px rgba(31,79,140,.06)}",
".portal-nav-brand{width:68px;display:flex;flex-direction:column;align-items:center;gap:5px;color:var(--ops-ink);text-decoration:none;white-space:nowrap;margin-bottom:12px}",
".portal-brand-mark{width:44px;height:44px;border-radius:15px;background:linear-gradient(145deg,#e8f1ff,#fff);border:1px solid #d8e6ff;color:var(--ops-blue);display:grid;place-items:center;font-size:24px;font-weight:950;box-shadow:0 7px 18px rgba(23,105,255,.12)}",
".portal-brand-name{font-size:9px;font-weight:950;letter-spacing:-.02em}.portal-brand-name span{color:var(--ops-blue)}",
".portal-nav-links{display:flex;flex-direction:column;gap:4px;width:100%;overflow-y:auto;scrollbar-width:none}.portal-nav-links::-webkit-scrollbar{display:none}",
".portal-nav-link{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:58px;padding:7px 4px;border-radius:14px;color:#5b6f8f;text-decoration:none;font-size:9px;font-weight:800;text-align:center;line-height:1.15}",
".portal-nav-link:hover{background:#f0f6ff;color:#1d4f91}.portal-nav-link.active{background:linear-gradient(145deg,#e8f2ff,#f4f8ff);color:var(--ops-blue);box-shadow:inset 3px 0 0 var(--ops-blue)}",
".portal-nav-icon{font-size:20px;line-height:1}.portal-nav-spacer{flex:1}",
".portal-nav-cute{width:60px;padding:8px 5px;border-radius:15px;background:linear-gradient(145deg,#eef8ff,#fff7fb);border:1px solid #e6edf8;text-align:center;color:#7990ad;font-size:8px;line-height:1.3}.portal-nav-cute b{display:block;font-size:20px;margin-bottom:3px}",
".portal-mobile-nav{display:none}.portal-mobile-more-layer{display:none}",
"@media(max-width:760px){body{padding-left:0;padding-bottom:72px}.portal-nav{position:sticky;top:0;inset:auto;width:100%;height:54px;flex-direction:row;padding:7px 12px;border-right:0;border-bottom:1px solid var(--ops-line);box-shadow:0 4px 18px rgba(31,79,140,.06)}.portal-nav-brand{width:auto;flex-direction:row;margin:0}.portal-brand-mark{width:35px;height:35px;border-radius:12px;font-size:19px}.portal-brand-name{font-size:13px}.portal-nav-links,.portal-nav-cute{display:none}.portal-mobile-nav{position:fixed;display:grid;grid-template-columns:repeat(5,1fr);left:0;right:0;bottom:0;z-index:110;background:rgba(255,255,255,.98);border-top:1px solid var(--ops-line);padding:6px 4px calc(6px + env(safe-area-inset-bottom));box-shadow:0 -7px 24px rgba(31,79,140,.10);backdrop-filter:blur(12px)}.portal-mobile-link{min-width:0;border:0;background:transparent;display:flex;flex-direction:column;align-items:center;gap:3px;padding:4px 1px;color:#7486a2;text-decoration:none;font:850 8px Inter,ui-sans-serif,system-ui;white-space:nowrap}.portal-mobile-link .portal-nav-icon{font-size:18px}.portal-mobile-link.active{color:var(--ops-blue)}.portal-mobile-more-layer{display:block;position:fixed;inset:0;z-index:105;background:rgba(26,43,68,.20);backdrop-filter:blur(2px)}.portal-mobile-more-sheet{position:absolute;left:10px;right:10px;bottom:70px;padding:12px;border:1px solid #e1e8f2;border-radius:20px;background:linear-gradient(145deg,#fff,#f7fbff 65%,#fff8fb);box-shadow:0 20px 46px rgba(31,57,94,.18)}.portal-mobile-more-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:2px 2px 9px}.portal-mobile-more-head strong{font-size:12px;color:#29425f}.portal-mobile-more-head button{border:0;background:#eef3f8;border-radius:50%;width:28px;height:28px;color:#667b99;font-size:17px}.portal-mobile-more-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.portal-mobile-more-item{display:flex;align-items:center;gap:9px;padding:11px;border:1px solid #e6edf6;border-radius:13px;background:#fff;color:#49617f;text-decoration:none;font-size:10px;font-weight:850}.portal-mobile-more-item .portal-nav-icon{width:30px;height:30px;border-radius:9px;background:#f1f5fb;display:grid;place-items:center;font-size:17px}.portal-mobile-more-item.active{border-color:#bfd4ff;background:#eef4ff;color:#1769ff}}"
].join("")

export function currentPortalModule(pathname=window.location.pathname,search=window.location.search){
  const p=String(pathname||"/")
  const q=new URLSearchParams(search||"")
  if(p.startsWith("/scan-tem")&&q.get("mode")==="shelf")return"shelf"
  if(p.startsWith("/schedule"))return"schedule"
  if(p.startsWith("/guide"))return"guide"
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
  const mobilePrimary=PORTAL_MODULES.filter(x=>["ctkm","shelf","temr","inventory"].includes(x.id))
  const mobileMore=PORTAL_MODULES.filter(x=>["inventory","expiration","schedule","guide"].includes(x.id))
  const moreActive=mobileMore.some(x=>x.id===active)
  return <>
    <style>{css}</style>
    <nav className="portal-nav" aria-label="Điều hướng vận hành">
      <a className="portal-nav-brand" href="/?module=ctkm"><span className="portal-brand-mark">⚡</span><span className="portal-brand-name">Store<span>Ops</span></span></a>
      <div className="portal-nav-links">{PORTAL_MODULES.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-nav-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.label}</span></a>)}</div>
      <div className="portal-nav-spacer"/>
      <div className="portal-nav-cute" aria-hidden="true"><b>✨</b>Hôm nay<br/>cố lên nhé ✨</div>
    </nav>
    {moreOpen&&<div className="portal-mobile-more-layer" onClick={()=>setMoreOpen(false)} role="presentation">
      <section className="portal-mobile-more-sheet" onClick={event=>event.stopPropagation()} aria-label="Thêm chức năng">
        <div className="portal-mobile-more-head"><strong>Thêm chức năng</strong><button type="button" aria-label="Đóng menu" onClick={()=>setMoreOpen(false)}>×</button></div>
        <div className="portal-mobile-more-grid">{mobileMore.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-mobile-more-item "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.label}</span></a>)}</div>
      </section>
    </div>}
    <nav className="portal-mobile-nav" aria-label="Điều hướng chính trên điện thoại">
      {mobilePrimary.map(x=><a key={x.id} aria-current={active===x.id?"page":undefined} className={"portal-mobile-link "+(active===x.id?"active":"")} href={x.href}><span className="portal-nav-icon">{x.icon}</span><span>{x.short}</span></a>)}
      <button type="button" className={"portal-mobile-link "+(moreActive||moreOpen?"active":"")} aria-expanded={moreOpen} aria-label="Thêm chức năng" onClick={()=>setMoreOpen(value=>!value)}><span className="portal-nav-icon">•••</span><span>Thêm</span></button>
    </nav>
  </>
}
