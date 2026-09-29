import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("overview uses existing jobs queue and health APIs without inventing sales data",async()=>{const s=await read("./OverviewDashboard.jsx");assert.match(s,/\/api\/jobs/);assert.match(s,/\/api\/queue\/status/);assert.match(s,/\/api\/health/);assert.doesNotMatch(s,/doanh số|revenue/i)})
test("overview exposes store workflow cards",async()=>{const s=await read("./OverviewDashboard.jsx");for(const x of ["CTKM","Kiểm kệ","Tem R","Kiểm tồn kho","Kiểm hạn dùng","Công việc gần đây","Ưu tiên kiểm kệ"])assert.match(s,new RegExp(x))})
test("inventory card is explicit about not being wired yet",async()=>{const s=await read("./OverviewDashboard.jsx");assert.match(s,/Đang nối dữ liệu thực/);assert.match(s,/Sẽ mở ở FE-6/)})
test("portal overview renders the real dashboard",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/OverviewDashboard/);assert.match(s,/root\.render\(<OverviewDashboard\/>\)/)})
