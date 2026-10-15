export const AUTO_CAPTURE_CONFIG = Object.freeze({
  sampleWidth: 120,
  sampleHeight: 90,
  roi: Object.freeze({ x: 0.08, y: 0.15, width: 0.84, height: 0.70 }),
  intervalMs: 250,
  stableFrames: 4,
  minMean: 55,
  maxMean: 235,
  minStdDev: 18,
  minEdgeEnergy: 10,
  minActiveTiles: 3,
  maxMotion: 4.5,
  rearmMotion: 15,
  rearmFrames: 2,
  minCaptureGapMs: 1800,
  maxGlareRatio: 0.35,
})

function clamp(value, min, max) { return Math.max(min, Math.min(max, value)) }

export function getFrameRoi(video, frameEl) {
  if (!video?.videoWidth || !video?.videoHeight) return null
  const vw = video.videoWidth
  const vh = video.videoHeight
  if (!frameEl) {
    return {
      sx: Math.round(vw * 0.08),
      sy: Math.round(vh * 0.15),
      sw: Math.round(vw * 0.84),
      sh: Math.round(vh * 0.70),
    }
  }
  const videoRect = typeof video.getBoundingClientRect === "function" ? video.getBoundingClientRect() : null
  const frameRect = typeof frameEl.getBoundingClientRect === "function" ? frameEl.getBoundingClientRect() : null
  if (!videoRect?.width || !videoRect?.height || !frameRect?.width || !frameRect?.height) {
    return {
      sx: Math.round(vw * 0.08),
      sy: Math.round(vh * 0.15),
      sw: Math.round(vw * 0.84),
      sh: Math.round(vh * 0.70),
    }
  }
  const scale = Math.max(videoRect.width / vw, videoRect.height / vh)
  if (!Number.isFinite(scale) || scale <= 0) {
    return {
      sx: Math.round(vw * 0.08),
      sy: Math.round(vh * 0.15),
      sw: Math.round(vw * 0.84),
      sh: Math.round(vh * 0.70),
    }
  }
  const renderedW = vw * scale
  const renderedH = vh * scale
  const videoLeft = (videoRect.width - renderedW) / 2
  const videoTop = (videoRect.height - renderedH) / 2

  const frameLeft = frameRect.left - (videoRect.left + videoLeft)
  const frameTop = frameRect.top - (videoRect.top + videoTop)
  const frameWidth = frameRect.width
  const frameHeight = frameRect.height

  const marginX = frameWidth * 0.06
  const marginY = frameHeight * 0.06

  const sx = Math.max(0, Math.min(vw - 1, Math.round((frameLeft - marginX) / scale)))
  const sy = Math.max(0, Math.min(vh - 1, Math.round((frameTop - marginY) / scale)))
  const sw = Math.max(1, Math.min(vw - sx, Math.round((frameWidth + marginX * 2) / scale)))
  const sh = Math.max(1, Math.min(vh - sy, Math.round((frameHeight + marginY * 2) / scale)))

  if (sw <= 10 || sh <= 10) {
    return {
      sx: Math.round(vw * 0.08),
      sy: Math.round(vh * 0.15),
      sw: Math.round(vw * 0.84),
      sh: Math.round(vh * 0.70),
    }
  }

  return { sx, sy, sw, sh }
}

export function meanAbsDiff(a, b) {
  if (!a || !b || a.length !== b.length || !a.length) return Infinity
  let total = 0
  for (let i = 0; i < a.length; i += 1) total += Math.abs(a[i] - b[i])
  return total / a.length
}

function tileIndex(x, y, width, height) {
  const tx = Math.min(2, Math.floor((x / Math.max(1, width)) * 3))
  const ty = Math.min(2, Math.floor((y / Math.max(1, height)) * 3))
  return ty * 3 + tx
}

