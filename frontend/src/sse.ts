export interface SSEEvent {
  type: string
  data: string
  parsed: Record<string, unknown> | string | null
}

const DIAG_PREFIX = '[CONN-DIAG]'
let totalBytesRead = 0
let totalEventsParsed = 0
let parseErrors = 0

export function getSSEDiagnosticsSummary(): string {
  return `SSE诊断: 总读取=${totalBytesRead}B | 事件=${totalEventsParsed} | 解析错误=${parseErrors}`
}

export async function* parseSSE(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) {
    console.warn(`${DIAG_PREFIX} SSE parse — 响应体为空`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let chunkCount = 0

  console.log(`${DIAG_PREFIX} SSE parse — 开始读取流`)

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        console.log(`${DIAG_PREFIX} SSE parse — 流结束 | 总chunks=${chunkCount} | 总事件=${totalEventsParsed}`)
        break
      }

      chunkCount++
      totalBytesRead += value.byteLength

      buffer += decoder.decode(value, { stream: true })
      const normalized = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      const parts = normalized.split('\n\n')
      buffer = parts.pop() || ''

      for (const raw of parts) {
        if (!raw.trim()) continue
        const event: SSEEvent = { type: '', data: '', parsed: null }
        const lines = raw.split('\n')

        for (const line of lines) {
          if (line.startsWith('event:')) {
            event.type = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            event.data += (event.data ? '\n' : '') + line.slice(5).trim()
          } else if (line.startsWith(':')) {
            continue
          }
        }

        if (event.data) {
          try {
            event.parsed = JSON.parse(event.data)
          } catch {
            event.parsed = null
          }
          totalEventsParsed++
          yield event
        }
      }
    }

    if (buffer.trim()) {
      const event: SSEEvent = { type: '', data: '', parsed: null }
      const lines = buffer.split('\n')
      for (const line of lines) {
        if (line.startsWith('event:')) {
          event.type = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          event.data += (event.data ? '\n' : '') + line.slice(5).trim()
        }
      }
      if (event.data) {
        try {
          event.parsed = JSON.parse(event.data)
        } catch {
          event.parsed = null
        }
        totalEventsParsed++
        yield event
      }
    }
  } catch (e) {
    parseErrors++
    console.error(`${DIAG_PREFIX} SSE parse — 读取异常: ${e instanceof Error ? e.message : String(e)} | 已读取=${totalBytesRead}B | chunk=${chunkCount}`)
    throw e
  } finally {
    reader.releaseLock()
    console.log(`${DIAG_PREFIX} SSE parse — 释放reader锁`)
  }
}

export function isEventStream(response: Response): boolean {
  const ct = response.headers.get('content-type')
  return ct ? ct.includes('text/event-stream') : false
}
