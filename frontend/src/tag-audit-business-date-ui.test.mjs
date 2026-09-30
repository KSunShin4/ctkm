import test from "node:test"
import assert from "node:assert/strict"

import {
  businessDateState,
  formatBusinessDate,
  staleBusinessDateMessage,
} from "./tag-audit-business-date-ui.js"

test("same-month old report date is informative but does not gate scanner", () => {
  const state = businessDateState({
    business_date_stale: true,
    business_date_blocked: false,
    scanner_reclassifies_actions: true,
    business_date: "2026-09-05",
    scanner_business_date: "2026-09-06",
    report_month: "2026-09",
  })
  assert.equal(state.stale, false)
  assert.equal(state.blocked, false)
  assert.equal(state.reportDateStale, true)
  assert.equal(state.reclassifiesActions, true)
  assert.equal(state.businessDate, "2026-09-05")
  assert.equal(state.scannerBusinessDate, "2026-09-06")
  assert.equal(state.reportMonth, "2026-09")
})

test("known incompatible report month gates scanner", () => {
  const state = businessDateState({
    business_date_stale: true,
    business_date_blocked: true,
    business_date: "2026-08-31",
    scanner_business_date: "2026-09-06",
    report_month: "2026-08",
  })
  assert.equal(state.stale, true)
  assert.equal(state.blocked, true)
})

test("reads business date state from nested scanner result context", () => {
  assert.equal(
    businessDateState({context:{business_date_stale:false,business_date_blocked:false,business_date:"2026-09-06"}})?.stale,
    false,
  )
})

test("ignores unrelated API payloads", () => {
  assert.equal(businessDateState({ready:true,item_count:3}), null)
})

test("formats ISO business dates for store-facing Vietnamese UI", () => {
  assert.equal(formatBusinessDate("2026-09-05"), "05/09/2026")
  assert.equal(formatBusinessDate("not-a-date"), "not-a-date")
})

test("same-month old workbook message says no daily rerun is needed", () => {
  const message = staleBusinessDateMessage({
    stale: false,
    blocked: false,
    reportDateStale: true,
    businessDate: "2026-09-05",
    scannerBusinessDate: "2026-09-06",
  })
  assert.match(message, /05\/09\/2026/)
  assert.match(message, /06\/09\/2026/)
  assert.match(message, /Không cần chạy lại workbook mỗi ngày/i)
})

test("incompatible month message still requires correct workbook", () => {
  const message = staleBusinessDateMessage({
    stale: true,
    blocked: true,
    reportDateStale: true,
    reportMonth: "2026-08",
    scannerBusinessDate: "2026-09-06",
  })
  assert.match(message, /2026-08/)
  assert.match(message, /đúng tháng/i)
})

test("current workbook produces no warning", () => {
  assert.equal(staleBusinessDateMessage({stale:false,blocked:false,reportDateStale:false}), "")
})


test("missing report metadata produces a fail-closed scanner message", () => {
  const state = businessDateState({
    business_date_stale: false,
    business_date_blocked: true,
    business_date_block_reason: "missing_report_metadata",
    scanner_reclassifies_actions: false,
  })
  assert.equal(state.blocked, true)
  assert.equal(state.blockReason, "missing_report_metadata")
  assert.match(staleBusinessDateMessage(state), /thiếu metadata/i)
  assert.match(staleBusinessDateMessage(state), /do hệ thống xuất/i)
})
