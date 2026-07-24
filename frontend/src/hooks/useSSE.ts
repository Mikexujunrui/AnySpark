import { useState, useRef, useEffect, useCallback } from 'react'
import { createSSE } from "../api"
import { parseSSE, isEventStream } from "../sse"

const DIAG_PREFIX = '[CONN-DIAG]'
const HEARTBEAT_MS = 300000  // 5 min — long-running tools (extract_all_chapters etc.) can take 200s+

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
      console.log(`${DIAG_PREFIX} useSSE.sendMessage — 中止之前的连接`)
      abortRef.current.abort()
    }
    clearHeartbeat()

    const controller = new AbortController()
    abortRef.current = controller

    setStreaming(true)
    const startTime = performance.now()
    console.log(`${DIAG_PREFIX} useSSE.sendMessage — 开始 | msg_len=${msg.length}`)

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
          const elapsed = Math.round(performance.now() - startTime)
          console.log(`${DIAG_PREFIX} useSSE.sendMessage — 非SSE响应完成 | %dms`, elapsed)
          return
        }

        let streamingStarted = false
        let eventCount = 0
        resetHeartbeat(controller)

        for await (const event of parseSSE(res)) {
          if (!mountedRef.current) break
          eventCount++
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
              msgText = `[!] ${msgText}`
            }

            // Always attach parts to the last streaming message, even when
            // the done text is trivial. This ensures the toggle switch for
            // tool calls / thinking process actually works.
            const parts = data.parts as unknown[] | undefined
            if (parts && mountedRef.current) {
              onMessage?.({ type: 'attach_parts', text: '', parts, metrics })
            }

            // When streaming already showed the content, skip the plain event
            // to avoid duplicate messages. The attach_parts event above already
            // handles attaching tool calls, reasoning, and chapter diffs.
            // Exception: abnormal termination — always show the [!] message
            // because the prefix adds new information not in the streamed content.
            if (streamingStarted && !isAbnormal) {
              // Skip — content already streamed
            } else if (msgText && mountedRef.current) {
              onMessage?.({ type: 'plain', text: msgText, parts: data.parts as unknown[] | undefined, metrics })
            }
            onKnowledgeChanged?.()
            streamingStarted = false

            const elapsed = Math.round(performance.now() - startTime)
            console.log(`${DIAG_PREFIX} useSSE.sendMessage — 完成 | events=${eventCount} | %dms | finish_reason=${finishReason}`,
              elapsed)
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
      if (e instanceof DOMException && e.name === 'AbortError') {
        console.log(`${DIAG_PREFIX} useSSE.sendMessage — 用户取消`)
        return
      }
      const elapsed = Math.round(performance.now() - startTime)
      console.error(`${DIAG_PREFIX} useSSE.sendMessage — 错误 | %dms | %s`, elapsed, e instanceof Error ? e.message : String(e))
      if (mountedRef.current) onError?.(e instanceof Error ? e : new Error(String(e)), msg)
    } finally {
      clearHeartbeat()
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (mountedRef.current) {
        setStreaming(false)
        console.log(`${DIAG_PREFIX} useSSE.sendMessage — streaming=false`)
      }
    }
  }

  const cancel = useCallback(async () => {
    clearHeartbeat()
    if (abortRef.current) {
      console.log(`${DIAG_PREFIX} useSSE.cancel — 中止SSE连接`)
      abortRef.current.abort()
      abortRef.current = null
    }
    try {
      await fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
      console.log(`${DIAG_PREFIX} useSSE.cancel — 取消请求已发送`)
    } catch (e) {
      console.error(`${DIAG_PREFIX} useSSE.cancel — 取消失败:`, e)
    }
    setStreaming(false)
  }, [sessionId, clearHeartbeat])

  return { sendMessage, cancel, streaming }
}
