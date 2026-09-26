import React,{useMemo,useState} from "react"
import ProductNav from "./ProductNav.jsx"
import {HelpTip, MODULE_HELP, helpTipCss} from "./help-foundation.jsx"

const ARTICLES=[
  {id:"quick",group:"Bắt đầu",title:"Bắt đầu nhanh",summary:"Chọn đúng công cụ rồi thực hiện theo 3–6 bước ngắn.",steps:[
    "CTKM / Tem: vào CTKM / Tem để tổng hợp CTKM, Tem R hoặc kiểm tem.",
    "Xếp lịch: đăng nhập quản trị, chọn tuần và kiểm tra nhân viên.",
    "Nhập OFF, nguyện vọng, nhận hàng và các rule cần thiết.",
    "Tạo phương án, chỉnh trực tiếp và xem gợi ý theo lịch hiện tại.",
    "Khi hoàn tất, bấm Kiểm tra & Xuất Excel. Cảnh báo nghiệp vụ không chặn xuất."
  ]},
  {id:"ctkm",group:"CTKM / Tem",title:"Tổng hợp CTKM",summary:"Đọc CTKM + POG và tạo workbook hành động.",steps:[
    "Chọn File CTKM và đúng sheet cần xử lý.",
    "Chọn File POG; nếu workbook có nhiều sheet, chọn sheet POG tương ứng.",
    "Clearance chỉ thêm khi kỳ đó có dữ liệu clearance.",
    "Kiểm tra mapping khi hệ thống yêu cầu hoặc khi tên cột nguồn thay đổi.",
    "Chạy xử lý, xem preview rồi tải workbook kết quả."
  ],notes:["Người dùng cửa hàng có thể dùng CTKM/Tem mà không cần đăng nhập admin.","Preset dùng chung và queue/system vẫn là chức năng quản trị."]},
  {id:"tag",group:"CTKM / Tem",title:"Kiểm tem CTKM",summary:"Kiểm từng action hoặc kiểm theo kệ.",steps:[
    "Mở Kiểm tem CTKM để tải workbook action.",
    "Chọn chế độ thường, quét nhanh hoặc Kiểm theo kệ.",
    "Đối chiếu đúng/sai theo action hiện tại; tiến độ được hiển thị trong phiên làm việc.",
    "Nếu kiểm theo kệ, ưu tiên đi theo POG/vị trí để giảm bỏ sót."
  ],links:[["Mở kiểm tem","/scan-tem"],["Kiểm theo kệ","/scan-tem?mode=shelf"]]},
  {id:"temr",group:"CTKM / Tem",title:"Phân bổ Tem R",summary:"Chọn đúng cột tồn và tạo file Tem R.",steps:[
    "Tải file Tem R .xlsx.",
    "Chọn sheet và xác nhận mapping cột nếu file có cấu trúc khác.",
    "Chọn cột tồn kho đang hiển thị trong file.",
    "Chạy phân bổ và tải file kết quả."
  ]},
  {id:"schedule",group:"Xếp lịch",title:"Tạo lịch tuần",summary:"Tạo phương án rồi chỉnh thủ công khi cần.",steps:[
    "Chọn tuần và kiểm tra danh sách nhân viên.",
    "Khai báo OFF / ca bắt buộc / ca ưu tiên.",
    "Xác nhận ngày nhận hàng, target S/C, quan hệ nhân viên và trend CHT.",
    "Bấm Tạo phương án và chọn phương án gần mong muốn nhất.",
    "Chỉnh trực tiếp trên lịch; thống kê và trợ lý cập nhật theo lịch hiện tại."
  ],links:[["Mở Xếp lịch","/schedule"]]},
  {id:"schedule-edit",group:"Xếp lịch",title:"Chỉnh lịch và gợi ý thông minh",summary:"Người dùng quyết định, hệ thống chỉ đề xuất.",steps:[
    "Ô đã chỉnh tay được đánh dấu để hệ thống ưu tiên giữ.",
    "Trợ lý có thể đề xuất cân Sáng/Chiều, nhận hàng hoặc swap để giảm lệch.",
    "Đọc lý do rồi chọn Áp dụng hoặc Bỏ qua.",
    "Tối ưu phần còn lại giữ các ô đã chỉnh làm khóa tạm.",
    "Có thể Hoàn tác các chỉnh sửa gần nhất trong phiên."
  ]},
  {id:"excel",group:"Xếp lịch",title:"Xuất Excel lịch",summary:"Excel luôn lấy đúng lịch hiện tại.",steps:[
    "Dock Excel luôn ở trong tầm tay trên PC và mobile.",
    "Bấm Kiểm tra & Xuất Excel.",
    "Nếu lịch có lỗi/cảnh báo nghiệp vụ, hệ thống vẫn cho xuất đúng lịch người dùng đang chọn.",
    "Optimizer không chạy lại lúc xuất.",
    "Nếu số người vượt số dòng template, tên dư được ghép vào ô cuối của ca thay vì chặn file."
  ]},
  {id:"hard-soft",group:"Khái niệm",title:"HARD và SOFT khác nhau thế nào?",summary:"HARD ràng buộc solver; SOFT là ưu tiên.",steps:[
    "HARD: solver không được vi phạm khi tạo/tối ưu phương án.",
    "SOFT: hệ thống cố gắng đáp ứng nhưng có thể bỏ qua để có lịch tổng thể tốt hơn.",
    "Mặc định QLKV của CHT có thể được người dùng sửa/xóa; giá trị hiện tại mới là rule được áp dụng."
  ]},
  {id:"off",group:"Khái niệm",title:"OFF và target tuần",summary:"Người có OFF không bị ép target đủ 7 ngày.",steps:[
    "OFF làm giảm số người khả dụng của ngày đó.",
    "Hệ thống cân lại nhu cầu ca theo số người còn làm.",
    "Nhân viên có OFF được loại khỏi penalty target đủ 7 ngày.",
    "Nếu bật Bù OFF → nhận hàng, hệ thống ưu tiên bù bằng nhận hàng ở ngày còn làm."
  ]},
]
const QUICK_START=["Chọn tuần","Kiểm tra nhân viên","Nhập OFF / nguyện vọng","Tạo lịch","Chỉnh lịch + xem gợi ý","Xuất Excel"]

