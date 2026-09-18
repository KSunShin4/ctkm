import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Compatibility patches must stay flat across Vite HMR/module re-execution.
// Keep only native browser primitives and the React root globally; recreate the
// current wrapper from those primitives instead of wrapping a previous wrapper.
const COMPAT_KEY = '__ctkmCompatibilityV1'
const compat = globalThis[COMPAT_KEY] || (globalThis[COMPAT_KEY] = {})

// App.jsx historically checks drag-dropped filenames with a lowercase `.xlsx`
// suffix. Normalize only that suffix at the File API boundary so `.XLSX` works
// without changing the large UI component or any non-Excel filename.
if (!compat.nativeFileNameDescriptor) {
  compat.nativeFileNameDescriptor = Object.getOwnPropertyDescriptor(File.prototype, 'name')
}
const fileNameDescriptor = compat.nativeFileNameDescriptor
if (fileNameDescriptor?.get && fileNameDescriptor.configurable) {
  Object.defineProperty(File.prototype, 'name', {
    ...fileNameDescriptor,
    get() {
      const name = fileNameDescriptor.get.call(this)
      return /\.xlsx$/i.test(name) ? name.replace(/\.xlsx$/i, '.xlsx') : name
    },
  })
}

if (!compat.nativeFetch) compat.nativeFetch = window.fetch.bind(window)
const nativeFetch = compat.nativeFetch
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

const compatibilityFetch = async (...args) => {
  const requestUrl = String(args[0] instanceof Request ? args[0].url : args[0] || '')
  const requestMethod = String(
    args[1]?.method || (args[0] instanceof Request ? args[0].method : 'GET') || 'GET'
  ).toUpperCase()
  const retryableRead = requestMethod === 'GET' && (
    requestUrl.includes('/api/job/') ||
    requestUrl.includes('/api/queue/status') ||
    requestUrl.includes('/api/preview/')
  )

  let response
  for (let attempt = 0; attempt < (retryableRead ? 3 : 1); attempt += 1) {
    try {
      response = await nativeFetch(...args)
    } catch (error) {
      if (!retryableRead || attempt >= 2) throw error
      await sleep(350 * (attempt + 1))
      continue
    }
    if (retryableRead && response.status >= 500 && attempt < 2) {
      await sleep(350 * (attempt + 1))
      continue
    }
    break
  }

  // App.jsx expects API error responses to be JSON. Render/proxies may return a
  // plain-text or HTML 5xx body instead (for example "Internal Server Error").
  // Convert only failed /api responses to JSON so the UI shows the real message
  // instead of throwing "Unexpected token ... is not valid JSON".
  if (!response.ok && requestUrl.includes('/api/')) {
    const contentType = response.headers.get('content-type') || ''
    if (!contentType.toLowerCase().includes('application/json')) {
      const raw = (await response.clone().text()).trim()
      const detail = raw && !raw.startsWith('<')
        ? raw.slice(0, 1000)
        : `Máy chủ trả lỗi HTTP ${response.status}. Hãy thử lại hoặc kiểm tra log backend.`
      const headers = new Headers(response.headers)
      headers.set('content-type', 'application/json')
      return new Response(JSON.stringify({ detail }), {
        status: response.status,
        statusText: response.statusText,
        headers,
      })
    }
  }

  // App.jsx historically falls back to the first returned POG sheet. When the
  // backend reports multiple candidate sheets, prepend an empty option so the
  // existing dropdown requires an explicit user selection.
  if (!response.ok || !requestUrl.includes('/api/inspect-pog')) return response
  try {
    const data = await response.clone().json()
    if (!data?.requires_sheet_selection || !Array.isArray(data.sheet_names)) return response
    if (data.sheet_names[0] !== '') data.sheet_names = ['', ...data.sheet_names]
    const headers = new Headers(response.headers)
    headers.set('content-type', 'application/json')
    return new Response(JSON.stringify(data), {
      status: response.status,
      statusText: response.statusText,
      headers,
    })
  } catch {
    return response
  }
}
compatibilityFetch.__ctkmCompatibilityFetchV1 = true
compat.fetchWrapper = compatibilityFetch
window.fetch = compatibilityFetch

// Keep legacy App.jsx text aligned with current backend contracts without a risky
// full-file rewrite. Values already come from the correct API keys; only labels
// and a few historical explanatory strings are stale.
const SUMMARY_LABEL_REWRITES = new Map([
  ['Dòng khớp (CTKM + kệ)', 'Dòng khớp (CTKM + POG)'],
  ['POG không có CTKM phù hợp', 'POG không có KM phù hợp'],
  ['Cảnh báo trùng thời gian', 'Sản phẩm có cảnh báo trùng thời gian'],
])
const TEXT_REWRITES = new Map([
  ['Chỉ dùng mapping đã lưu (không gọi Gemini)', 'Không gọi Gemini (mapping chuẩn/đã lưu)'],
  ['Gemini nhận diện cột…', 'Nhận diện và kiểm tra mapping cột…'],
  [
    'Không lấy được gợi ý từ Gemini. Hãy chọn các cột thủ công rồi bấm “Lưu mapping đã xác nhận”.',
    'Có cảnh báo mapping. Hãy kiểm tra các cột bên dưới trước khi lưu hoặc chạy.',
  ],
])

