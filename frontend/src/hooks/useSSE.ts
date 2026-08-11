import { useState, useRef, useEffect, useCallback } from 'react'
import { parseSSE } from "../sse"

// V4 适配版 useSSE：壳的 hook 接口（sendMessage/cancel/streaming），内部走 V4 /api/chat/stream 协议。
// V4 事件：turn_start / text_delta / tool_call / tool_execution_start / tool_execution_end / tool_result / done / error

export interface SSECallbacks {
  onMessage?: (msg: { type: string; text: string; parts?: unknown[]; metrics?: Record<string, unknown> }) => void
  onProgress?: (data: Record<string, unknown> | null) => void
  onPlotCards?: (data: Record<string, unknown>) => void
  onQuestion?: (data: Record<string, unknown>) => void
  onWriting?: (data: Record<string, unknown>) => void
  onTaskList?: (data: Record<string, unknown>) => void
  onWorkflow?: (data: Record<string, unknown>) => void
  onPatch?: (data: Record<string, unknown>) => void
  onKnowledgeChanged?: () => void
  onCorrection?: (data: Record<string, unknown>) => void
  onMetrics?: (data: Record<string, unknown>) => void
  onError?: (error: Error, msg: string) => void
}

export interface SSEOptions {
  bookId: string
  sessionId: string
  agentMode: string
  autoModeEnabled: boolean
}

export function useSSE({ bookId, sessionId, agentMode, onMessage, onProgress, onKnowledgeChanged, onMetrics, onError }: SSEOptions & SSECallbacks) {
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)
  const convIdRef = useRef<string | null>(null)
  const toolNamesRef = useRef<Record<string, number>>({})
  const toolCallsRef = useRef(0)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  async function sendMessage(msg: string) {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setStreaming(true)
    convIdRef.current = null
    toolNamesRef.current = {}
    toolCallsRef.current = 0
    let streamingStarted = false

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          conversation_id: sessionId || undefined,
          model_id: agentMode || undefined,
        }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const text = await res.text().catch(() => '')
        onError?.(new Error(text || `HTTP ${res.status}`), msg)
        return
      }

      for await (const event of parseSSE(res)) {
        if (!mountedRef.current) break
        const data = event.parsed as Record<string, unknown> | null

        switch (event.type) {
          case 'turn_start':
            if (data?.conversation_id) convIdRef.current = String(data.conversation_id)
            onProgress?.({ type: 'thinking' })
            break
          case 'text_delta': {
            const text = typeof data === 'string' ? data : String((data as Record<string, unknown>)?.content || '')
            if (text) {
              if (!streamingStarted) {
                streamingStarted = true
                onProgress?.(null)
                onMessage?.({ type: 'start', text })
              } else {
                onMessage?.({ type: 'append', text })
              }
            }
            break
          }
          case 'tool_call': {
            const name = String((data as Record<string, unknown>)?.name || '')
            toolCallsRef.current += 1
            if (name) toolNamesRef.current[name] = (toolNamesRef.current[name] || 0) + 1
            onMessage?.({ type: 'tool', text: `[工具调用: ${name}]` })
            break
          }
          case 'tool_execution_start':
            onMessage?.({ type: 'tool', text: `[正在执行: ${String((data as Record<string, unknown>)?.name || '')}…]` })
            break
          case 'tool_execution_end':
            break
          case 'tool_result':
            break
          case 'done': {
            if (data?.conversation_id) convIdRef.current = String(data.conversation_id)
            if (mountedRef.current) {
              onProgress?.(null)
              // 工具调用轨迹（RunLedger 展示）
              onMetrics?.({
                rounds: 1,
                llm_calls: toolCallsRef.current + 1,
                tool_calls: toolCallsRef.current,
                tool_names: toolNamesRef.current,
                finish_reason: 'done',
              })
              onKnowledgeChanged?.()
            }
            break
          }
          case 'error':
            onError?.(new Error(String((data as Record<string, unknown>)?.message || '未知错误')), msg)
            break
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      onError?.(e instanceof Error ? e : new Error(String(e)), msg)
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      if (mountedRef.current) setStreaming(false)
    }
  }

  const cancel = useCallback(async () => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    // 尽力而为：告知后端取消
    try {
      await fetch('/api/chat/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: convIdRef.current || null }),
      })
    } catch { /* 静默 */ }
    setStreaming(false)
  }, [])

  return { sendMessage, cancel, streaming, conversationId: convIdRef }
}
