import React,{useEffect,useMemo,useState} from "react"
import ProductNav from "./ProductNav.jsx"

const API=window.location.origin
const token=()=>sessionStorage.getItem("ctkm.admin.token")||localStorage.getItem("admin_token")||""
const authFetch=(url,opts={})=>fetch(url,{...opts,headers:{...(opts.headers||{}),...(token()?{Authorization:"Bearer "+token()}:{})}})

const css=[
"*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f7fbff 0,#f5f8ff 50%,#fffafc 100%);color:#173052;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}",
".ops-dashboard{max-width:1480px;margin:0 auto;padding:22px 22px 90px}",
".ops-top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:15px}",
".ops-greeting{display:flex;align-items:center;gap:12px}.ops-mascot{width:54px;height:54px;border-radius:18px;display:grid;place-items:center;font-size:29px;background:linear-gradient(145deg,#e9f5ff,#fff1f7);border:1px solid #e0eaf6;box-shadow:0 8px 22px rgba(40,99,160,.09)}",
".ops-kicker{font-size:10px;color:#1769ff;font-weight:950;text-transform:uppercase;letter-spacing:.1em}.ops-top h1{font-size:24px;margin:3px 0 2px;letter-spacing:-.03em}.ops-top p{margin:0;color:#71839f;font-size:11px}",
".ops-date{display:flex;align-items:center;gap:8px;padding:10px 13px;background:#fff;border:1px solid #e2eaf4;border-radius:13px;font-size:10px;color:#667b99}.ops-date strong{font-size:12px;color:#173052}",
".metric-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}",
".module-card{position:relative;overflow:hidden;background:#fff;border:1px solid #e3eaf4;border-radius:18px;padding:15px;min-height:174px;box-shadow:0 10px 30px rgba(36,75,125,.055)}.module-card:after{content:'';position:absolute;width:95px;height:95px;border-radius:50%;right:-42px;top:-42px;background:var(--soft)}",
".module-head{display:flex;align-items:center;gap:9px;position:relative;z-index:1}.module-icon{width:42px;height:42px;border-radius:13px;background:var(--soft);display:grid;place-items:center;font-size:21px}.module-title{font-size:12px;font-weight:900}.module-value{margin-top:10px;font-size:27px;font-weight:950;letter-spacing:-.04em}.module-sub{font-size:9px;color:#7f91aa;margin-top:2px}.module-alert{display:flex;align-items:center;gap:5px;margin-top:10px;padding:7px 9px;border-radius:9px;background:#fff4f4;color:#d04444;font-size:9px;font-weight:800}.module-progress{height:7px;background:#edf2f7;border-radius:99px;margin-top:10px;overflow:hidden}.module-progress i{display:block;height:100%;border-radius:99px;background:var(--accent);width:34%}",
".module-link{position:absolute;left:14px;right:14px;bottom:13px;text-decoration:none;text-align:center;padding:8px 9px;border-radius:10px;background:var(--soft);color:var(--accent);font-size:9px;font-weight:900}",
".module-card.ctkm{--accent:#1769ff;--soft:#eaf2ff}.module-card.shelf{--accent:#12a86b;--soft:#e9fbf3}.module-card.temr{--accent:#8b4de8;--soft:#f3ebff}.module-card.inventory{--accent:#f08a25;--soft:#fff2e5}.module-card.expiration{--accent:#20a6be;--soft:#e8f9fb}",
".dashboard-row{display:grid;grid-template-columns:1.35fr .8fr 1fr;gap:10px;margin-top:10px}.panel{background:#fff;border:1px solid #e3eaf4;border-radius:18px;padding:15px;box-shadow:0 10px 30px rgba(36,75,125,.045)}.panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}.panel h2{font-size:13px;margin:0}.panel-link{font-size:9px;color:#1769ff;text-decoration:none;font-weight:850}",
".work-row{display:grid;grid-template-columns:70px 1fr auto;gap:8px;align-items:center;padding:8px 0;border-top:1px solid #f0f3f8}.work-row:first-of-type{border-top:0}.work-type{font-size:8px;font-weight:900;padding:4px 6px;border-radius:999px;text-align:center;background:#eef4ff;color:#1769ff}.work-title{font-size:10px;font-weight:850}.work-meta{font-size:8px;color:#91a0b4;margin-top:2px}.status{font-size:8px;padding:5px 7px;border-radius:999px;background:#f1f4f8;color:#718099;font-weight:850}.status.completed{background:#e8f8ef;color:#16895d}.status.failed{background:#fff0f0;color:#d04444}.status.running,.status.queued{background:#fff7e8;color:#c57a1e}.status.awaiting_mapping_confirmation{background:#fff0f3;color:#cc4760}",
".ring-wrap{display:flex;align-items:center;justify-content:center;min-height:170px}.ring{position:relative;width:136px;height:136px;border-radius:50%;background:conic-gradient(#1769ff 0 59%,#20b67a 59% 78%,#9657ec 78% 87%,#f39a36 87% 98%,#3dc2d4 98%);display:grid;place-items:center}.ring:before{content:'';width:88px;height:88px;background:#fff;border-radius:50%;position:absolute}.ring strong,.ring span{position:relative;z-index:1}.ring strong{font-size:22px}.ring span{font-size:8px;color:#8091aa;display:block;text-align:center;margin-top:-35px}",
".shelf-list{display:grid;gap:6px}.shelf-item{display:grid;grid-template-columns:1fr auto;gap:8px;padding:9px 0;border-top:1px solid #f0f3f8}.shelf-item:first-child{border-top:0}.shelf-name{font-size:10px;font-weight:900}.shelf-meta{font-size:8px;color:#8a9ab0;margin-top:2px}.shelf-badge{font-size:8px;font-weight:900;color:#d14d52;background:#fff0f1;border-radius:999px;padding:5px 7px;align-self:center}",
".empty-note{padding:18px 8px;text-align:center;color:#8a9ab0;font-size:10px}.health-note{margin-top:10px;padding:10px 12px;border-radius:12px;background:#f7fbff;border:1px solid #e5edf7;color:#7890ad;font-size:9px}.health-note strong{color:#1769ff}",
"@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(3,1fr)}.dashboard-row{grid-template-columns:1fr 1fr}.dashboard-row .panel:first-child{grid-column:1/-1}}",
"@media(max-width:760px){.ops-dashboard{padding:14px 10px 88px}.ops-top{align-items:flex-start}.ops-mascot{width:46px;height:46px;font-size:24px}.ops-top h1{font-size:20px}.ops-date{display:none}.metric-grid{grid-template-columns:1fr 1fr;gap:8px}.module-card{min-height:164px;padding:12px}.module-card.expiration{grid-column:1/-1}.module-value{font-size:22px}.dashboard-row{grid-template-columns:1fr}.dashboard-row .panel:first-child{grid-column:auto}.ring-wrap{min-height:150px}}"
].join("")

