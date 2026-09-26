import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("help foundation defines module-scoped contextual help",async()=>{const s=await read("./help-foundation.jsx");for(const x of ["overview","schedule","ops","guide","assistant","settings","HelpTip","role=\"tooltip\""])assert.match(s,new RegExp(x))})
test("guide quick start follows the six-step operating flow",async()=>{const s=await read("./GuideApp.jsx");for(const x of ["Chọn tuần","Kiểm tra nhân viên","Nhập OFF / nguyện vọng","Tạo lịch","Chỉnh lịch + xem gợi ý","Xuất Excel"])assert.match(s,new RegExp(x.replace("+","\\+")))})
