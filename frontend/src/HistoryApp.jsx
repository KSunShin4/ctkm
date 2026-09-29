import React,{useEffect,useMemo,useState} from "react"
import ProductNav from "./ProductNav.jsx"
import {Mascot,assistantComponentCss} from "./assistant-components.jsx"

const API=window.location.origin

const css=[
"*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f6f9ff 0%,#f5f8ff 55%,#fff9fc 100%);color:#173052;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}",
".history-page{max-width:1260px;margin:0 auto;padding:22px 22px 92px}",
".history-hero{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;padding:19px 21px;border:1px solid #dfe8f5;border-radius:22px;background:radial-gradient(circle at 94% 8%,rgba(206,190,255,.30),transparent 26%),linear-gradient(135deg,#fff,#f8fbff 62%,#fff8fb);box-shadow:0 14px 38px rgba(51,82,122,.07)}",
".history-hero-copy{display:flex;align-items:center;gap:13px}.history-hero .mascot-avatar{width:58px;height:58px;border-radius:20px}.history-kicker{font-size:8px;font-weight:950;letter-spacing:.12em;color:#7d58dd}.history-hero h1{margin:3px 0 4px;font-size:24px;letter-spacing:-.45px}.history-hero p{margin:0;max-width:700px;color:#7587a0;font-size:9.5px;line-height:1.55}.history-refresh{height:36px;padding:0 12px;border:1px solid #d8e3f0;border-radius:10px;background:#fff;color:#536d8b;font-size:9px;font-weight:900;cursor:pointer}.history-refresh:disabled{opacity:.55;cursor:default}",
".history-note{margin-top:10px;padding:10px 12px;border:1px solid #e4eaf3;border-radius:12px;background:#fff;color:#7e8fa6;font-size:8.5px}.history-note b{color:#47617e}",
".history-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:11px}.history-stat{padding:13px;border:1px solid #e3eaf4;border-radius:15px;background:#fff;box-shadow:0 7px 20px rgba(40,75,120,.04)}.history-stat span{display:block;font-size:8px;color:#8a9ab0}.history-stat strong{display:block;margin-top:4px;font-size:21px;letter-spacing:-.03em}.history-stat.ok strong{color:#159264}.history-stat.warn strong{color:#c47a1d}.history-stat.bad strong{color:#c8495c}",
".history-toolbar{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:11px;padding:8px;border:1px solid #e2e9f3;border-radius:14px;background:#fff}.history-tabs{display:flex;gap:5px;flex-wrap:wrap}.history-tabs button{border:0;border-radius:9px;background:#f2f5f9;color:#6b7f99;padding:7px 10px;font-size:8.5px;font-weight:900;cursor:pointer}.history-tabs button.active{background:linear-gradient(135deg,#1769ff,#6678ea);color:#fff;box-shadow:0 5px 13px rgba(23,105,255,.17)}.history-count{font-size:8.5px;color:#8697ad;font-weight:800;padding-right:4px}",
".history-list{display:grid;gap:8px;margin-top:10px}.history-card{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:13px 14px;border:1px solid #e4eaf3;border-radius:16px;background:#fff;box-shadow:0 7px 20px rgba(41,73,115,.035)}.history-icon{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;font-size:18px;background:#eef4ff;color:#1769ff}.history-card.tem_r .history-icon{background:#f4ecff;color:#8b4de8}.history-main{min-width:0}.history-topline{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.history-title{font-size:10.5px;font-weight:900;color:#2c435f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:560px}.history-kind{font-size:7.5px;padding:4px 6px;border-radius:999px;background:#eef4ff;color:#1769ff;font-weight:900}.history-card.tem_r .history-kind{background:#f5edff;color:#8b4de8}.history-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;color:#8b9ab0;font-size:8px}.history-message{margin-top:5px;font-size:8.5px;color:#637995;line-height:1.35}.history-actions{display:flex;align-items:center;gap:7px}.history-status{font-size:8px;padding:5px 7px;border-radius:999px;background:#f0f3f7;color:#72849c;font-weight:900;white-space:nowrap}.history-status.completed{background:#e9f9f1;color:#15895b}.history-status.failed{background:#fff0f2;color:#c7435c}.history-status.running,.history-status.queued{background:#fff7e8;color:#c4771a}.history-status.awaiting_mapping_confirmation{background:#fff0f4;color:#c84969}.history-download{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:0 10px;border-radius:9px;background:#eef4ff;color:#1769ff;text-decoration:none;font-size:8.5px;font-weight:900}.history-error{margin-top:10px;padding:10px 12px;border:1px solid #f0d8dd;border-radius:12px;background:#fff7f8;color:#c0445b;font-size:9px}.history-empty{margin-top:11px;padding:28px 16px;border:1px dashed #d9e3ef;border-radius:18px;background:rgba(255,255,255,.7);text-align:center}.history-empty .mascot{justify-content:center}.history-empty h2{margin:9px 0 4px;font-size:14px}.history-empty p{margin:0;color:#8293aa;font-size:9px}",
"@media(max-width:760px){.history-page{padding:12px 10px 86px}.history-hero{grid-template-columns:1fr;padding:14px;border-radius:17px}.history-hero-copy{align-items:flex-start}.history-hero .mascot-avatar{width:46px;height:46px;border-radius:15px}.history-hero h1{font-size:20px}.history-refresh{justify-self:start}.history-stats{grid-template-columns:1fr 1fr}.history-toolbar{align-items:flex-start;flex-direction:column}.history-card{grid-template-columns:auto 1fr;align-items:start}.history-actions{grid-column:1/-1;justify-content:flex-end}.history-title{max-width:230px}.history-meta{gap:6px}}"
].join("")

