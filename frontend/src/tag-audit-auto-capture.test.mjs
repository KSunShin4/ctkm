import test from "node:test"
import assert from "node:assert/strict"
import {
  AUTO_CAPTURE_CONFIG,
  analyzeLuma,
  autoCaptureStatusText,
  createAutoCaptureController,
  evaluateFrameQuality,
  getFrameRoi,
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

test("getFrameRoi handles missing or unready video gracefully", () => {
  assert.equal(getFrameRoi(null), null)
  assert.equal(getFrameRoi({ videoWidth: 0, videoHeight: 0 }), null)
})

test("getFrameRoi falls back to safe default when frame element is not provided", () => {
  const roi = getFrameRoi({ videoWidth: 1920, videoHeight: 1080 })
  assert.deepEqual(roi, {
    sx: 154,
    sy: 162,
    sw: 1613,
    sh: 756,
  })
})

test("getFrameRoi calculates exact source coordinates with object-fit: cover scaling", () => {
  const video = {
    videoWidth: 1920,
    videoHeight: 1080,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 400, height: 600 }),
  }
  const frameEl = {
    getBoundingClientRect: () => ({ left: 32, top: 90, width: 336, height: 420 }),
  }
  const roi = getFrameRoi(video, frameEl)
  assert.ok(roi)
  assert.ok(roi.sx >= 0 && roi.sx < 1920)
  assert.ok(roi.sy >= 0 && roi.sy < 1080)
  assert.ok(roi.sw > 0 && roi.sx + roi.sw <= 1920)
  assert.ok(roi.sh > 0 && roi.sy + roi.sh <= 1080)
})

test("evaluateFrameQuality is an alias for analyzeLuma", () => {
  assert.equal(evaluateFrameQuality, analyzeLuma)
})

test("quality gate rejects frame with severe glare (> 35% pixels >= 248)", () => {
  const width = 10
  const height = 10
  const pixels = new Uint8Array(width * height)
  // Fill 40% with glare (252) and 60% with normal luma (120)
  for (let i = 0; i < 40; i += 1) pixels[i] = 252
  for (let i = 40; i < 100; i += 1) pixels[i] = 120
  const result = evaluateFrameQuality(pixels, width, height)
  assert.equal(result.usable, false)
  assert.equal(result.reason, "glare")
  assert.equal(result.glareRatio, 0.4)
})

test("quality gate accepts frame with mild highlights below glare threshold", () => {
  const frame = textured()
  // Add 10 highlight pixels out of 108 pixels (~9.2% glare)
  for (let i = 0; i < 10; i += 1) {
    frame.pixels[i] = 250
  }
  const result = evaluateFrameQuality(frame.pixels, frame.width, frame.height, {
    ...AUTO_CAPTURE_CONFIG,
    minEdgeEnergy: 5,
    minActiveTiles: 2,
  })
  assert.equal(result.usable, true)
  assert.equal(result.reason, "ready")
  assert.ok(result.glareRatio > 0 && result.glareRatio <= 0.35)
})

test("autoCaptureStatusText provides guidance when glare is detected", () => {
  const text = autoCaptureStatusText({ status: "glare" })
  assert.equal(text, "Tem bị chói sáng · vui lòng nghiêng nhẹ góc chụp")
})

test("getFrameRoi safely handles edge case dimensions or invalid scale", () => {
  const tinyFrame = {
    getBoundingClientRect: () => ({ left: 100, top: 100, width: 5, height: 5 }),
  }
  const videoEl = {
    videoWidth: 1920,
    videoHeight: 1080,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 400, height: 600 }),
  }
  const fallbackRoi = getFrameRoi(videoEl, tinyFrame)
  assert.deepEqual(fallbackRoi, {
    sx: 154,
    sy: 162,
    sw: 1613,
    sh: 756,
  })
})

