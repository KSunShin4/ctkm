import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"

const read=path=>readFile(new URL(path,import.meta.url),"utf8")

test("guide module covers current CTKM, Tem and scheduling workflows",async()=>{
  const source=await read("./GuideApp.jsx")
  for(const text of [
    "Tổng hợp CTKM",
    "Kiểm tem CTKM",
    "Phân bổ Tem R",
    "Tạo lịch tuần",
    "Chỉnh lịch và gợi ý thông minh",
    "Xuất Excel lịch",
    "HARD và SOFT",
    "OFF và target tuần",
  ]) assert.match(source,new RegExp(text))
})

test("guide exposes search, FAQ and direct module links",async()=>{
  const source=await read("./GuideApp.jsx")
  assert.match(source,/Tìm hướng dẫn/)
  assert.match(source,/Câu hỏi thường gặp/)
  assert.match(source,/href="\/schedule"/)
  assert.match(source,/href="\/scan-tem"/)
  assert.match(source,/mode=shelf/)
})

test("portal main renders GuideApp only for guide-side entrypoint",async()=>{
  const source=await read("./portal-main.jsx")
  assert.match(source,/import GuideApp/)
  assert.match(source,/path\.startsWith\("\/assistant"\)/)
  assert.match(source,/render\\(<GuideApp\\/>\\)/)
  assert.match(source,/UiPreferenceRoot/)
})
