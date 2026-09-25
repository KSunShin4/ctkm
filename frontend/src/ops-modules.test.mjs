import test from "node:test"
import assert from "node:assert/strict"
import { OPS_MODULES, guideForModule, hrefForModule, resolveRootView, visibleOpsModules } from "./ops-modules.js"

test("module registry keeps store tools available without admin",()=>{
  const ids=visibleOpsModules(false).map(item=>item.id)
  for(const id of ["ctkm","tag-audit","shelf","temr","expiration","guide","assistant"]){
    assert.ok(ids.includes(id), id)
  }
  assert.ok(!ids.includes("schedule"))
  assert.ok(visibleOpsModules(true).some(item=>item.id==="schedule"))
})

test("root view resolver only admits registered hub and legacy views",()=>{
  assert.equal(resolveRootView(""),"dashboard")
  assert.equal(resolveRootView("?view=ctkm"),"ctkm")
  assert.equal(resolveRootView("?view=guide"),"guide")
  assert.equal(resolveRootView("?view=unknown"),"dashboard")
})

test("module hrefs keep each workflow independent",()=>{
  const byId=Object.fromEntries(OPS_MODULES.map(item=>[item.id,item]))
  assert.equal(hrefForModule(byId.ctkm),"/?view=ctkm")
  assert.equal(hrefForModule(byId["tag-audit"]),"/scan-tem")
  assert.equal(hrefForModule(byId.schedule),"/schedule")
  assert.equal(hrefForModule(byId.dashboard),"/")
})

test("guide content is module-owned and can be changed independently",()=>{
  assert.ok(guideForModule("ctkm").length>=5)
  assert.ok(guideForModule("schedule").some(step=>step.includes("Xuất Excel")))
  assert.deepEqual(guideForModule("dashboard"),[])
})
