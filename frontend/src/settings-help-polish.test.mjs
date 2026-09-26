import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("settings are local UI preferences only",async()=>{const s=await read("./SettingsApp.jsx");assert.match(s,/localStorage/);assert.match(s,/Không thay đổi rule CTKM, mapping, solver hay dữ liệu nguồn/);assert.doesNotMatch(s,/fetch\(/)})
test("settings expose safe reset and accessible toggles",async()=>{const s=await read("./SettingsApp.jsx");assert.match(s,/Khôi phục mặc định/);assert.match(s,/aria-pressed/)})
test("settings route is no longer a placeholder",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/SettingsApp/);assert.doesNotMatch(s,/PortalPlaceholderApp/)})
test("navigation marks active module accessibly on desktop and mobile",async()=>{const s=await read("./ProductNav.jsx");assert.equal((s.match(/aria-current/g)||[]).length,2)})
