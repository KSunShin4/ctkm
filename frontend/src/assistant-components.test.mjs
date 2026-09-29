import test from "node:test"
import assert from "node:assert/strict"
import {readFile,stat} from "node:fs/promises"
const read=p=>readFile(new URL(p,import.meta.url),"utf8")

test("assistant foundation exposes four reusable components and five mascot states",async()=>{
  const s=await read("./assistant-components.jsx")
  for(const x of ["Mascot","AssistantCard","GuideBubble","EmptyState","idle","thinking","success","warning","guide"])assert.match(s,new RegExp(x))
})

test("mascot states use real optimized anime assets instead of CSS-drawn faces",async()=>{
  const s=await read("./assistant-components.jsx")
  const mapping={
    idle:"/mascots/avatar.webp",
    thinking:"/mascots/working.webp",
    success:"/mascots/success.webp",
    warning:"/mascots/warning.webp",
    guide:"/mascots/guide.webp",
  }
  for(const [state,asset] of Object.entries(mapping)){
    assert.match(s,new RegExp(state))
    assert.ok(s.includes(asset))
  }
  assert.match(s,/className="mascot-image"/)
  assert.match(s,/alt=""/)
  assert.match(s,/decoding="async"/)
  assert.doesNotMatch(s,/mascot-hair|mascot-face|mascot-body|mascot-mark/)
})

test("all shipped mascot WebP assets stay lightweight",async()=>{
  for(const name of ["avatar","guide","working","warning","success"]){
    const info=await stat(new URL("../public/mascots/"+name+".webp",import.meta.url))
    assert.ok(info.size>0,name+" must not be empty")
    assert.ok(info.size<30000,name+" should remain under 30 KB")
  }
})

test("assistant components include responsive mobile rules",async()=>{
  const s=await read("./assistant-components.jsx")
  assert.match(s,/@media\(max-width:760px\)/)
  assert.match(s,/data-state/)
})

test("assistant route renders component showcase without business actions",async()=>{
  const s=await read("./portal-main.jsx")
  assert.match(s,/AssistantShowcase/)
  const d=await read("./AssistantShowcase.jsx")
  assert.match(d,/người dùng quyết định/i)
  assert.doesNotMatch(d,/fetch\(/)
})
