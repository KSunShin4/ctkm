import test from "node:test"
import assert from "node:assert/strict"

import {
  firstUncheckedIndex,
  markResolved,
  progressStats,
  recordDecision,
  shelfStats,
} from "./tag-audit-shelf-progress.js"

const items = [
  {check_key:"a", shelf_key:"S1"},
  {check_key:"b", shelf_key:"S1"},
  {check_key:"c", shelf_key:"S2"},
]

test("progress stats count action-level decisions", () => {
  const progress = {
    a:{state:"pass"},
    b:{state:"fail",reason:"Sai giá"},
  }
  assert.deepEqual(progressStats(items, progress), {
    total:3, checked:2, remaining:1, pass:1, fail:1, review:0,
  })
  assert.deepEqual(shelfStats(items, progress, "S1"), {
    total:2, checked:2, remaining:0, pass:1, fail:1, review:0,
  })
})

test("first unchecked resumes inside current shelf", () => {
  const progress = {a:{state:"pass"}}
  assert.equal(firstUncheckedIndex(items.slice(0,2), progress), 1)
  assert.equal(firstUncheckedIndex(items.slice(0,2), {a:{state:"pass"},b:{state:"fail"}}), -1)
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

test("failed action can be marked resolved without changing verdict", () => {
  const progress = {b:{state:"fail",reason:"Sai giá",checkedAt:"x",resolved:false}}
  const resolved = markResolved(progress, "b", true)
  assert.equal(resolved.b.state, "fail")
  assert.equal(resolved.b.resolved, true)
})