export function analyzeLuma(pixels, width, height, config = AUTO_CAPTURE_CONFIG) {
  const count = pixels?.length || 0
  if (!count || width <= 1 || height <= 1) {
    return { mean: 0, stdDev: 0, edgeEnergy: 0, activeTiles: 0, glareRatio: 0, usable: false, reason: "camera_not_ready" }
  }

  let sum = 0
  let sumSq = 0
  let glareCount = 0
  for (let i = 0; i < count; i += 1) {
    const value = pixels[i]
    sum += value
    sumSq += value * value
    if (value >= 248) {
      glareCount += 1
    }
  }
  const mean = sum / count
  const variance = Math.max(0, sumSq / count - mean * mean)
  const stdDev = Math.sqrt(variance)
  const glareRatio = count ? glareCount / count : 0

  let edgeTotal = 0
  let edgeCount = 0
  const tileTotals = Array(9).fill(0)
  const tileCounts = Array(9).fill(0)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x
      if (x + 1 < width) {
        const diff = Math.abs(pixels[index] - pixels[index + 1])
        edgeTotal += diff; edgeCount += 1
        const tile = tileIndex(x, y, width, height)
        tileTotals[tile] += diff; tileCounts[tile] += 1
      }
      if (y + 1 < height) {
        const diff = Math.abs(pixels[index] - pixels[index + width])
        edgeTotal += diff; edgeCount += 1
        const tile = tileIndex(x, y, width, height)
        tileTotals[tile] += diff; tileCounts[tile] += 1
      }
    }
  }
  const edgeEnergy = edgeCount ? edgeTotal / edgeCount : 0
  const activeTiles = tileTotals.reduce((total, value, index) => {
    const energy = tileCounts[index] ? value / tileCounts[index] : 0
    return total + (energy >= config.minEdgeEnergy * 0.55 ? 1 : 0)
  }, 0)

  const maxGlareRatio = config.maxGlareRatio ?? 0.35
  let reason = "ready"
  if (mean < config.minMean) reason = "too_dark"
  else if (mean > config.maxMean) reason = "too_bright"
  else if (glareRatio > maxGlareRatio) reason = "glare"
  else if (stdDev < config.minStdDev) reason = "low_contrast"
  else if (edgeEnergy < config.minEdgeEnergy) reason = "not_sharp_enough"
  else if (activeTiles < config.minActiveTiles) reason = "center_not_filled"

  return {
    mean: Math.round(mean * 10) / 10,
    stdDev: Math.round(stdDev * 10) / 10,
    edgeEnergy: Math.round(edgeEnergy * 10) / 10,
    activeTiles,
    glareRatio: Math.round(glareRatio * 1000) / 1000,
    usable: reason === "ready",
    reason,
  }
}

export const evaluateFrameQuality = analyzeLuma

export function createAutoCaptureController(config = AUTO_CAPTURE_CONFIG) {
  let previous = null
  let captured = null
  let stableCount = 0
  let rearmCount = 0
  let armed = true
  let lastCaptureAt = 0

  function inspect(sample, now = Date.now()) {
    const quality = analyzeLuma(sample?.pixels, sample?.width || 0, sample?.height || 0, config)
    const motion = previous ? meanAbsDiff(sample.pixels, previous.pixels) : Infinity
    const sceneChange = captured ? meanAbsDiff(sample.pixels, captured.pixels) : motion
    previous = sample

    if (!armed) {
      rearmCount = sceneChange >= config.rearmMotion ? rearmCount + 1 : 0
      if (rearmCount >= config.rearmFrames && now - lastCaptureAt >= config.minCaptureGapMs) {
        armed = true
        stableCount = 0
        rearmCount = 0
        captured = null
        return { trigger: false, armed: true, status: "rearmed", quality, motion, sceneChange, stableCount }
      }
      return { trigger: false, armed: false, status: "move_next", quality, motion, sceneChange, stableCount: 0 }
    }

    if (!quality.usable) {
      stableCount = 0
      return { trigger: false, armed: true, status: quality.reason, quality, motion, sceneChange, stableCount }
    }
    if (!Number.isFinite(motion) || motion > config.maxMotion) {
      stableCount = 0
      return { trigger: false, armed: true, status: "hold_still", quality, motion, sceneChange, stableCount }
    }

    stableCount += 1
    if (stableCount < config.stableFrames) {
      return { trigger: false, armed: true, status: "stabilizing", quality, motion, sceneChange, stableCount }
    }

    armed = false
    captured = sample
    lastCaptureAt = now
    stableCount = 0
    rearmCount = 0
    return { trigger: true, armed: false, status: "capture", quality, motion, sceneChange, stableCount: config.stableFrames }
  }

  function lockCurrent(now = Date.now()) {
    armed = false
    captured = previous
    stableCount = 0
    rearmCount = 0
    lastCaptureAt = now
  }

  function reset() {
    previous = null
    captured = null
    stableCount = 0
    rearmCount = 0
    armed = true
    lastCaptureAt = 0
  }

  function snapshot() { return { armed, stableCount, rearmCount, lastCaptureAt } }

  return { inspect, lockCurrent, reset, snapshot }
}

