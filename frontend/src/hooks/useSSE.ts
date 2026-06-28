import { useState, useRef, useEffect, useCallback } from 'react'
import { createSSE } from "../api"
import { parseSSE, isEventStream } from "../sse"

const HEARTBEAT_MS = 30000

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

export function useSSE({ bookId, sessionId, agentMode, autoModeEnabled, onMessage, onProgress, onPlotCards, onQuestion, onWriting, onTaskList, onWorkflow, onPatch, onKnowledgeChanged, onCorrection, onMetrics, onError }: SSEOptions & SSECallbacks) {
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const heartbeatRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearTimeout(heartbeatRef.current)
      heartbeatRef.current = null
    }
  }, [])

  const resetHeartbeat = useCallback((controller: AbortController) => {
    clearHeartbeat()
    heartbeatRef.current = setTimeout(() => {
      controller.abort()
    }, HEARTBEAT_MS)
  }, [clearHeartbeat])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      clearHeartbeat()
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [clearHeartbeat])

  async function sendMessage(msg: string) {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    clearHeartbeat()

    const controller = new AbortController()
    abortRef.current = controller

    setStreaming(true)
    try {
      const res = await createSSE('/api/chat', {
        message: msg,
        book_id: bookId,
        mode: agentMode,
        session_id: sessionId,
        auto_mode_enabled: autoModeEnabled,
      }, controller.signal)

      if (msg.startsWith('/w ') || msg.startsWith('/ws ')) {
        if (res.headers.get('content-type')?.includes('text/event-stream')) {
          let started = false
          resetHeartbeat(controller)
          for await (const event of parseSSE(res)) {
            if (!mountedRef.current) break
            resetHeartbeat(controller)
            const text = event.type === 'chunk'
              ? (typeof event.parsed === 'string' ? event.parsed : ((event.parsed as Record<string, unknown>)?.text as string) || event.data || '')
              : ''
            if (text) {
              if (!started) {
                started = true
                onMessage?.({ type: 'start', text })
              } else {
                onMessage?.({ type: 'append', text })
              }
            }
          }
          if (started && mountedRef.current) onKnowledgeChanged?.()
        }
      } else {
        if (!isEventStream(res)) {
          const data = await res.json()
          if (mountedRef.current) onMessage?.({ type: 'plain', text: data.message || '完成' })
          return
        }

        let streamingStarted = false
        resetHeartbeat(controller)

        for await (const event of parseSSE(res)) {
          if (!mountedRef.current) break
          resetHeartbeat(controller)
          const data = event.parsed as Record<string, unknown> | null
          const rawData = event.data || ''

          if (event.type === 'chunk') {
            const text = typeof data === 'string' ? data : ((data as Record<string, unknown>)?.text as string) || rawData
            if (!streamingStarted) {
              streamingStarted = true
              onProgress?.(null)
              onMessage?.({ type: 'start', text })
            } else {
              onMessage?.({ type: 'append', text })
            }
            continue
          }

          if (!data) continue

          if (event.type === 'progress') {
            onProgress?.(data as Record<string, unknown>)
          } else if (event.type === 'done') {
            onProgress?.(null)
            const metrics = data.metrics as Record<string, unknown> | undefined
            const finishReason = (metrics?.finish_reason as string) || ''
            // 大厂做法：finish_reason 驱动差异化展示。异常终态加标记并强制显示，
            // 确保用户始终知晓为何停止（不再被 trivial 过滤静默吞掉）。
            const ABNORMAL_REASONS = ['llm_error', 'llm_empty', 'abnormal_exit', 'token_budget_reached', 'round_limit_reached', 'task_incomplete_done']
            const isAbnormal = ABNORMAL_REASONS.includes(finishReason)
            let msgText = data.totalEntities || data.totalRelations
              ? `${(data.message as string) || ''}\n实体: ${data.totalEntities || 0}  |  关系: ${data.totalRelations || 0}  |  伏笔: ${data.totalForeshadows || 0}`
              : (data.message as string) || ''
            if (isAbnormal && msgText) {
              msgText = `⚠️ ${msgText}`
            }
            // 正常终态：仅当 message 是无信息占位符且已有流式输出时才吞掉。
            // 异常终态永远显示。
            const isTrivial = !msgText || msgText === '完成' || msgText === '操作已取消' || msgText === '⚠️ 完成' || msgText === '⚠️ 操作已取消'
            if (!isTrivial || !streamingStarted || isAbnormal) {
              if (msgText && mountedRef.current) onMessage?.({ type: 'plain', text: msgText, parts: data.parts as unknown[] | undefined, metrics })
            }
            onKnowledgeChanged?.()
            streamingStarted = false
          } else if (event.type === 'plot_cards') {
            onProgress?.(null)
            onPlotCards?.(data as Record<string, unknown>)
          } else if (event.type === 'question') {
            onProgress?.(null)
            onQuestion?.(data as Record<string, unknown>)
          } else if (event.type === 'writing') {
            onWriting?.(data as Record<string, unknown>)
          } else if (event.type === 'task_list') {
            onTaskList?.(data as Record<string, unknown>)
          } else if (event.type === 'workflow') {
            onWorkflow?.(data as Record<string, unknown>)
          } else if (event.type === 'patch_result') {
            onPatch?.(data as Record<string, unknown>)
          } else if (event.type === 'writing_end') {
            onWriting?.({ type: 'end', ...data } as Record<string, unknown>)
            onKnowledgeChanged?.()
          } else if (event.type === 'chapter_updated') {
            onKnowledgeChanged?.()
          } else if (event.type === 'text-correction') {
            onCorrection?.(data as Record<string, unknown>)
          } else if (event.type === 'agent_metrics') {
            onMetrics?.(data as Record<string, unknown>)
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      if (mountedRef.current) onError?.(e instanceof Error ? e : new Error(String(e)), msg)
    } finally {
      clearHeartbeat()
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (mountedRef.current) setStreaming(false)
    }
  }

  const cancel = useCallback(async () => {
    clearHeartbeat()
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    try {
      await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
    } catch (e) {
      console.error('Cancel failed:', e)
    }
    setStreaming(false)
  }, [sessionId, clearHeartbeat])

  return { sendMessage, cancel, streaming }
}
