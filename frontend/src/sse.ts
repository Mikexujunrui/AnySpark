export interface SSEEvent {
  type: string
  data: string
  parsed: Record<string, unknown> | string | null
}

export async function* parseSSE(response: Response): AsyncGenerator<SSEEvent> {
  if (!response.body) return

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break

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
        yield event
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export function isEventStream(response: Response): boolean {
  const ct = response.headers.get('content-type')
  return ct ? ct.includes('text/event-stream') : false
}
