import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")

test("overview uses existing jobs queue and health APIs without inventing sales data",async()=>{
  const s=await read("./OverviewDashboard.jsx")
  assert.match(s,/\/api\/jobs/)
  assert.match(s,/\/api\/queue\/status/)
  assert.match(s,/\/api\/health/)
  assert.doesNotMatch(s,/doanh số|revenue/i)
})

test("overview exposes the five store workflow cards and truthful status panels",async()=>{
  const s=await read("./OverviewDashboard.jsx")
  for(const x of ["CTKM","Kiểm kệ","Tem R","Kiểm tồn kho","Kiểm hạn dùng","Công việc gần đây","Bắt đầu nhanh","Trạng thái hệ thống"])assert.match(s,new RegExp(x))
  assert.match(s,/Tiến độ lưu trên thiết bị/)
  assert.match(s,/Không bịa tiến độ/)
})

test("overview does not render fake shelf percentages or decorative workload percentages",async()=>{
  const s=await read("./OverviewDashboard.jsx")
  assert.doesNotMatch(s,/width:34%/)
  assert.doesNotMatch(s,/conic-gradient/)
  assert.doesNotMatch(s,/Phân bố công việc/)
})

test("inventory card links to the real store-level inventory workspace",async()=>{
  const s=await read("./OverviewDashboard.jsx")
  assert.match(s,/Tồn store-level ↔ POG/)
  assert.match(s,/href="\/\?module=inventory"/)
  assert.doesNotMatch(s,/Đang nối dữ liệu thực|Sẽ mở ở FE-6/)
})

test("portal overview renders the real dashboard",async()=>{
  const s=await read("./portal-main.jsx")
  assert.match(s,/OverviewDashboard/)
  assert.match(s,/render\(<OverviewDashboard\/>\)/);assert.match(s,/UiPreferenceRoot/)
})
