import React,{useEffect,useMemo,useState} from "react"
import ProductNav from "./ProductNav.jsx"
import {Mascot,assistantComponentCss} from "./assistant-components.jsx"

const API=window.location.origin
const token=()=>sessionStorage.getItem("ctkm.admin.token")||localStorage.getItem("admin_token")||""
const authFetch=(url,opts={})=>fetch(url,{...opts,headers:{...(opts.headers||{}),...(token()?{Authorization:"Bearer "+token()}:{})}})

const css=[
"*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f6f9ff 0%,#f5f8ff 56%,#fff9fc 100%);color:#173052;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}",
".ops-dashboard{max-width:1360px;margin:0 auto;padding:22px 24px 92px}",
".overview-hero{position:relative;overflow:hidden;display:grid;grid-template-columns:1fr auto;align-items:center;gap:22px;padding:20px 22px;border:1px solid #dce8f7;border-radius:24px;background:radial-gradient(circle at 92% 10%,rgba(255,196,225,.38),transparent 26%),radial-gradient(circle at 72% 120%,rgba(178,230,255,.46),transparent 31%),linear-gradient(135deg,#fff 0%,#f7fbff 58%,#fff7fb 100%);box-shadow:0 14px 40px rgba(54,92,142,.08);margin-bottom:13px}",
".overview-hero-copy{display:flex;align-items:center;gap:14px;min-width:0}.overview-hero .mascot-avatar{width:62px;height:62px;border-radius:21px}.overview-kicker{font-size:9px;color:#1769ff;font-weight:950;text-transform:uppercase;letter-spacing:.11em}.overview-hero h1{font-size:25px;margin:3px 0 4px;letter-spacing:-.5px}.overview-hero p{margin:0;color:#71839f;font-size:10px;line-height:1.55}.overview-date{display:flex;flex-direction:column;align-items:flex-end;gap:5px;padding:10px 13px;background:rgba(255,255,255,.82);border:1px solid #e2eaf4;border-radius:14px;font-size:9px;color:#7a8da7;backdrop-filter:blur(8px)}.overview-date strong{font-size:13px;color:#173052}",
".metric-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}",
".module-card{position:relative;overflow:hidden;background:#fff;border:1px solid #e3eaf4;border-radius:19px;padding:15px;min-height:178px;box-shadow:0 10px 30px rgba(36,75,125,.055)}.module-card:after{content:'';position:absolute;width:100px;height:100px;border-radius:50%;right:-44px;top:-44px;background:var(--soft)}",
".module-head{display:flex;align-items:center;gap:9px;position:relative;z-index:1}.module-icon{width:42px;height:42px;border-radius:13px;background:var(--soft);display:grid;place-items:center;font-size:20px}.module-title{font-size:12px;font-weight:900}.module-value{margin-top:11px;font-size:24px;font-weight:950;letter-spacing:-.04em}.module-sub{font-size:8.5px;color:#8192aa;margin-top:3px;line-height:1.4}.module-alert{display:inline-flex;align-items:center;gap:5px;margin-top:8px;padding:5px 7px;border-radius:999px;background:#fff0f3;color:#cc4760;font-size:8px;font-weight:900}.module-note{display:inline-flex;margin-top:8px;padding:5px 7px;border-radius:999px;background:var(--soft);color:var(--accent);font-size:8px;font-weight:900}",
".module-link{position:absolute;left:14px;right:14px;bottom:13px;text-decoration:none;text-align:center;padding:8px 9px;border-radius:10px;background:var(--soft);color:var(--accent);font-size:9px;font-weight:900}",
".module-card.ctkm{--accent:#1769ff;--soft:#eaf2ff}.module-card.shelf{--accent:#12a86b;--soft:#e9fbf3}.module-card.temr{--accent:#8b4de8;--soft:#f3ebff}.module-card.inventory{--accent:#f08a25;--soft:#fff2e5}.module-card.expiration{--accent:#20a6be;--soft:#e8f9fb}",
".dashboard-row{display:grid;grid-template-columns:1.35fr .92fr .92fr;gap:10px;margin-top:10px}.panel{background:#fff;border:1px solid #e3eaf4;border-radius:19px;padding:15px;box-shadow:0 10px 30px rgba(36,75,125,.045)}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:9px}.panel h2{font-size:13px;margin:0}.panel-link{font-size:9px;color:#1769ff;text-decoration:none;font-weight:850}",
".work-row{display:grid;grid-template-columns:70px 1fr auto;gap:8px;align-items:center;padding:8px 0;border-top:1px solid #f0f3f8}.work-row:first-of-type{border-top:0}.work-type{font-size:8px;font-weight:900;padding:4px 6px;border-radius:999px;text-align:center;background:#eef4ff;color:#1769ff}.work-title{font-size:10px;font-weight:850}.work-meta{font-size:8px;color:#91a0b4;margin-top:2px;line-height:1.35}.status{font-size:8px;padding:5px 7px;border-radius:999px;background:#f1f4f8;color:#718099;font-weight:850}.status.completed{background:#e8f8ef;color:#16895d}.status.failed{background:#fff0f0;color:#d04444}.status.running,.status.queued{background:#fff7e8;color:#c57a1e}.status.awaiting_mapping_confirmation{background:#fff0f3;color:#cc4760}",
".quick-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.quick-link{display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #e7edf6;border-radius:12px;background:#fbfdff;color:#39516f;text-decoration:none;font-size:9px;font-weight:850}.quick-link b{width:28px;height:28px;border-radius:9px;background:#eef4ff;display:grid;place-items:center;color:#1769ff}.quick-link:hover{border-color:#bfd4f4;background:#f6faff}",
".system-list{display:grid;gap:7px}.system-row{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;border-radius:11px;background:#f8fbff;border:1px solid #e8eef7;font-size:9px}.system-row span{color:#8192aa}.system-row strong{color:#2f4968;text-align:right}.system-ok{color:#0d9461!important}.system-warn{color:#c7781d!important}",
".shelf-helper{display:grid;gap:7px}.shelf-helper div{padding:9px 10px;border:1px solid #e9eef5;border-radius:11px;background:#fff}.shelf-helper strong{display:block;font-size:9px}.shelf-helper span{display:block;margin-top:2px;font-size:8px;color:#8a9ab0;line-height:1.4}",
".empty-note{padding:18px 8px;text-align:center;color:#8a9ab0;font-size:10px}.health-note{margin-top:10px;padding:10px 12px;border-radius:12px;background:#f7fbff;border:1px solid #e5edf7;color:#7890ad;font-size:9px}.health-note strong{color:#1769ff}",
"@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(3,1fr)}.dashboard-row{grid-template-columns:1fr 1fr}.dashboard-row .panel:first-child{grid-column:1/-1}}",
"@media(max-width:760px){.ops-dashboard{padding:12px 10px 88px}.overview-hero{grid-template-columns:1fr;padding:14px;border-radius:18px}.overview-hero-copy{align-items:flex-start}.overview-hero .mascot-avatar{width:48px;height:48px;border-radius:16px}.overview-hero h1{font-size:20px}.overview-date{display:none}.metric-grid{grid-template-columns:1fr 1fr;gap:8px}.module-card{min-height:166px;padding:12px}.module-card.expiration{grid-column:1/-1}.module-value{font-size:21px}.dashboard-row{grid-template-columns:1fr}.dashboard-row .panel:first-child{grid-column:auto}.quick-grid{grid-template-columns:1fr 1fr}.work-row{grid-template-columns:60px 1fr auto}}"
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
    const active=jobs.filter(x=>x.status==="running"||x.status==="queued")
    const completed=jobs.filter(x=>x.status==="completed")
    return {ctkm,temr,attention,active,completed,latest:jobs.slice(0,6),waiting:(queue?.waiting||[]).length}
  },[jobs,queue])

  const mascotState=stats.attention.length?"warning":stats.active.length?"thinking":"guide"
  const quickActions=[
    ["✦","CTKM","/?module=ctkm"],
    ["✓","Kiểm kệ","/scan-tem?mode=shelf"],
    ["◇","Tem R","/?module=temr"],
    ["▣","Kiểm tồn","/?module=inventory"],
    ["◷","Hạn dùng","/?module=expiration"],
  ]

  return <><ProductNav current="overview"/><main className="ops-dashboard"><style>{css}</style><style>{assistantComponentCss}</style>
    <header className="overview-hero">
      <div className="overview-hero-copy"><Mascot state={mascotState}/><div><div className="overview-kicker">PharmaOps · Vận hành cửa hàng</div><h1>Hôm nay mình làm gì trước?</h1><p>Đi thẳng vào công việc cần làm. Dashboard chỉ hiển thị dữ liệu backend thật; tiến độ Kiểm kệ được lưu riêng trên thiết bị.</p></div></div>
      <div className="overview-date"><span>Ngày hiện tại</span><strong>{today()}</strong></div>
    </header>
    {error&&<div className="health-note">{error}</div>}

    <section className="metric-grid">
      <article className="module-card ctkm"><div className="module-head"><div className="module-icon">✦</div><div><div className="module-title">CTKM</div><div className="module-sub">Khuyến mãi + POG + Clearance</div></div></div><div className="module-value">{stats.ctkm.length||"—"}</div><div className="module-sub">job CTKM backend đang giữ</div>{stats.attention.length>0&&<div className="module-alert">● {stats.attention.length} job cần chú ý</div>}<a className="module-link" href="/?module=ctkm">Mở CTKM →</a></article>
      <article className="module-card shelf"><div className="module-head"><div className="module-icon">✓</div><div><div className="module-title">Kiểm kệ</div><div className="module-sub">Luồng thực thi tại cửa hàng</div></div></div><div className="module-value">Theo kệ</div><div className="module-note">Tiến độ lưu trên thiết bị</div><div className="module-sub">Cần quay lại · Chưa kiểm · Cần tháo · Hoàn tất</div><a className="module-link" href="/scan-tem?mode=shelf">Tiếp tục kiểm kệ →</a></article>
      <article className="module-card temr"><div className="module-head"><div className="module-icon">◇</div><div><div className="module-title">Tem R</div><div className="module-sub">Phân bổ theo tồn + POG</div></div></div><div className="module-value">{stats.temr.length||"—"}</div><div className="module-sub">job Tem R backend đang giữ</div><a className="module-link" href="/?module=temr">Mở Tem R →</a></article>
      <article className="module-card inventory"><div className="module-head"><div className="module-icon">▣</div><div><div className="module-title">Kiểm tồn kho</div><div className="module-sub">Tồn store-level ↔ POG</div></div></div><div className="module-value">Sẵn sàng</div><div className="module-sub">Không cộng lặp tồn giữa nhiều vị trí</div><a className="module-link" href="/?module=inventory">Mở kiểm tồn kho →</a></article>
      <article className="module-card expiration"><div className="module-head"><div className="module-icon">◷</div><div><div className="module-title">Kiểm hạn dùng</div><div className="module-sub">ITEMID · lô · HSD · tồn kho</div></div></div><div className="module-value">Sẵn sàng</div><div className="module-sub">Nhập tay là chính · camera hỗ trợ quét mã</div><a className="module-link" href="/?module=expiration">Mở kiểm hạn dùng →</a></article>
    </section>

    <section className="dashboard-row">
      <article className="panel"><div className="panel-head"><h2>Công việc gần đây</h2><a className="panel-link" href="/?module=ctkm">Mở CTKM →</a></div>
        {stats.latest.length?stats.latest.map(j=><div className="work-row" key={j.job_id}><span className="work-type">{j.kind==="tem_r"?"Tem R":"CTKM"}</span><div><div className="work-title">{j.output_name||j.month||"Công việc cửa hàng"}</div><div className="work-meta">{j.message||j.created_at||j.job_id}</div></div><span className={"status "+(j.status||"")}>{statusLabel(j.status)}</span></div>):<div className="empty-note">Chưa có job backend trong phiên. Bạn vẫn có thể bắt đầu CTKM, Kiểm kệ, Tem R hoặc Hạn dùng.</div>}
      </article>
      <article className="panel"><div className="panel-head"><h2>Bắt đầu nhanh</h2><span className="panel-link">5 công cụ chính</span></div><div className="quick-grid">{quickActions.map(([icon,label,href])=><a className="quick-link" href={href} key={label}><b>{icon}</b><span>{label}</span></a>)}</div></article>
      <article className="panel"><div className="panel-head"><h2>Trạng thái hệ thống</h2><span className="panel-link">Dữ liệu thật</span></div><div className="system-list">
        <div className="system-row"><span>Backend</span><strong className={health?.status==="ok"?"system-ok":""}>{health?.status==="ok"?"Đã kết nối":"Đang kiểm tra"}</strong></div>
        <div className="system-row"><span>Job đang chạy/chờ</span><strong className={stats.active.length||stats.waiting?"system-warn":""}>{stats.active.length+stats.waiting}</strong></div>
        <div className="system-row"><span>Job hoàn tất</span><strong>{stats.completed.length}</strong></div>
        <div className="system-row"><span>Export profile</span><strong>{health?.ctkm_output_profile||"—"}</strong></div>
      </div></article>
    </section>

    <section className="dashboard-row">
      <article className="panel"><div className="panel-head"><h2>Kiểm kệ nên dùng thế nào?</h2><a className="panel-link" href="/scan-tem?mode=shelf">Mở Kiểm kệ →</a></div><div className="shelf-helper">
        <div><strong>1. Đi theo kệ</strong><span>Danh sách kệ và action là luồng chính, không cần camera.</span></div>
        <div><strong>2. Xử lý Cần quay lại trước</strong><span>Sai/Review và tem chưa tháo vẫn được giữ để quay lại.</span></div>
        <div><strong>3. Camera là công cụ phụ</strong><span>Quét nhanh chỉ hỗ trợ đọc/tìm; không tự quyết định nghiệp vụ.</span></div>
      </div></article>
      <article className="panel"><div className="panel-head"><h2>Dữ liệu dashboard</h2></div><div className="shelf-helper">
        <div><strong>Không bịa tiến độ</strong><span>Dashboard không hiển thị % Kiểm kệ nếu backend không cung cấp.</span></div>
        <div><strong>Không bịa số tồn/HSD</strong><span>Số liệu chỉ xuất hiện sau khi người dùng chạy module tương ứng.</span></div>
      </div></article>
      <article className="panel"><div className="panel-head"><h2>Cần chú ý</h2></div>{stats.attention.length?<div className="shelf-helper"><div><strong>{stats.attention.length} job cần xử lý</strong><span>Có job lỗi hoặc đang chờ xác nhận mapping.</span></div></div>:<div className="empty-note">Không có job backend nào đang báo lỗi hoặc chờ mapping.</div>}</article>
    </section>
  </main></>
}