const statusLabel=s=>({completed:"Hoàn tất",failed:"Lỗi",running:"Đang chạy",queued:"Đang chờ",awaiting_mapping_confirmation:"Chờ mapping"}[s]||s||"—")
const today=()=>new Intl.DateTimeFormat("vi-VN",{day:"2-digit",month:"2-digit",year:"numeric"}).format(new Date())

export default function OverviewDashboard(){
  const [jobs,setJobs]=useState([]),[queue,setQueue]=useState(null),[health,setHealth]=useState(null),[error,setError]=useState("")
  useEffect(()=>{let live=true
    Promise.allSettled([authFetch(API+"/api/jobs"),authFetch(API+"/api/queue/status"),fetch(API+"/api/health")]).then(async results=>{
      if(!live)return
      const [jr,qr,hr]=results
      if(jr.status==="fulfilled"&&jr.value.ok){const body=await jr.value.json();setJobs(Array.isArray(body)?body:[])}
      if(qr.status==="fulfilled"&&qr.value.ok)setQueue(await qr.value.json())
      if(hr.status==="fulfilled"&&hr.value.ok)setHealth(await hr.value.json())
      if(jr.status==="fulfilled"&&jr.value.status!==401&&!jr.value.ok)setError("Không tải được lịch sử job.")
    }).catch(e=>live&&setError(e.message))
    return()=>{live=false}
  },[])

  const stats=useMemo(()=>{
    const ctkm=jobs.filter(x=>x.kind==="ctkm")
    const temr=jobs.filter(x=>x.kind==="tem_r")
    const attention=jobs.filter(x=>x.status==="failed"||x.status==="awaiting_mapping_confirmation")
    return {ctkm,temr,attention,latest:jobs.slice(0,6),waiting:(queue?.waiting||[]).length}
  },[jobs,queue])

  const recentShelves=[
    {name:"Kệ cần quay lại",meta:"Mở Kiểm kệ để xem danh sách theo POG",count:"→"},
    {name:"Sai / Review",meta:"Ưu tiên xử lý trước khi hoàn tất kệ",count:"!"},
    {name:"Chưa kiểm",meta:"Tiến độ lưu theo phiên kiểm kệ",count:"…"},
  ]

  return <><ProductNav current="overview"/><main className="ops-dashboard"><style>{css}</style>
    <header className="ops-top">
      <div className="ops-greeting"><div className="ops-mascot" aria-hidden="true">💊✨</div><div><div className="ops-kicker">Vận hành cửa hàng</div><h1>Xin chào, hôm nay mình làm gì trước?</h1><p>CTKM · Kiểm kệ · Tem R · Kiểm tồn · Kiểm hạn dùng</p></div></div>
      <div className="ops-date"><span>Ngày nghiệp vụ</span><strong>{today()}</strong></div>
    </header>
    {error&&<div className="health-note">{error}</div>}

    <section className="metric-grid">
      <article className="module-card ctkm"><div className="module-head"><div className="module-icon">✦</div><div><div className="module-title">CTKM</div><div className="module-sub">Chương trình khuyến mãi</div></div></div><div className="module-value">{stats.ctkm.length||"—"}</div><div className="module-sub">job CTKM trong phiên backend</div>{stats.attention.length>0&&<div className="module-alert">● {stats.attention.length} mục cần chú ý</div>}<a className="module-link" href="/?module=ctkm">Mở CTKM →</a></article>
      <article className="module-card shelf"><div className="module-head"><div className="module-icon">✓</div><div><div className="module-title">Kiểm kệ</div><div className="module-sub">Luồng thực thi chính</div></div></div><div className="module-value">Theo kệ</div><div className="module-progress"><i/></div><div className="module-sub">Đúng · Sai · Review · Cần quay lại</div><a className="module-link" href="/scan-tem?mode=shelf">Tiếp tục kiểm kệ →</a></article>
      <article className="module-card temr"><div className="module-head"><div className="module-icon">◇</div><div><div className="module-title">Tem R</div><div className="module-sub">Phân bổ theo tồn + POG</div></div></div><div className="module-value">{stats.temr.length||"—"}</div><div className="module-sub">job Tem R trong phiên backend</div><a className="module-link" href="/?module=temr">Mở Tem R →</a></article>
      <article className="module-card inventory"><div className="module-head"><div className="module-icon">▣</div><div><div className="module-title">Kiểm tồn kho</div><div className="module-sub">Tồn store-level ↔ POG</div></div></div><div className="module-value">Sẵn sàng</div><div className="module-sub">Không cộng lặp tồn giữa nhiều vị trí</div><a className="module-link" href="/?module=inventory">Mở kiểm tồn kho →</a></article>
      <article className="module-card expiration"><div className="module-head"><div className="module-icon">◷</div><div><div className="module-title">Kiểm hạn dùng</div><div className="module-sub">Lô · HSD · tồn kho</div></div></div><div className="module-value">Sẵn sàng</div><div className="module-sub">Dùng checker hiện tại</div><a className="module-link" href="/?module=expiration">Mở kiểm hạn dùng →</a></article>
    </section>

    <section className="dashboard-row">
      <article className="panel"><div className="panel-head"><h2>Công việc gần đây</h2><a className="panel-link" href="/?module=ctkm">Mở CTKM →</a></div>
        {stats.latest.length?stats.latest.map(j=><div className="work-row" key={j.job_id}><span className="work-type">{j.kind==="tem_r"?"Tem R":"CTKM"}</span><div><div className="work-title">{j.output_name||j.month||"Công việc cửa hàng"}</div><div className="work-meta">{j.message||j.created_at||j.job_id}</div></div><span className={"status "+(j.status||"")}>{statusLabel(j.status)}</span></div>):<div className="empty-note">Chưa có job trong phiên. Bạn vẫn có thể bắt đầu CTKM, Kiểm kệ hoặc Tem R.</div>}
      </article>
      <article className="panel"><div className="panel-head"><h2>Phân bố công việc</h2><span className="panel-link">Theo module</span></div><div className="ring-wrap"><div className="ring"><strong>{jobs.length||0}</strong><span>job phiên này</span></div></div></article>
      <article className="panel"><div className="panel-head"><h2>Ưu tiên kiểm kệ</h2><a className="panel-link" href="/scan-tem?mode=shelf">Mở danh sách →</a></div><div className="shelf-list">{recentShelves.map(x=><div className="shelf-item" key={x.name}><div><div className="shelf-name">{x.name}</div><div className="shelf-meta">{x.meta}</div></div><span className="shelf-badge">{x.count}</span></div>)}</div></article>
    </section>
    <div className="health-note"><strong>{health?.status==="ok"?"● Hệ thống ổn định":"○ Đang kiểm tra hệ thống"}</strong>{health?.ctkm_output_profile?" · Export: "+health.ctkm_output_profile:""}{stats.waiting?" · Queue đang chờ: "+stats.waiting:""}</div>
  </main></>
}
