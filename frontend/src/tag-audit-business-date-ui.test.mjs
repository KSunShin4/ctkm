import test from "node:test"
import assert from "node:assert/strict"

import {
  businessDateState,
  formatBusinessDate,
  staleBusinessDateMessage,
} from "./tag-audit-business-date-ui.js"

test("reads business date state from direct context payload", () => {
  assert.deepEqual(
    businessDateState({
      business_date_stale: true,
      business_date: "2026-09-05",
      scanner_business_date: "2026-09-06",
      report_month: "2026-09",
    }),
    {
      stale: true,
      businessDate: "2026-09-05",
      scannerBusinessDate: "2026-09-06",
      reportMonth: "2026-09",
    },
  )
})

test("reads business date state from nested scanner result context", () => {
  assert.equal(
    businessDateState({context:{business_date_stale:false,business_date:"2026-09-06"}})?.stale,
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

test("stale message includes both report date and current scanner date", () => {
  const message = staleBusinessDateMessage({
    stale: true,
    businessDate: "2026-09-05",
    scannerBusinessDate: "2026-09-06",
  })
  assert.match(message, /05\/09\/2026/)
  assert.match(message, /06\/09\/2026/)
  assert.match(message, /workbook CTKM mới/i)
})

test("current workbook produces no warning", () => {
  assert.equal(staleBusinessDateMessage({stale:false}), "")
})
