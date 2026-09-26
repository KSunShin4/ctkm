import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("shared app shell exposes six modules and mobile navigation",async()=>{const s=await read("./ProductNav.jsx");for(const x of ["Tổng quan","Xếp lịch","CTKM / Tem","Hướng dẫn","Trợ lý","Cài đặt","portal-mobile-nav"])assert.match(s,new RegExp(x));for(const x of ["/overview","/schedule","/guide","/assistant","/settings"])assert.ok(s.includes(x))})
test("legacy CTKM and scheduling screens keep shared navigation",async()=>{assert.match(await read("./App.jsx"),/ProductNav current="ops"/);assert.match(await read("./SchedulingApp.jsx"),/ProductNav current="schedule"/)})
test("index routes shell modules and preserves CTKM root",async()=>{const s=await read("../index.html");for(const x of ["overview","guide","assistant","settings"])assert.ok(s.includes(`pathname.startsWith('/${x}')`));assert.ok(s.includes("import('/src/portal-main.jsx')"));assert.ok(s.includes("import('/src/main.jsx')"))})
