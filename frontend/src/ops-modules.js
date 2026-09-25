export const OPS_MODULES = [
  {id:"dashboard",label:"Tổng quan",icon:"⌂",kind:"hub",view:"dashboard",description:"Nhìn nhanh các công cụ và việc nên làm."},
  {id:"ctkm",label:"CTKM / Tem",icon:"🏷️",kind:"legacy",view:"ctkm",description:"Tổng hợp CTKM, POG, Clearance và xuất workbook."},
  {id:"tag-audit",label:"Kiểm tem",icon:"📷",kind:"link",href:"/scan-tem",description:"Quét và đối chiếu tem khuyến mãi tại kệ."},
  {id:"shelf",label:"Kiểm kệ",icon:"🧾",kind:"link",href:"/scan-tem?mode=shelf",description:"Kiểm Đúng/Sai theo từng action trên kệ."},
  {id:"temr",label:"Tem R",icon:"R",kind:"legacy",view:"temr",description:"Phân bổ Tem R theo vị trí và tồn kho."},
  {id:"expiration",label:"Hạn dùng",icon:"◷",kind:"legacy",view:"expiration",description:"Quét lô và đối chiếu hạn dùng."},
  {id:"schedule",label:"Xếp lịch",icon:"📅",kind:"link",href:"/schedule",adminOnly:true,description:"Tạo, chỉnh và tối ưu lịch làm việc."},
  {id:"guide",label:"Hướng dẫn",icon:"?",kind:"hub",view:"guide",description:"Bắt đầu nhanh và giải thích từng chức năng."},
  {id:"assistant",label:"Trợ lý",icon:"✦",kind:"hub",view:"assistant",description:"Gợi ý bước tiếp theo và dẫn tới đúng công cụ."},
]

export function visibleOpsModules(isAdmin=false){
  return OPS_MODULES.filter(module=>!module.adminOnly||isAdmin)
}

export function hrefForModule(module){
  if(module.href)return module.href
  if(module.kind==="legacy")return `/?view=${module.view}`
  return module.view==="dashboard"?"/":`/?view=${module.view}`
}

export function resolveRootView(search=""){
  const params=new URLSearchParams(search)
  const view=params.get("view")||"dashboard"
  const allowed=new Set(["dashboard","guide","assistant","ctkm","temr","expiration"])
  return allowed.has(view)?view:"dashboard"
}

export function guideForModule(id){
  const guides={
    ctkm:["Chọn file CTKM và POG","Kiểm tra đúng sheet","Chọn tháng báo cáo","Duyệt mapping nếu cần","Chạy pipeline và tải Excel"],
    "tag-audit":["Tải workbook kết quả CTKM","Mở camera","Đưa tem vào khung","Đọc kết quả Đúng/Sai","Đánh dấu tiến độ tại kệ"],
    temr:["Chọn file Tem R","Xác nhận cột tồn kho","Kiểm tra mapping","Chọn khoảng cách vị trí","Phân bổ và tải kết quả"],
    expiration:["Chọn file tồn/lô","Nhập hoặc quét mã","Kiểm tra kết quả","Lọc các dòng lệch","Xử lý sản phẩm cần kiểm tra"],
    schedule:["Chọn tuần và nhân viên","Nhập OFF/nguyện vọng","Tạo phương án","Chỉnh lịch và xem gợi ý","Kiểm tra & Xuất Excel"],
  }
  return guides[id]||[]
}
