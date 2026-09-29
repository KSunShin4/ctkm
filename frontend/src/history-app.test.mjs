import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")

test("history reads only the public runtime job lifecycle endpoint",async()=>{
  const s=await read("./HistoryApp.jsx")
  assert.match(s,/\/api\/jobs/)
  assert.match(s,/job\.has_output/)
  assert.match(s,/\/api\/download\//)
  assert.doesNotMatch(s,/localStorage|sessionStorage/)
})

test("history is explicit that it is process-session history rather than permanent storage",async()=>{
  const s=await read("./HistoryApp.jsx")
  assert.match(s,/phiên Cloud Run hiện tại/)
  assert.match(s,/chưa phải kho lịch sử vĩnh viễn/)
})

test("history exposes real lifecycle filters and no fabricated business metrics",async()=>{
  const s=await read("./HistoryApp.jsx")
  for(const x of ["Tất cả","CTKM","Tem R","Cần chú ý","Hoàn tất","Đang xử lý / chờ","Lỗi"])assert.match(s,new RegExp(x))
  assert.match(s,/completed/)
  assert.match(s,/awaiting_mapping_confirmation/)
  assert.match(s,/failed/)
  assert.doesNotMatch(s,/doanh số|revenue|34%/i)
})