const statusLabel=s=>({completed:"Hoàn tất",failed:"Lỗi",running:"Đang chạy",queued:"Đang chờ",awaiting_mapping_confirmation:"Chờ mapping"}[s]||s||"—")
const kindLabel=k=>k==="tem_r"?"Tem R":"CTKM"
const kindIcon=k=>k==="tem_r"?"◇":"✦"

function formatWhen(value){
  if(!value)return"—"
  const d=new Date(value)
  if(Number.isNaN(d.getTime()))return String(value)
  return new Intl.DateTimeFormat("vi-VN",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"}).format(d)
}

export default function HistoryApp(){
  const [jobs,setJobs]=useState([])
  const [filter,setFilter]=useState("all")
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState("")

  const load=async()=>{
    setLoading(true);setError("")
    try{
      const res=await fetch(API+"/api/jobs")
      const body=await res.json()
      if(!res.ok)throw new Error(typeof body?.detail==="string"?body.detail:"Không tải được lịch sử")
      setJobs(Array.isArray(body)?body:[])
    }catch(err){setError(err.message||String(err))}
    finally{setLoading(false)}
  }

  useEffect(()=>{load()},[])

  const stats=useMemo(()=>({
    total:jobs.length,
    completed:jobs.filter(x=>x.status==="completed").length,
    active:jobs.filter(x=>["queued","running","awaiting_mapping_confirmation"].includes(x.status)).length,
    failed:jobs.filter(x=>x.status==="failed").length,
  }),[jobs])

  const visible=useMemo(()=>jobs.filter(job=>{
    if(filter==="ctkm")return job.kind==="ctkm"
    if(filter==="tem_r")return job.kind==="tem_r"
    if(filter==="attention")return job.status==="failed"||job.status==="awaiting_mapping_confirmation"
    return true
  }),[jobs,filter])

  return <><ProductNav current="history"/><main className="history-page"><style>{css}</style><style>{assistantComponentCss}</style>
    <section className="history-hero">
      <div className="history-hero-copy"><Mascot state={error?"warning":loading?"thinking":"guide"}/><div><div className="history-kicker">LỊCH SỬ VẬN HÀNH</div><h1>Các tác vụ gần đây</h1><p>Hiển thị lifecycle job mà backend đang giữ trong phiên Cloud Run hiện tại. Đây chưa phải kho lịch sử vĩnh viễn qua restart/deploy.</p></div></div>
      <button className="history-refresh" type="button" onClick={load} disabled={loading}>{loading?"Đang tải…":"↻ Làm mới"}</button>
    </section>
    <div className="history-note"><b>Phạm vi:</b> CTKM và Tem R từ <code>/api/jobs</code>. Chỉ job hoàn tất và còn file output mới có nút tải lại.</div>
    {error&&<div className="history-error">⚠ {error}</div>}

    <section className="history-stats">
      <div className="history-stat"><span>Tổng job trong phiên</span><strong>{stats.total}</strong></div>
      <div className="history-stat ok"><span>Hoàn tất</span><strong>{stats.completed}</strong></div>
      <div className="history-stat warn"><span>Đang xử lý / chờ</span><strong>{stats.active}</strong></div>
      <div className="history-stat bad"><span>Lỗi</span><strong>{stats.failed}</strong></div>
    </section>

    <div className="history-toolbar">
      <div className="history-tabs">
        {[["all","Tất cả"],["ctkm","CTKM"],["tem_r","Tem R"],["attention","Cần chú ý"]].map(([key,label])=><button key={key} type="button" className={filter===key?"active":""} onClick={()=>setFilter(key)}>{label}</button>)}
      </div>
      <div className="history-count">{visible.length} / {jobs.length} job</div>
    </div>

    {visible.length?<section className="history-list">{visible.map(job=><article className={"history-card "+(job.kind||"ctkm")} key={job.job_id}>
      <div className="history-icon">{kindIcon(job.kind)}</div>
      <div className="history-main">
        <div className="history-topline"><div className="history-title">{job.month?kindLabel(job.kind)+" · "+job.month:kindLabel(job.kind)+" · "+job.job_id}</div><span className="history-kind">{kindLabel(job.kind)}</span></div>
        <div className="history-meta"><span>{formatWhen(job.created_at)}</span><span>Job {job.job_id}</span>{Number.isFinite(job.progress)&&<span>{job.progress}%</span>}</div>
        <div className="history-message">{job.error||job.message||"Không có ghi chú."}</div>
      </div>
      <div className="history-actions"><span className={"history-status "+(job.status||"")}>{statusLabel(job.status)}</span>{job.has_output&&<a className="history-download" href={API+"/api/download/"+encodeURIComponent(job.job_id)}>↓ Tải file</a>}</div>
    </article>)}</section>:!loading&&<section className="history-empty"><Mascot state="guide"/><h2>Chưa có tác vụ trong bộ lọc này</h2><p>Chạy CTKM hoặc Tem R, sau đó quay lại đây để xem lifecycle và tải lại output còn hiệu lực.</p></section>}
  </main></>
}