const rewriteTextNodes = root => {
  if (!root || typeof document.createTreeWalker !== 'function') return
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    const raw = node.nodeValue || ''
    const trimmed = raw.trim()
    let replacement = TEXT_REWRITES.get(trimmed)
    if (!replacement && trimmed.startsWith('Gemini không khả dụng. Bạn vẫn có thể chọn mapping thủ công bên dưới.')) {
      replacement = trimmed.replace(
        'Gemini không khả dụng. Bạn vẫn có thể chọn mapping thủ công bên dưới.',
        'Có cảnh báo mapping. Hãy kiểm tra mapping bên dưới.'
      )
    }
    if (!replacement && trimmed.startsWith('Gemini đang nhận diện cột, ghép CTKM với POG theo tháng')) {
      replacement = trimmed.replace(
        'Gemini đang nhận diện cột',
        'Hệ thống đang kiểm tra mapping cột'
      )
    }
    if (replacement && trimmed !== replacement) {
      node.nodeValue = raw.replace(trimmed, replacement)
    }
    node = walker.nextNode()
  }
}

const ensureTagAuditNav = root => {
  const nav = root?.querySelector?.('.module-nav')
  if (!nav) return

  // Store-facing shelf checking is a first-class module. Keep it immediately
  // beside “Kiểm tra hạn dùng” and never gate it behind Admin.
  let shelfButton = nav.querySelector('[data-ctkm-shelf-link="v1"]')
  if (!shelfButton) {
    shelfButton = document.createElement('button')
    shelfButton.type = 'button'
    shelfButton.dataset.ctkmShelfLink = 'v1'
    shelfButton.textContent = 'Kiểm tra kệ'
    shelfButton.title = 'Mở chế độ kiểm Đúng/Sai từng action theo kệ'
    shelfButton.addEventListener('click', () => {
      window.location.assign('/scan-tem?mode=shelf')
    })
    const expirationButton = nav.firstElementChild
    if (expirationButton) expirationButton.after(shelfButton)
    else nav.appendChild(shelfButton)
  }

  const existing = nav.querySelector('[data-ctkm-tag-audit-link="v1"]')
  let scheduleButton = nav.querySelector('[data-ctkm-schedule-link="v1"]')
  const isAdmin = Array.from(root.querySelectorAll?.('.auth-actions span') || [])
    .some(node => node.textContent?.trim() === 'ADMIN')

  if (!isAdmin) {
    existing?.remove()
    scheduleButton?.remove()
    return
  }
  if (!scheduleButton) {
    scheduleButton = document.createElement('button')
    scheduleButton.type = 'button'
    scheduleButton.dataset.ctkmScheduleLink = 'v1'
    scheduleButton.textContent = 'Xếp lịch'
    scheduleButton.title = 'Xếp lịch nhân viên và xuất Excel'
    scheduleButton.addEventListener('click', () => {
      window.location.assign('/schedule')
    })
    nav.appendChild(scheduleButton)
  }
  if (existing) return

  const button = document.createElement('button')
  button.type = 'button'
  button.dataset.ctkmTagAuditLink = 'v1'
  button.textContent = 'Kiểm tem CTKM'
  button.title = 'Mở công cụ quét và đối chiếu một tem khuyến mãi mỗi lần'
  button.addEventListener('click', () => {
    window.location.assign('/scan-tem')
  })
  nav.appendChild(button)
}

const rewriteLegacyUiText = root => {
  root?.querySelectorAll?.('.stat-label').forEach(node => {
    const replacement = SUMMARY_LABEL_REWRITES.get(node.textContent?.trim())
    if (replacement && node.textContent !== replacement) node.textContent = replacement
  })
  root?.querySelectorAll?.('.section-title > span').forEach(node => {
    if (node.textContent?.trim() === '50 dòng đầu mỗi sheet') {
      node.textContent = 'Tối đa 100 dòng hiển thị mỗi sheet'
    }
  })
  root?.querySelectorAll?.('.stat-box').forEach(box => {
    const label = box.querySelector('.stat-label')?.textContent?.trim()
    const sub = box.querySelector('.stat-sub')
    if (label !== 'Thiếu vị trí POG' || !sub) return
    const text = sub.textContent?.trim() || ''
    const match = text.match(/^(\d+)\s+CTKM theo hóa đơn(?:\s+·\s+không tính thiếu POG)?$/)
    if (!match) return
    const replacement = `${match[1]} CTKM theo hóa đơn · không tính thiếu POG`
    if (text !== replacement) sub.textContent = replacement
  })
  root?.querySelectorAll?.('.download-name').forEach(node => {
    const text = node.textContent?.trim() || ''
    const match = text.match(/^tong_hop_ctkm_(\d{4}-\d{2})\.xlsx$/i)
    if (match) node.textContent = `Workbook CTKM tháng ${match[1]}`
  })
  ensureTagAuditNav(root)
  rewriteTextNodes(root)
}

const rootElement = document.getElementById('root')
compat.labelObserver?.disconnect?.()
const labelObserver = new MutationObserver(() => rewriteLegacyUiText(rootElement))
labelObserver.observe(rootElement, { childList: true, subtree: true, characterData: true })
compat.labelObserver = labelObserver

if (!compat.reactRoot) compat.reactRoot = ReactDOM.createRoot(rootElement)
compat.reactRoot.render(<App />)
queueMicrotask(() => rewriteLegacyUiText(rootElement))
