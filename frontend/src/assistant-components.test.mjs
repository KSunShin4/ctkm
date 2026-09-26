import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")
test("assistant foundation exposes four reusable components and five mascot states",async()=>{const s=await read("./assistant-components.jsx");for(const x of ["Mascot","AssistantCard","GuideBubble","EmptyState","idle","thinking","success","warning","guide"])assert.match(s,new RegExp(x))})
test("assistant components include responsive mobile rules",async()=>{const s=await read("./assistant-components.jsx");assert.match(s,/@media\(max-width:760px\)/);assert.match(s,/data-state/)})
test("assistant route renders component showcase without business actions",async()=>{const s=await read("./portal-main.jsx");assert.match(s,/AssistantShowcase/);const d=await read("./AssistantShowcase.jsx");assert.match(d,/người dùng quyết định/i);assert.doesNotMatch(d,/fetch\(/)})
