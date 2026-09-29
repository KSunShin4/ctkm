import test from "node:test"
import assert from "node:assert/strict"
import {readFile,stat} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("assistant foundation exposes reusable components and real mascot states",async()=>{const s=await read("./assistant-components.jsx");for(const x of ["Mascot","AssistantCard","GuideBubble","EmptyState","idle","thinking","working","success","warning","guide","mascot-image"])assert.match(s,new RegExp(x));assert.doesNotMatch(s,/mascot-hair|mascot-face|mascot-body/)})
test("assistant components include responsive mobile rules",async()=>{const s=await read("./assistant-components.jsx");assert.match(s,/@media\(max-width:760px\)/);assert.match(s,/data-state/)})
test("assistant route renders component showcase without business actions",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/AssistantShowcase/);const d=await read("./AssistantShowcase.jsx");assert.match(d,/người dùng quyết định/i);assert.doesNotMatch(d,/fetch\(/)})


test("all five optimized mascot assets exist and are referenced",async()=>{const s=await read("./assistant-components.jsx");const names=["avatar","guide","working","warning","success"];for(const name of names){const rel=`../public/mascots/mascot-${name}.webp`;const info=await stat(new URL(rel,import.meta.url));assert.ok(info.size>1000);assert.ok(s.includes(`/mascots/mascot-${name}.webp`))}})