export function createVideoSampler(config = AUTO_CAPTURE_CONFIG, getRoi = null) {
  const canvas = document.createElement("canvas")
  canvas.width = config.sampleWidth
  canvas.height = config.sampleHeight
  const ctx = canvas.getContext("2d", { alpha: false, willReadFrequently: true })
  if (!ctx) throw new Error("Không tạo được bộ phân tích camera")

  return video => {
    if (!video?.videoWidth || !video?.videoHeight) throw new Error("Camera chưa sẵn sàng")
    let sx, sy, sw, sh
    const custom = typeof getRoi === "function" ? getRoi(video) : null
    if (custom && custom.sw > 0 && custom.sh > 0) {
      sx = clamp(custom.sx, 0, video.videoWidth - 1)
      sy = clamp(custom.sy, 0, video.videoHeight - 1)
      sw = clamp(custom.sw, 1, video.videoWidth - sx)
      sh = clamp(custom.sh, 1, video.videoHeight - sy)
    } else {
      const roi = config.roi
      sx = clamp(Math.round(video.videoWidth * roi.x), 0, video.videoWidth - 1)
      sy = clamp(Math.round(video.videoHeight * roi.y), 0, video.videoHeight - 1)
      sw = clamp(Math.round(video.videoWidth * roi.width), 1, video.videoWidth - sx)
      sh = clamp(Math.round(video.videoHeight * roi.height), 1, video.videoHeight - sy)
    }
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height)
    const rgba = ctx.getImageData(0, 0, canvas.width, canvas.height).data
    const luma = new Uint8Array(canvas.width * canvas.height)
    for (let src = 0, dst = 0; src < rgba.length; src += 4, dst += 1) {
      luma[dst] = Math.round(rgba[src] * 0.299 + rgba[src + 1] * 0.587 + rgba[src + 2] * 0.114)
    }
    return { pixels: luma, width: canvas.width, height: canvas.height }
  }
}

export function autoCaptureStatusText(decision, config = AUTO_CAPTURE_CONFIG) {
  switch (decision?.status) {
    case "too_dark": return "Ảnh đang tối · đưa tem ra vùng sáng hơn"
    case "too_bright": return "Ảnh quá sáng/phản chiếu · đổi góc camera"
    case "glare": return "Tem bị chói sáng · vui lòng nghiêng nhẹ góc chụp"
    case "low_contrast": return "Tem chưa nổi rõ · đưa camera gần hơn"
    case "not_sharp_enough": return "Ảnh chưa đủ nét · lấy nét rồi giữ yên"
    case "center_not_filled": return "Đưa một tem lấp phần lớn khung xanh"
    case "hold_still": return "Giữ yên camera…"
    case "stabilizing": return `Giữ yên ${decision.stableCount}/${config.stableFrames}`
    case "capture": return "Đã khóa ảnh · đang kiểm tem"
    case "move_next": return "Đưa tem tiếp theo vào khung để mở khóa"
    case "rearmed": return "Đã nhận tem mới · giữ yên để tự quét"
    default: return "Đưa một tem vào khung xanh"
  }
}
