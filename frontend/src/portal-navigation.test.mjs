import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")

test("shared store shell keeps four primary mobile tabs plus a More sheet",async()=>{
  const s=await read("./ProductNav.jsx")
  for(const x of ["Tổng quan","CTKM","Kiểm kệ","Tem R","Kiểm tồn kho","Kiểm hạn dùng","Xếp lịch","Lịch sử","Hướng dẫn","Cài đặt","portal-mobile-nav","portal-mobile-more-sheet"])assert.match(s,new RegExp(x))
  for(const x of ["/overview","/?module=ctkm","/scan-tem?mode=shelf","/?module=temr","/?module=inventory","/?module=expiration","/schedule","/history","/guide","/settings"])assert.ok(s.includes(x))
  assert.match(s,/grid-template-columns:repeat\(5,1fr\)/)
  assert.match(s,/mobilePrimary/)
  assert.match(s,/mobileMore/)
  assert.match(s,/>Thêm</)
})
test("legacy CTKM and scheduling screens keep shared navigation",async()=>{const app=await read("./App.jsx");assert.match(app,/ProductNav current=\{activeModule\}/);assert.doesNotMatch(app,/className="ops-tool-tabs"/);assert.match(await read("./SchedulingApp.jsx"),/ProductNav current="schedule"/)})
test("index routes shell modules and preserves CTKM root",async()=>{const s=await read("../index.html");for(const x of ["overview","history","guide","assistant","settings"])assert.ok(s.includes(`pathname.startsWith('/${x}')`));assert.ok(s.includes("import('/src/portal-main.jsx')"));assert.ok(s.includes("import('/src/main.jsx')"))})
test("ctkm root keeps approved workspace and relies on the shared vertical module navigation",async()=>{
  const app=await read("./App.jsx")
  const nav=await read("./ProductNav.jsx")
  assert.match(app,/ops-page-head/);assert.match(app,/ops-hero/)
  assert.match(app,/URLSearchParams\(window\.location\.search\)/)
  assert.match(app,/ProductNav current=\{activeModule\}/)
  assert.doesNotMatch(app,/<nav className="ops-tool-tabs"/)
  assert.doesNotMatch(app,/<div className="topbar">/);assert.doesNotMatch(app,/<nav className="module-nav"/)
  for(const x of ["CTKM","Kiểm kệ","Tem R","Kiểm tồn kho","Kiểm hạn dùng"])assert.match(nav,new RegExp(x))
})
test("ctkm root installs the same UI preference root as portal pages",async()=>{const main=await read("./main.jsx");assert.match(main,/UiPreferenceRoot/);assert.match(main,/uiPreferenceCss/)})


test("ctkm operational workspace prioritizes action sheets without deleting audit sheets",async()=>{
  const app=await read("./App.jsx")
  for(const x of ["CTKM_OPERATIONAL_SHEETS","TỔNG HỢP - TEM","Gắn tem","Tháo tem","Chờ gắn","Cần review","Dữ liệu khác / audit","Kiểm theo kệ"])assert.match(app,new RegExp(x))
  assert.match(app,/Tìm mã SP, tên sản phẩm, kệ, channel/)
  assert.match(app,/Tìm kiếm chỉ thay đổi hiển thị, không thay đổi workbook/)
})

test("shelf workflow uses shared shell and keeps camera explicitly beta",async()=>{
  const shelf=await read("./TagAuditShelfCheck.jsx")
  assert.match(shelf,/ProductNav current="shelf"/)
  assert.match(shelf,/Quét nhanh \(Beta\)/)
  assert.match(shelf,/chỉ hỗ trợ tìm\/đọc tem/)
  assert.match(shelf,/Sai & Review/)
})


test("inventory is a first-class desktop module backed by real inspection",async()=>{
  const nav=await read("./ProductNav.jsx")
  const app=await read("./App.jsx")
  assert.match(nav,/Kiểm tồn kho/)
  assert.match(nav,/\?module=inventory/)
  assert.match(app,/\/api\/inspect-inventory/)
  assert.match(app,/Tồn store-level ↔ vị trí POG/)
  assert.match(app,/stock_conflict/)
  assert.match(app,/Không cộng tồn lặp/)
})


