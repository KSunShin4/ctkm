import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"

const read=path=>readFile(new URL(path,import.meta.url),"utf8")

test("shared product navigation exposes the planned module shell",async()=>{
  const source=await read("./ProductNav.jsx")
  for(const label of ["CTKM / Tem","Xếp lịch","Hướng dẫn","Trợ lý"]) assert.match(source,new RegExp(label))
  for(const href of ["/schedule","/guide","/assistant"]) assert.match(source,new RegExp(href.replace("/","\\/")))
})

test("CTKM and scheduling screens mount the shared product navigation",async()=>{
  const app=await read("./App.jsx")
  const schedule=await read("./SchedulingApp.jsx")
  assert.match(app,/ProductNav current="ops"/)
  assert.match(schedule,/ProductNav current="schedule"/)
})

test("index routes guide and assistant to their independent module entrypoint",async()=>{
  const index=await read("../index.html")
  assert.match(index,/pathname\.startsWith\('\/guide'\)/)
  assert.match(index,/pathname\.startsWith\('\/assistant'\)/)
  assert.match(index,/import\('\/src\/portal-main\.jsx'\)/)
})