const FAQ=[
  ["Vì sao lịch có cảnh báo nhưng vẫn xuất Excel được?","Cảnh báo giúp người dùng biết lịch chưa tối ưu hoặc đang vi phạm rule nghiệp vụ, nhưng quyền quyết định file cuối thuộc người dùng. Chỉ lỗi kỹ thuật làm workbook không thể dựng mới chặn export."],
  ["Vì sao chỉnh lịch rồi thống kê thay đổi?","Thống kê luôn tính theo assignments hiện tại sau mỗi lần chỉnh hoặc áp dụng gợi ý, không giữ số liệu của phương án ban đầu."],
  ["CTKM có cần admin không?","Không đối với thao tác vận hành cửa hàng như inspect CTKM/POG, chạy pipeline, preview/download, Tem R và kiểm tem. Preset dùng chung và queue/system vẫn cần admin."],
  ["Tối ưu phần còn lại có đổi ô tôi đã chỉnh không?","Không. Các ô đã chỉnh tay được chuyển thành khóa tạm trong lần tối ưu đó; hệ thống sắp phần còn lại xung quanh quyết định của bạn."],
]

const css=`
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#17202a;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.guide{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
.guide-hero{display:grid;grid-template-columns:1.3fr .7fr;gap:16px;align-items:stretch}
.hero-card,.guide-card,.faq-card{background:#fff;border:1px solid #e4e7ec;border-radius:16px;box-shadow:0 2px 10px rgba(16,24,40,.04)}
.hero-card{padding:24px}.hero-card h1{font-size:29px;margin:5px 0 7px;letter-spacing:-.7px}.hero-card p{margin:0;color:#667085;font-size:13px;line-height:1.6}
.guide-kicker{font-size:10px;font-weight:900;color:#175cd3;text-transform:uppercase;letter-spacing:.09em}
.search-card{padding:18px;display:flex;flex-direction:column;justify-content:center}.search-card label{font-size:11px;font-weight:850;margin-bottom:7px}.guide-search{width:100%;border:1px solid #d0d5dd;border-radius:10px;padding:11px 12px;font:12px inherit;outline:none}.guide-search:focus{border-color:#84adff;box-shadow:0 0 0 3px #eef4ff}
.quick-links{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.quick-link{color:#175cd3;background:#eff8ff;border:1px solid #b2ddff;text-decoration:none;padding:7px 9px;border-radius:8px;font-size:10px;font-weight:800}
.quick-start-panel{margin-top:14px;background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:18px}.quick-start-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.quick-start-head h2{margin:3px 0 0;font-size:17px}.quick-start-steps{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-top:13px}.quick-start-steps a{display:flex;align-items:center;gap:7px;padding:10px 8px;border:1px solid #e4e7ec;border-radius:10px;color:#344054;text-decoration:none;font-size:10px;font-weight:750}.quick-start-steps b{display:grid;place-items:center;min-width:20px;height:20px;border-radius:50%;background:#ecfdf3;color:#087f5b;font-size:9px}
.guide-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:14px;margin-top:14px}.guide-side{position:sticky;top:56px;align-self:start;background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:10px}.guide-side button{display:block;width:100%;border:0;background:transparent;text-align:left;padding:9px 10px;border-radius:8px;font:750 11px inherit;color:#475467;cursor:pointer}.guide-side button:hover,.guide-side button.active{background:#eef4ff;color:#175cd3}
.guide-results{display:grid;gap:10px}.guide-card{padding:18px}.guide-card h2{margin:3px 0 5px;font-size:16px}.guide-card p{margin:0;color:#667085;font-size:11px}.guide-group{font-size:9px;font-weight:900;color:#087f5b;text-transform:uppercase;letter-spacing:.07em}.guide-steps{margin:13px 0 0;padding:0;list-style:none;counter-reset:step}.guide-steps li{counter-increment:step;display:grid;grid-template-columns:25px 1fr;gap:8px;align-items:start;margin-top:7px;font-size:11px;line-height:1.5}.guide-steps li:before{content:counter(step);display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#eef4ff;color:#175cd3;font-size:9px;font-weight:900}.guide-notes{margin-top:10px;padding:10px 12px;border-radius:10px;background:#fffaeb;color:#946200;font-size:10px;line-height:1.55}.article-links{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.article-links a{padding:7px 10px;border-radius:8px;background:#175cd3;color:#fff;text-decoration:none;font-size:10px;font-weight:800}
.faq{margin-top:18px}.faq h2{font-size:18px}.faq-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.faq-card{padding:14px}.faq-card strong{font-size:11px}.faq-card p{margin:5px 0 0;font-size:10px;color:#667085;line-height:1.55}.empty-guide{padding:24px;text-align:center;background:#fff;border:1px dashed #d0d5dd;border-radius:14px;color:#667085;font-size:12px}
@media(max-width:760px){.quick-start-steps{grid-template-columns:1fr 1fr}.guide{padding:15px 10px 42px}.guide-hero{grid-template-columns:1fr}.hero-card{padding:18px}.hero-card h1{font-size:23px}.guide-layout{grid-template-columns:1fr}.guide-side{position:static;display:flex;overflow:auto;gap:4px;padding:7px}.guide-side button{width:auto;white-space:nowrap}.faq-grid{grid-template-columns:1fr}}
`

