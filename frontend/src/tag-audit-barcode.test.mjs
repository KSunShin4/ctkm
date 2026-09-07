import test from "node:test"
import assert from "node:assert/strict"

import {
  chooseBarcodeCandidate,
  normalizeBarcodeValue,
} from "./tag-audit-barcode.js"

test("rejects short false-positive barcode values", () => {
  assert.equal(normalizeBarcodeValue("14496"), "")
})

test("accepts 8 to 14 digit barcode values and strips formatting", () => {
  assert.equal(normalizeBarcodeValue("EAN 8938501432167"), "8938501432167")
  assert.equal(normalizeBarcodeValue("12345678"), "12345678")
})

test("rejects barcode values longer than 14 digits", () => {
  assert.equal(normalizeBarcodeValue("123456789012345"), "")
})

test("chooses the first valid barcode instead of falling back to an invalid detection", () => {
  const values = [
    {rawValue:"14496"},
    {rawValue:"8938501432167"},
  ]
  assert.equal(chooseBarcodeCandidate(values), "8938501432167")
})

test("returns empty when detector has no valid barcode", () => {
  assert.equal(chooseBarcodeCandidate([{rawValue:"14496"},{rawValue:"ABC"}]), "")
  assert.equal(chooseBarcodeCandidate([]), "")
  assert.equal(chooseBarcodeCandidate(null), "")
})
