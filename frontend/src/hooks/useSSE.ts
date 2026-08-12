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
  // S98：步骤进度——轮次（turn_index/max_iterations）+ 已完成工具步骤数（真实计数，非猜测）
  const turnRef = useRef(0)
  const maxTurnsRef = useRef(0)
  const doneStepsRef = useRef(0)

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
    turnRef.current = 0
    maxTurnsRef.current = 0
    doneStepsRef.current = 0
    let streamingStarted = false

    // S98：带轮次/步骤计数的进度（ProgressIndicator 用真实轮次进度 + 工具完成数）
    const progressNow = (stage: string, detail?: string) => onProgress?.({
      stage,
      detail,
      turnIndex: turnRef.current,
      maxIterations: maxTurnsRef.current,
      doneSteps: doneStepsRef.current,
    })

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          conversation_id: sessionId || undefined,
          book_id: bookId || undefined, // S80：智能体作用域=打开的项目
          // 不传 model_id：后端用默认激活模型（避免 'write' 等假模型名）
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
            // S98：轮次信息（core turn_start 带 turn_index/max_iterations）
            turnRef.current = Number((data as Record<string, unknown>)?.turn_index) || turnRef.current + 1
            maxTurnsRef.current = Number((data as Record<string, unknown>)?.max_iterations) || maxTurnsRef.current
            progressNow('正在思考…', `第 ${turnRef.current} 轮规划`)
            break
          case 'text_delta': {
            const text = typeof data === 'string' ? data : String((data as Record<string, unknown>)?.content || '')
            if (text) {
              if (!streamingStarted) {
                streamingStarted = true
                // S98：正文开始不隐藏进度条，阶段转「生成正文」（可能还有后续轮次调工具）
                progressNow('生成正文', '')
                onMessage?.({ type: 'start', text })
              } else {
                onMessage?.({ type: 'append', text })
              }
            }
            break
          }
          case 'tool_call': {
            const names = (data as Record<string, unknown>)?.name
            const name = Array.isArray(names) ? names.join(', ') : String(names || '')
            toolCallsRef.current += 1
            if (name) {
              const nameList = Array.isArray(names) ? names : [name]
              nameList.forEach((n: string) => { if (n) toolNamesRef.current[n] = (toolNamesRef.current[n] || 0) + 1 })
              onMessage?.({ type: 'tool', text: `[工具调用: ${name}]` })
              progressNow('调用工具', `${name}…`)
            }
            break
          }
          case 'tool_execution_start': {
            const tname = String((data as Record<string, unknown>)?.name || '')
            onMessage?.({ type: 'tool', text: `[正在执行: ${tname}…]` })
            progressNow('正在执行', `${tname}…`)
            break
          }
          case 'tool_execution_end': {
            // S98：工具步骤完成计数（仅 ok 计入）
            if ((data as Record<string, unknown>)?.ok) doneStepsRef.current += 1
            progressNow('正在执行', `${String((data as Record<string, unknown>)?.name || '')} 完成`)
            break
          }
          case 'tool_result':
            break
          case 'done': {
            if (data?.conversation_id) convIdRef.current = String(data.conversation_id)
            if (mountedRef.current) {
              onProgress?.(null)
              // S82：done 帧附本轮 parts（工具调用卡片 + 思考过程）——attach 到消息渲染
              const parts = (data as Record<string, unknown>)?.parts
              if (Array.isArray(parts) && parts.length > 0) {
                onMessage?.({ type: 'attach_parts', text: '', parts })
              }
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
