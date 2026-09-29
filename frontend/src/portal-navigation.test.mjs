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
test("legacy CTKM and scheduling screens keep shared navigation",async()=>{assert.match(await read("./App.jsx"),/ProductNav current="ops"/);assert.match(await read("./SchedulingApp.jsx"),/ProductNav current="schedule"/)})
test("index routes shell modules and preserves CTKM root",async()=>{const s=await read("../index.html");for(const x of ["overview","guide","assistant","settings"])assert.ok(s.includes(`pathname.startsWith('/${x}')`));assert.ok(s.includes("import('/src/portal-main.jsx')"));assert.ok(s.includes("import('/src/main.jsx')"))})
test("ctkm root keeps approved workspace and supports deep links into real tools",async()=>{
  const app=await read("./App.jsx")
  assert.match(app,/ops-page-head/);assert.match(app,/ops-hero/);assert.match(app,/ops-tool-tabs/)
  assert.match(app,/Tổng hợp CTKM/);assert.match(app,/Kiểm hạn dùng/);assert.match(app,/Phân bổ Tem R/);assert.match(app,/Kiểm theo kệ/)
  assert.match(app,/URLSearchParams\(window\.location\.search\)/)
  assert.doesNotMatch(app,/<div className="topbar">/);assert.doesNotMatch(app,/<nav className="module-nav"/)
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