test("final pastel theme overrides legacy shell styles instead of being overwritten",async()=>{
  const app=await read("./App.jsx")
  const finalTheme=app.lastIndexOf("FINAL THEME OVERRIDES")
  const legacyTheme=app.lastIndexOf("Approved mockup alignment: one shared PharmaOps shell")
  assert.ok(finalTheme>legacyTheme)
  assert.match(app,/temr-head/)
  assert.match(app,/temr-rule-row/)
  assert.match(app,/inventory-title-wrap/)
  assert.match(app,/main\.temr-mode/)
  assert.match(app,/main\.inventory-mode/)
})

test("Tem R and inventory redesign keeps existing deterministic data paths",async()=>{
  const app=await read("./App.jsx")
  assert.match(app,/handleTemR/)
  assert.match(app,/handleInventoryInspect/)
  assert.match(app,/\/api\/inspect-inventory/)
  assert.match(app,/temRStockColumn/)
  assert.match(app,/stock_conflict/)
  assert.match(app,/Không cộng tồn lặp/)
})


test("expiration workspace matches pastel module language without changing checker semantics",async()=>{
  const app=await read("./App.jsx")
  for(const x of ["expiration-title-wrap","expiration-rule-row","expiration-source-panel","expiration-entry-panel","expiration-stats"])assert.match(app,new RegExp(x))
  assert.match(app,/MÃ_P;SỐ_LÔ;DD\/MM\/YYYY/)
  assert.match(app,/handleExpirationCheck/)
  assert.match(app,/Camera chỉ hỗ trợ nhập mã nhanh/)
  assert.match(app,/expirationResult\.matched/)
  assert.match(app,/expirationResult\.unmatched/)
})


test("mobile More sheet exposes inventory and expiration instead of dropping store features",async()=>{
  const s=await read("./ProductNav.jsx")
  assert.match(s,/\["inventory","expiration","schedule","history","guide","settings"\]/)
  assert.match(s,/aria-expanded=\{moreOpen\}/)
  assert.match(s,/Thêm chức năng/)
  assert.match(s,/moreActive/)
})


test("admin login is compact by default and keeps the existing auth contract",async()=>{
  const app=await read("./App.jsx")
  assert.match(app,/adminPanelOpen/)
  assert.match(app,/admin-trigger/)
  assert.match(app,/auth-popover/)
  assert.match(app,/loginAdmin/)
  assert.match(app,/logoutAdmin/)
  assert.match(app,/className="admin-pill">ADMIN/)
  assert.doesNotMatch(app,/<form className="auth-actions" onSubmit=\{loginAdmin\}>/)
})

test("CTKM running error and download states keep the approved pastel language",async()=>{
  const app=await read("./App.jsx")
  for(const x of ["pipeline-state-card","pipeline-state-list","pipeline-step-list","pipeline-error-message","download-bar-polished"]) {
    if(x==="pipeline-state-list") continue
    assert.match(app,new RegExp(x))
  }
  assert.match(app,/queueHasWaiting/)
  assert.match(app,/STEP_LABELS\.map/)
  assert.match(app,/handleDownload/)
  assert.match(app,/Quay lại và thử lại/)
})


test("history is a first-class portal module and mobile More destination",async()=>{
  const nav=await read("./ProductNav.jsx")
  const portal=await read("./portal-main.jsx")
  const index=await read("../index.html")
  assert.match(nav,/id:"history"/)
  assert.match(nav,/href:"\/history"/)
  assert.match(nav,/startsWith\("\/history"\)/)
  assert.match(portal,/HistoryApp/)
  assert.match(portal,/startsWith\("\/history"\)/)
  assert.match(index,/pathname\.startsWith\('\/history'\)/)
})


test("scheduling uses the shared sidebar without a duplicate horizontal topbar",async()=>{
  const s=await read("./SchedulingApp.jsx")
  assert.match(s,/ProductNav current="schedule"/)
  assert.match(s,/schedule-hero/)
  assert.match(s,/schedule-flow/)
  assert.match(s,/XẾP LỊCH NHÂN VIÊN/)
  assert.doesNotMatch(s,/<header className="sched-top"/)
  assert.match(s,/export-dock/)
  assert.match(s,/generate/)
  assert.match(s,/exportExcel/)
})

test("settings keeps local-only preferences while matching the shared pastel shell",async()=>{
  const s=await read("./SettingsApp.jsx")
  assert.match(s,/settings-hero/)
  assert.match(s,/settings-grid/)
  assert.match(s,/Mascot/)
  assert.match(s,/localStorage/)
  assert.match(s,/readUiPreferences/)
  assert.match(s,/writeUiPreferences/)
  assert.match(s,/DEFAULT_UI_PREFERENCES/)
  assert.doesNotMatch(s,/fetch\(/)
})
