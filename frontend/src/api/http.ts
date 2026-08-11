// HTTP infrastructure extracted from api.ts — shared by all api domains.

const API = ''

// ── Connection diagnostics ──
// Structured logging for all API/SSE connections to help diagnose
// frontend-backend connectivity instability.
const DIAG_PREFIX = '[CONN-DIAG]'
export const diagLog = {
  info: (msg: string, ...args: unknown[]) => {
    console.log(`${DIAG_PREFIX} ${msg}`, ...args)
  },
  warn: (msg: string, ...args: unknown[]) => {
    console.warn(`${DIAG_PREFIX} ${msg}`, ...args)
  },
  error: (msg: string, ...args: unknown[]) => {
    console.error(`${DIAG_PREFIX} ${msg}`, ...args)
  },
}

export async function assertOk(res: Response): Promise<void> {
  if (res.ok) return
  let message: string = res.statusText || `请求失败 (${res.status})`
  const data = await res.json().catch(() => null)
  if (data && (data.error || data.detail || data.message)) {
    message = data.error || data.detail || data.message
  }
  throw new Error(message)
}

async function requestWithDiags<T>(method: string, url: string, options?: RequestInit): Promise<T> {
  const startTime = performance.now()
  diagLog.info(`${method} ${url} — 开始请求`)
  try {
    const res = await fetch(API + url, options)
    const elapsed = Math.round(performance.now() - startTime)
    if (!res.ok) {
      diagLog.warn(`${method} ${url} — 失败 %d | %dms`, res.status, elapsed)
    } else {
      diagLog.info(`${method} ${url} — 成功 | %dms`, elapsed)
    }
    await assertOk(res)
    return res.json()
  } catch (e) {
    const elapsed = Math.round(performance.now() - startTime)
    const errMsg = e instanceof Error ? e.message : String(e)
    diagLog.error(`${method} ${url} — 异常 | %dms | %s`, elapsed, errMsg)
    throw e
  }
}

export async function get<T = unknown>(url: string): Promise<T> {
  return requestWithDiags<T>('GET', url)
}

export async function post<T = unknown>(url: string, data?: unknown): Promise<T> {
  return requestWithDiags<T>('POST', url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function del<T = unknown>(url: string): Promise<T> {
  return requestWithDiags<T>('DELETE', url, {
    method: 'DELETE',
    headers: { 'X-Confirm-Delete': 'true' },
  })
}

export async function put<T = unknown>(url: string, data?: unknown): Promise<T> {
  return requestWithDiags<T>('PUT', url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
