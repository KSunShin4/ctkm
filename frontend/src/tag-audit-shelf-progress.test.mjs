import test from "node:test"
import assert from "node:assert/strict"

import {
  firstUncheckedIndex,
  markExtraResolved,
  markResolved,
  progressStats,
  recordDecision,
  recordRemovalDecision,
  resetProgressForItems,
  resetRemovalToday,
  resetRemovalTodayForItems,
  shelfStats,
} from "./tag-audit-shelf-progress.js"

const items = [
  {check_key:"a", task_key:"a", shelf_key:"S1", expected_action:"gan_tem"},
  {check_key:"b", task_key:"b", shelf_key:"S1", expected_action:"gan_tem"},
  {check_key:"c", task_key:"c", shelf_key:"S2", expected_action:"gan_tem"},
]

function baseExpected(total, checked, remaining, pass, fail, review) {
  return {
    total, checked, remaining, pass, fail, review,
    attachTotal:total, removeTotal:0, removed:0, removePending:0,
    removeStillPresent:0, removeNotFound:0,
  }
}

test("progress stats count action-level decisions", () => {
  const progress = {
    a:{state:"pass"},
    b:{state:"fail",reason:"Sai giá"},
  }
  assert.deepEqual(progressStats(items, progress), baseExpected(3,2,1,1,1,0))
  assert.deepEqual(shelfStats(items, progress, "S1"), baseExpected(2,2,0,1,1,0))
})

test("removal progress persists removed state and only counts unresolved checks on the same day", () => {
  const removalItems = [
    {check_key:"r1",removal_key:"rm1",shelf_key:"S1",expected_action:"thao_tem"},
    {check_key:"r2",removal_key:"rm2",shelf_key:"S1",expected_action:"thao_tem"},
    {check_key:"r3",removal_key:"rm3",shelf_key:"S1",expected_action:"thao_tem"},
  ]
  const removal = {
    rm1:{state:"removed",checkedAt:"2026-09-07T01:00:00.000Z"},
    rm2:{state:"still_present",checkedAt:"2026-09-08T01:00:00.000Z"},
    rm3:{state:"not_found",checkedAt:"2026-09-07T01:00:00.000Z"},
  }
  const stats = progressStats(removalItems, {}, removal, "2026-09-08")
  assert.deepEqual(stats, {
    total:3,checked:2,remaining:1,pass:1,fail:1,review:0,
    attachTotal:0,removeTotal:3,removed:1,removePending:2,
    removeStillPresent:1,removeNotFound:0,
  })
})

test("first unchecked resumes active and removal tasks correctly", () => {
  assert.equal(firstUncheckedIndex(items.slice(0,2), {a:{state:"pass"}}), 1)
  assert.equal(firstUncheckedIndex(items.slice(0,2), {a:{state:"pass"},b:{state:"fail"}}), -1)

  const removalItems = [
    {removal_key:"r1",expected_action:"thao_tem"},
    {removal_key:"r2",expected_action:"thao_tem"},
  ]
  const removal = {
    r1:{state:"removed",checkedAt:"2026-09-07T01:00:00.000Z"},
    r2:{state:"still_present",checkedAt:"2026-09-08T01:00:00.000Z"},
  }
  assert.equal(firstUncheckedIndex(removalItems, {}, 0, removal, "2026-09-08"), -1)
  assert.equal(firstUncheckedIndex(removalItems, {}, 0, removal, "2026-09-09"), 1)
})

test("record decision stores fail reason and pass clears reason", () => {
  const when = new Date("2026-09-07T12:00:00.000Z")
  let progress = recordDecision({}, "b", "fail", "Sai ngày", "tem 06/09-12/09", when)
  assert.equal(progress.b.state, "fail")
  assert.equal(progress.b.reason, "Sai ngày")
  assert.equal(progress.b.note, "tem 06/09-12/09")
  assert.equal(progress.b.checkedAt, "2026-09-07T12:00:00.000Z")
  progress = recordDecision(progress, "b", "pass", "Sai ngày", "đã thay", when)
  assert.equal(progress.b.state, "pass")
  assert.equal(progress.b.reason, "")
})

test("record removal decision distinguishes removed still-present and not-found", () => {
  const when = new Date("2026-09-08T02:00:00.000Z")
  let removal = recordRemovalDecision({}, "r", "still_present", "chưa tháo", when)
  assert.equal(removal.r.state, "still_present")
  assert.equal(removal.r.note, "chưa tháo")
  removal = recordRemovalDecision(removal, "r", "removed", "đã xử lý", when)
  assert.equal(removal.r.state, "removed")
})

test("reset today preserves confirmed removals but clears unresolved removal observations", () => {
  const removal = {
    r1:{state:"removed",checkedAt:"2026-09-08T01:00:00.000Z"},
    r2:{state:"still_present",checkedAt:"2026-09-08T01:00:00.000Z"},
    r3:{state:"not_found",checkedAt:"2026-09-07T01:00:00.000Z"},
  }
  const reset = resetRemovalToday(removal, "2026-09-08")
  assert.equal(reset.r1.state, "removed")
  assert.equal(reset.r2, undefined)
  assert.equal(reset.r3.state, "not_found")
})

test("reset one shelf clears its normal progress and today's unresolved removal only", () => {
  const target = [
    {check_key:"a",expected_action:"gan_tem"},
    {removal_key:"r1",expected_action:"thao_tem"},
    {removal_key:"r2",expected_action:"thao_tem"},
  ]
  const progress = {a:{state:"pass"},other:{state:"pass"}}
  const removal = {
    r1:{state:"removed",checkedAt:"2026-09-08T01:00:00.000Z"},
    r2:{state:"still_present",checkedAt:"2026-09-08T01:00:00.000Z"},
    other:{state:"still_present",checkedAt:"2026-09-08T01:00:00.000Z"},
  }
  assert.deepEqual(resetProgressForItems(progress,target), {other:{state:"pass",reason:"",note:"",checkedAt:"",resolved:false}})
  const resetRemoval = resetRemovalTodayForItems(removal,target,"2026-09-08")
  assert.equal(resetRemoval.r1.state,"removed")
  assert.equal(resetRemoval.r2,undefined)
  assert.equal(resetRemoval.other.state,"still_present")
})

test("failed action can be marked resolved without changing verdict", () => {
  const progress = {b:{state:"fail",reason:"Sai giá",checkedAt:"x",resolved:false}}
  const resolved = markResolved(progress, "b", true)
  assert.equal(resolved.b.state, "fail")
  assert.equal(resolved.b.resolved, true)
})

test("extra-tag report can be marked resolved without deleting evidence", () => {
  const extra = [{id:"x",item_id:"P1",resolved:false}]
  const resolved = markExtraResolved(extra,"x",true)
  assert.equal(resolved[0].id,"x")
  assert.equal(resolved[0].resolved,true)
})