export default function GuideApp(){
  const [query,setQuery]=useState("")
  const [group,setGroup]=useState("Tất cả")
  const groups=useMemo(()=>["Tất cả",...new Set(ARTICLES.map(x=>x.group))],[])
  const results=useMemo(()=>{
    const q=query.trim().toLocaleLowerCase("vi")
    return ARTICLES.filter(article=>{
      if(group!=="Tất cả"&&article.group!==group)return false
      if(!q)return true
      return [article.title,article.summary,...article.steps,...(article.notes||[])].join(" ").toLocaleLowerCase("vi").includes(q)
    })
  },[query,group])
  return <><ProductNav current="guide"/><main className="guide"><style>{css}</style><style>{helpTipCss}</style>
    <section className="guide-hero">
      <div className="hero-card"><div className="guide-kicker">Trung tâm hướng dẫn</div><h1>Bạn đang muốn làm gì?</h1><p>Tìm nhanh đúng thao tác trong CTKM, Tem và Xếp lịch. Nội dung được chia theo module để sau này có thể thay đổi độc lập.</p><div className="quick-links"><a className="quick-link" href="/">CTKM / Tem</a><a className="quick-link" href="/schedule">Xếp lịch</a><a className="quick-link" href="/scan-tem">Kiểm tem</a><a className="quick-link" href="/scan-tem?mode=shelf">Kiểm theo kệ</a></div></div>
      <div className="hero-card search-card"><label htmlFor="guide-search">Tìm hướng dẫn</label><input id="guide-search" className="guide-search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Ví dụ: xuất Excel, nhân viên OFF, Tem R…"/><div style={{fontSize:10,color:"#98a2b3",marginTop:7}}>{results.length} bài phù hợp</div></div>
    </section>
    <section className="quick-start-panel" aria-labelledby="quick-start-title">
      <div className="quick-start-head"><div><div className="guide-kicker">Quick Start</div><h2 id="quick-start-title">Tạo lịch đầu tiên trong 6 bước</h2></div><HelpTip title="Quick Start" text={MODULE_HELP.schedule.quickStart}/></div>
      <div className="quick-start-steps">{QUICK_START.map((step,i)=><a key={step} href={i===5?"/guide#excel":"/schedule"}><b>{i+1}</b><span>{step}</span></a>)}</div>
    </section>
    <div className="guide-layout">
      <aside className="guide-side">{groups.map(x=><button key={x} className={group===x?"active":""} onClick={()=>setGroup(x)}>{x}</button>)}</aside>
      <section className="guide-results">{results.length?results.map(article=><article className="guide-card" key={article.id} id={article.id}><div className="guide-group">{article.group}</div><h2>{article.title}</h2><p>{article.summary}</p><ol className="guide-steps">{article.steps.map((step,i)=><li key={i}>{step}</li>)}</ol>{article.notes?.length>0&&<div className="guide-notes">{article.notes.map((x,i)=><div key={i}>• {x}</div>)}</div>}{article.links?.length>0&&<div className="article-links">{article.links.map(([label,href])=><a key={href} href={href}>{label}</a>)}</div>}</article>):<div className="empty-guide">Không tìm thấy hướng dẫn phù hợp. Thử từ khóa ngắn hơn.</div>}</section>
    </div>
    <section className="faq"><h2>Câu hỏi thường gặp</h2><div className="faq-grid">{FAQ.map(([q,a])=><div className="faq-card" key={q}><strong>{q}</strong><p>{a}</p></div>)}</div></section>
  </main></>
}
