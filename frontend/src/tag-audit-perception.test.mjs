import test from "node:test"
import assert from "node:assert/strict"
import {
  HAPTIC_PATTERNS,
  confidencePercent,
  perceptionSummary,
  resolveHapticPattern,
  triggerHapticFeedback,
} from "./tag-audit-perception.js"

test("perceptionSummary formats engine, confidence, barcodeSource, and warnings", () => {
  const result = {
    observed: {
      ocr_engine: "rapidocr",
      confidence: 0.92,
      barcode_source: "zxingcpp",
      barcode_candidates: ["8935001234567"],
      image_quality: {
        warnings: [{ code: "glare", message: "Tem có vùng lóa" }],
      },
      image_quality_warning: "Phơi sáng cao",
      barcode_warning: "Chỉ tìm thấy 1 barcode",
    },
  }

  const summary = perceptionSummary(result)
  assert.equal(summary.engine, "RapidOCR")
  assert.equal(summary.confidence, 0.92)
  assert.equal(summary.barcodeSource, "ZXing")
  assert.deepEqual(summary.barcodeCandidates, ["8935001234567"])
  assert.equal(summary.barcodeWarning, "Chỉ tìm thấy 1 barcode")
  assert.equal(summary.warnings.length, 2)
  assert.equal(summary.warnings[0].code, "glare")
  assert.equal(summary.warnings[1].code, "image_preprocessor_error")
})

test("perceptionSummary handles browser barcode and fallback engines", () => {
  const result = {
    observed: {
      ocr_engine: "rapidocr+gemini",
      confidence: "0.85",
      barcode_source: "ocr",
    },
  }

  const summaryWithBrowser = perceptionSummary(result, "8935001234567")
  assert.equal(summaryWithBrowser.engine, "RapidOCR + Gemini fallback")
  assert.equal(summaryWithBrowser.barcodeSource, "Camera trình duyệt")

  const summaryWithoutBrowser = perceptionSummary(result, "")
  assert.equal(summaryWithoutBrowser.barcodeSource, "OCR")
})

test("confidencePercent safely normalizes and clamps confidence values", () => {
  assert.equal(confidencePercent(0.854), 85)
  assert.equal(confidencePercent(1.0), 100)
  assert.equal(confidencePercent(0), 0)
  assert.equal(confidencePercent(-0.1), 0)
  assert.equal(confidencePercent(1.5), 100)
  assert.equal(confidencePercent(null), null)
  assert.equal(confidencePercent(undefined), null)
  assert.equal(confidencePercent("abc"), null)
})

test("HAPTIC_PATTERNS defines immutable vibration rhythms", () => {
  assert.deepEqual(Array.from(HAPTIC_PATTERNS.pass), [40])
  assert.deepEqual(Array.from(HAPTIC_PATTERNS.review), [50, 60, 50])
  assert.deepEqual(Array.from(HAPTIC_PATTERNS.ambiguous), [50, 60, 50])
  assert.deepEqual(Array.from(HAPTIC_PATTERNS.fail), [120, 80, 120])
})

test("resolveHapticPattern maps string and object verdicts to expected patterns", () => {
  // PASS mappings
  assert.deepEqual(resolveHapticPattern("PASS"), HAPTIC_PATTERNS.pass)
  assert.deepEqual(resolveHapticPattern("pass"), HAPTIC_PATTERNS.pass)
  assert.deepEqual(resolveHapticPattern("success"), HAPTIC_PATTERNS.pass)
  assert.deepEqual(resolveHapticPattern({ code: "PASS", severity: "success" }), HAPTIC_PATTERNS.pass)
  assert.deepEqual(resolveHapticPattern({ severity: "success" }), HAPTIC_PATTERNS.pass)
  assert.deepEqual(resolveHapticPattern({ verdict: { code: "PASS" } }), HAPTIC_PATTERNS.pass)

  // FAIL mappings
  assert.deepEqual(resolveHapticPattern("FAIL"), HAPTIC_PATTERNS.fail)
  assert.deepEqual(resolveHapticPattern("fail"), HAPTIC_PATTERNS.fail)
  assert.deepEqual(resolveHapticPattern("error"), HAPTIC_PATTERNS.fail)
  assert.deepEqual(resolveHapticPattern({ code: "FAIL", severity: "error" }), HAPTIC_PATTERNS.fail)
  assert.deepEqual(resolveHapticPattern({ verdict: { severity: "error" } }), HAPTIC_PATTERNS.fail)

  // REVIEW / AMBIGUOUS mappings
  assert.deepEqual(resolveHapticPattern("REVIEW"), HAPTIC_PATTERNS.review)
  assert.deepEqual(resolveHapticPattern("review"), HAPTIC_PATTERNS.review)
  assert.deepEqual(resolveHapticPattern("ambiguous"), HAPTIC_PATTERNS.review)
  assert.deepEqual(resolveHapticPattern({ code: "REVIEW", severity: "warn" }), HAPTIC_PATTERNS.review)
  assert.deepEqual(resolveHapticPattern({ progress_state: "review" }), HAPTIC_PATTERNS.review)

  // Edge cases
  assert.equal(resolveHapticPattern(null), null)
  assert.equal(resolveHapticPattern(undefined), null)
  assert.equal(resolveHapticPattern(""), null)
  assert.equal(resolveHapticPattern({}), null)
})

test("triggerHapticFeedback is safe in environments without navigator.vibrate", () => {
  // Node.js test runner has no navigator or navigator.vibrate
  assert.equal(triggerHapticFeedback("PASS"), false)
  assert.equal(triggerHapticFeedback("FAIL"), false)
  assert.equal(triggerHapticFeedback(null), false)

  // Navigator without vibrate method
  const dummyNav = {}
  assert.equal(triggerHapticFeedback("PASS", { navigator: dummyNav }), false)

  // Disabled in options
  assert.equal(triggerHapticFeedback("PASS", { enabled: false }), false)
})

test("triggerHapticFeedback calls navigator.vibrate with correct pattern and handles errors safely", () => {
  const calls = []
  const mockNavigator = {
    vibrate(pattern) {
      calls.push(pattern)
      return true
    },
  }

  // Trigger PASS
  const resPass = triggerHapticFeedback("PASS", { navigator: mockNavigator })
  assert.equal(resPass, true)
  assert.deepEqual(calls[0], HAPTIC_PATTERNS.pass)

  // Trigger REVIEW
  const resReview = triggerHapticFeedback("REVIEW", { navigator: mockNavigator })
  assert.equal(resReview, true)
  assert.deepEqual(calls[1], HAPTIC_PATTERNS.review)

  // Trigger FAIL
  const resFail = triggerHapticFeedback("FAIL", { navigator: mockNavigator })
  assert.equal(resFail, true)
  assert.deepEqual(calls[2], HAPTIC_PATTERNS.fail)

  // When vibrate throws an error (e.g. user gesture permission violation)
  const throwingNav = {
    vibrate() {
      throw new Error("SecurityError: vibrate not permitted without user gesture")
    },
  }
  assert.doesNotThrow(() => {
    const res = triggerHapticFeedback("PASS", { navigator: throwingNav })
    assert.equal(res, false)
  })
})

