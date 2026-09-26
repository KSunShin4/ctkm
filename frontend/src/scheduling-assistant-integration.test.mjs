import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("scheduling integrates shared help and assistant components",async()=>{const s=await read("./SchedulingApp.jsx");for(const x of ["HelpTip","MODULE_HELP","Mascot","GuideBubble","assistantComponentCss","helpTipCss"])assert.match(s,new RegExp(x))})
test("scheduling explains suggestion consent and hard soft semantics",async()=>{const s=await read("./SchedulingApp.jsx");assert.match(s,/Không có thay đổi nào xảy ra cho đến khi bạn bấm Áp dụng/);assert.match(s,/HARD là điều kiện bắt buộc/);assert.match(s,/SOFT là ưu tiên/);assert.match(s,/Hoàn tác/)})
test("integration preserves existing deterministic suggestion application",async()=>{const s=await read("./SchedulingApp.jsx");assert.match(s,/applySmartSuggestion/);assert.match(s,/onClick=\{\(\)=>applySuggestion\(s\)\}/);assert.doesNotMatch(s,/autoApply|applyAutomatically/)})
