const DB_NAME = "ctkm-tag-audit"
const DB_VERSION = 1
const STORE_NAME = "context"
const WORKBOOK_KEY = "latest-uploaded-workbook"
const MAX_CACHE_BYTES = 30 * 1024 * 1024

function openDb() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) return reject(new Error("IndexedDB không khả dụng"))
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error("Không mở được IndexedDB"))
  })
}

async function withStore(mode, operation) {
  const db = await openDb()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode)
      const store = tx.objectStore(STORE_NAME)
      let request
      try { request = operation(store) } catch (error) { reject(error); return }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error || new Error("IndexedDB operation failed"))
    })
  } finally {
    db.close()
  }
}

export async function cacheUploadedWorkbook(file) {
  if (!(file instanceof Blob)) return { cached: false, reason: "not_blob" }
  if (file.size <= 0 || file.size > MAX_CACHE_BYTES) return { cached: false, reason: "size_limit" }
  const value = {
    blob: file,
    name: typeof file.name === "string" && file.name ? file.name : "ctkm.xlsx",
    type: file.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    size: file.size,
    savedAt: new Date().toISOString(),
  }
  try {
    await withStore("readwrite", store => store.put(value, WORKBOOK_KEY))
    return { cached: true }
  } catch (error) {
    return { cached: false, reason: error?.message || "storage_error" }
  }
}

export async function readCachedWorkbook() {
  try {
    const value = await withStore("readonly", store => store.get(WORKBOOK_KEY))
    if (!value?.blob || !(value.blob instanceof Blob)) return null
    if (value.blob.size <= 0 || value.blob.size > MAX_CACHE_BYTES) return null
    return value
  } catch {
    return null
  }
}

export async function clearCachedWorkbook() {
  try {
    await withStore("readwrite", store => store.delete(WORKBOOK_KEY))
    return true
  } catch {
    return false
  }
}

function copyAuthHeaders(options = {}) {
  const headers = new Headers(options.headers || {})
  const authorization = headers.get("Authorization")
  return authorization ? { Authorization: authorization } : {}
}

export async function restoreTagAuditContext(nativeFetch, requestOptions = {}) {
  const cached = await readCachedWorkbook()
  if (!cached) return null

  const file = new File([cached.blob], cached.name || "ctkm.xlsx", {
    type: cached.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  })
  const form = new FormData()
  form.append("workbook", file)

  try {
    const response = await nativeFetch("/api/tag-audit/context", {
      method: "POST",
      headers: copyAuthHeaders(requestOptions),
      body: form,
    })
    if (!response.ok) return null
    let payload = null
    try { payload = await response.clone().json() } catch {}
    if (!payload?.ready) return null
    return response
  } catch {
    return null
  }
}

export function workbookFromRequestBody(body) {
  if (!(body instanceof FormData)) return null
  const workbook = body.get("workbook")
  return workbook instanceof Blob ? workbook : null
}

export const tagAuditContextCacheConfig = {
  dbName: DB_NAME,
  storeName: STORE_NAME,
  maxCacheBytes: MAX_CACHE_BYTES,
}
