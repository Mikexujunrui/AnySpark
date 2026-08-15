// SSE factories extracted from api.ts — unified streaming connection layer.

import { diagLog } from './http'

const API = ''

export function createSSE(url: string, data: unknown, signal?: AbortSignal): Promise<Response> {
  diagLog.info(`SSE POST ${url} — 建立连接`)
  return fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
  }).then(res => {
    const ct = res.headers.get('content-type') || ''
    diagLog.info(`SSE POST ${url} — 响应 %d | content-type=%s`, res.status, ct)
    if (!res.ok) {
      diagLog.error(`SSE POST ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    if (e instanceof DOMException && e.name === 'AbortError') {
      diagLog.info(`SSE POST ${url} — 已取消 (AbortError)`)
    } else {
      diagLog.error(`SSE POST ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    }
    throw e
  })
}

export function createTaskSSE(bookId: string, taskId: string): Promise<Response> {
  const url = `/api/books/${bookId}/tasks/${taskId}/stream`
  diagLog.info(`SSE GET ${url} — 建立连接`)
  return fetch(API + url).then(res => {
    diagLog.info(`SSE GET ${url} — 响应 %d`, res.status)
    if (!res.ok) {
      diagLog.error(`SSE GET ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    diagLog.error(`SSE GET ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    throw e
  })
}

export function createAutopilotBridgeSSE(bookId: string, taskId: string): Promise<Response> {
  const url = `/api/books/${bookId}/autopilot/${taskId}/chat-bridge`
  diagLog.info(`SSE GET ${url} — 建立连接`)
  return fetch(API + url).then(res => {
    diagLog.info(`SSE GET ${url} — 响应 %d`, res.status)
    if (!res.ok) {
      diagLog.error(`SSE GET ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    diagLog.error(`SSE GET ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    throw e
  })
}
