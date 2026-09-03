import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// App.jsx historically checks drag-dropped filenames with a lowercase `.xlsx`
// suffix. Normalize only that suffix at the File API boundary so `.XLSX` works
// without changing the large UI component or any non-Excel filename.
const fileNameDescriptor = Object.getOwnPropertyDescriptor(File.prototype, 'name')
if (fileNameDescriptor?.get && fileNameDescriptor.configurable) {
  Object.defineProperty(File.prototype, 'name', {
    ...fileNameDescriptor,
    get() {
      const name = fileNameDescriptor.get.call(this)
      return /\.xlsx$/i.test(name) ? name.replace(/\.xlsx$/i, '.xlsx') : name
    },
  })
}

const nativeFetch = window.fetch.bind(window)
window.fetch = async (...args) => {
  const response = await nativeFetch(...args)
  const requestUrl = String(args[0] instanceof Request ? args[0].url : args[0] || '')

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

// Keep legacy App.jsx text aligned with current backend contracts without a risky
// full-file rewrite. Values already come from the correct API keys; only labels
// and the historical 50-row preview caption are stale.
const SUMMARY_LABEL_REWRITES = new Map([
  ['Dòng khớp (CTKM + kệ)', 'Dòng khớp (CTKM + POG)'],
  ['POG không có CTKM phù hợp', 'POG không có KM phù hợp'],
  ['Cảnh báo trùng thời gian', 'Sản phẩm có cảnh báo trùng thời gian'],
])

const rewriteLegacyUiText = root => {
  root?.querySelectorAll?.('.stat-label').forEach(node => {
    const replacement = SUMMARY_LABEL_REWRITES.get(node.textContent?.trim())
    if (replacement && node.textContent !== replacement) node.textContent = replacement
  })
  root?.querySelectorAll?.('.section-title > span').forEach(node => {
    if (node.textContent?.trim() === '50 dòng đầu mỗi sheet') {
      node.textContent = 'Tối đa 100 dòng visible mỗi sheet'
    }
  })
}

const rootElement = document.getElementById('root')
const labelObserver = new MutationObserver(() => rewriteLegacyUiText(rootElement))
labelObserver.observe(rootElement, { childList: true, subtree: true, characterData: true })

ReactDOM.createRoot(rootElement).render(<App />)
queueMicrotask(() => rewriteLegacyUiText(rootElement))
