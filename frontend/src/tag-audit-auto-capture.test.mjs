import test from "node:test"
import assert from "node:assert/strict"
import {
  AUTO_CAPTURE_CONFIG,
  analyzeLuma,
  createAutoCaptureController,
  meanAbsDiff,
} from "./tag-audit-auto-capture.js"

function sample(value, width = 12, height = 9) {
  return { pixels: new Uint8Array(width * height).fill(value), width, height }
}

function textured(offset = 0, width = 12, height = 9) {
  const pixels = new Uint8Array(width * height)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      pixels[y * width + x] = Math.max(0, Math.min(255, 60 + ((x + y) % 2) * 140 + offset))
    }
  }
  return { pixels, width, height }
}

test("meanAbsDiff is deterministic and rejects incompatible frames", () => {
  assert.equal(meanAbsDiff(new Uint8Array([10, 20]), new Uint8Array([12, 24])), 3)
  assert.equal(meanAbsDiff(new Uint8Array([1]), new Uint8Array([1, 2])), Infinity)
})

test("quality gate rejects dark flat frames", () => {
  const result = analyzeLuma(sample(20).pixels, 12, 9)
  assert.equal(result.usable, false)
  assert.equal(result.reason, "too_dark")
})

test("quality gate accepts a well-lit textured center frame", () => {
  const frame = textured()
  const result = analyzeLuma(frame.pixels, frame.width, frame.height, {
    ...AUTO_CAPTURE_CONFIG,
    minEdgeEnergy: 5,
    minActiveTiles: 2,
  })
  assert.equal(result.usable, true)
})

test("controller requires sustained stability before one trigger", () => {
  const controller = createAutoCaptureController({
    ...AUTO_CAPTURE_CONFIG,
    stableFrames: 3,
    minEdgeEnergy: 5,
    minActiveTiles: 2,
    maxMotion: 5,
  })
  const frame = textured()
  assert.equal(controller.inspect(frame, 1000).trigger, false)
  assert.equal(controller.inspect(frame, 1250).trigger, false)
  assert.equal(controller.inspect(frame, 1500).trigger, false)
  const triggered = controller.inspect(frame, 1750)
  assert.equal(triggered.trigger, true)
  assert.equal(triggered.status, "capture")
  assert.equal(controller.inspect(frame, 2000).trigger, false)
  assert.equal(controller.inspect(frame, 2000).status, "move_next")
})

test("captured scene stays locked until a materially different scene appears", () => {
  const controller = createAutoCaptureController({
    ...AUTO_CAPTURE_CONFIG,
    stableFrames: 1,
    minEdgeEnergy: 5,
    minActiveTiles: 2,
    maxMotion: 5,
    rearmMotion: 10,
    rearmFrames: 2,
    minCaptureGapMs: 1000,
  })
  const first = textured()
  controller.inspect(first, 1000)
  assert.equal(controller.inspect(first, 1250).trigger, true)

  const changed = textured(25)
  assert.equal(controller.inspect(changed, 2500).status, "move_next")
  const rearmed = controller.inspect(changed, 2750)
  assert.equal(rearmed.status, "rearmed")
  assert.equal(rearmed.armed, true)
})
