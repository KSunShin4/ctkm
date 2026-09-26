import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("overview dashboard uses only existing jobs and queue APIs",async()=>{const s=await read("./OverviewDashboard.jsx");assert.match(s,/\/api\/jobs/);assert.match(s,/\/api\/queue\/status/);assert.doesNotMatch(s,/sales|doanh số|revenue/i)})
test("overview exposes operational status and module shortcuts",async()=>{const s=await read("./OverviewDashboard.jsx");for(const x of ["Job trong phiên","Hoàn tất","Cần chú ý","Đang chờ queue","Xếp lịch","CTKM / Tem","Hướng dẫn","Trợ lý"])assert.match(s,new RegExp(x))})
test("portal overview renders the real dashboard",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/OverviewDashboard/);assert.match(s,/root\.render\(<OverviewDashboard\/>\)/)})
