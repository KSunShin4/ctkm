import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")

test("shared store shell prioritizes real store workflows and five mobile tabs",async()=>{
  const s=await read("./ProductNav.jsx")
  for(const x of ["Tổng quan","CTKM","Kiểm kệ","Tem R","Kiểm hạn dùng","portal-mobile-nav"])assert.match(s,new RegExp(x))
  for(const x of ["/overview","/?module=ctkm","/scan-tem?mode=shelf","/?module=temr","/?module=expiration"])assert.ok(s.includes(x))
  assert.match(s,/grid-template-columns:repeat\(5,1fr\)/)
})
test("legacy CTKM and scheduling screens keep shared navigation",async()=>{const app=await read("./App.jsx");assert.match(app,/ProductNav current=\{activeModule\}/);assert.doesNotMatch(app,/className="ops-tool-tabs"/);assert.match(await read("./SchedulingApp.jsx"),/ProductNav current="schedule"/)})
test("index routes shell modules and preserves CTKM root",async()=>{const s=await read("../index.html");for(const x of ["overview","guide","assistant","settings"])assert.ok(s.includes(`pathname.startsWith('/${x}')`));assert.ok(s.includes("import('/src/portal-main.jsx')"));assert.ok(s.includes("import('/src/main.jsx')"))})
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
