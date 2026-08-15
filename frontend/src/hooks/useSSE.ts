import { useState, useRef, useEffect, useCallback } from 'react'
import { parseSSE } from "../sse"
import { playDone, playFail } from "../lib/sound"

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
  onQueueConsume?: (data: Record<string, unknown>) => void
  onBatchProposal?: (data: Record<string, unknown>) => void
  onSkillRefine?: (data: Record<string, unknown>) => void // S104：技能草稿生成提醒
  onError?: (error: Error, msg: string) => void
}

export interface SSEOptions {
  bookId: string
  sessionId: string
  agentMode: string
  autoModeEnabled: boolean
}

// S157：SSE 空闲超时兜底（8-15 事故修复）——后端 120s 无事件才发 error 帧，且 error 帧的
// send 可能因客户端不读而阻塞（turn2 回答生成后流中断，streaming 永久 true 锁死输入、
// 无法再发命令）。前端 90s 无任何事件 → abort 连接 + 报错解锁；后端 send 失败自动清理线程。
const IDLE_STREAM_TIMEOUT_MS = 90_000

export function useSSE({ bookId, sessionId, agentMode, onMessage, onProgress, onKnowledgeChanged, onMetrics, onQueueConsume, onBatchProposal, onSkillRefine, onError }: SSEOptions & SSECallbacks) {
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
  // S100：会话累计 token（每次 done 累加）——常驻用量条展示
  const sessionTokensRef = useRef<{ prompt_tokens: number; completion_tokens: number; total_tokens: number }>({
    prompt_tokens: 0, completion_tokens: 0, total_tokens: 0,
  })

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

    // S157：空闲计时器——每个事件重置；流挂起超时则 abort 连接（AbortError 由 catch 静默消化，
    // 错误提示已在定时器回调里给出；用户手动 cancel 走同一 abort 路径但不报错）
    let idleTimer: ReturnType<typeof setTimeout> | null = null
    const resetIdle = () => {
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        idleTimer = null
        if (mountedRef.current) {
          onError?.(new Error('流式响应空闲超时（90 秒无数据），连接已中断，请重试。'), msg)
          controller.abort()
        }
      }, IDLE_STREAM_TIMEOUT_MS)
    }
    resetIdle()

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
        resetIdle()  // 每个事件重置空闲计时（模型思考/工具执行期也可达数十秒）
        const data = event.parsed as Record<string, unknown> | null

        switch (event.type) {
          case 'turn_start':
            if (data?.conversation_id) convIdRef.current = String(data.conversation_id)
            // S98：轮次信息（core turn_start 带 turn_index/max_iterations）
            turnRef.current = Number((data as Record<string, unknown>)?.turn_index) || turnRef.current + 1
            maxTurnsRef.current = Number((data as Record<string, unknown>)?.max_iterations) || maxTurnsRef.current
            // S100：软警告——接近轮次上限（剩 3 轮内）提示即将收尾（pi turnBudget soft 语义）
            const nearLimit = maxTurnsRef.current > 0 && turnRef.current >= maxTurnsRef.current - 3
            progressNow(
              '正在思考…',
              nearLimit
                ? `第 ${turnRef.current}/${maxTurnsRef.current} 轮（⚠️ 接近上限，即将收尾）`
                : `第 ${turnRef.current} 轮规划`
            )
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
              // S102：批量工具（提议模式）——提取参数回调给宿主弹批准窗
              const argsList = (data as Record<string, unknown>)?.arguments
              if (onBatchProposal && Array.isArray(argsList)) {
                nameList.forEach((n: string, i: number) => {
                  if (n === 'batch_rewrite' || n === 'batch_review') {
                    onBatchProposal({ name: n, arguments: argsList[i] || {} })
                  }
                })
              }
              // S104：技能草稿生成提醒（skill_refine 产出 → 弹窗确认）
              if (onSkillRefine && Array.isArray(argsList)) {
                nameList.forEach((n: string) => {
                  if (n === 'skill_refine') onSkillRefine({ name: n })
                })
              }
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
            // S155：整个循环彻底结束 → 完成提示音（主人要求：主循环只在彻底结束时响）
            playDone()
            if (data?.conversation_id) convIdRef.current = String(data.conversation_id)
            if (mountedRef.current) {
              onProgress?.(null)
              // S82：done 帧附本轮 parts（工具调用卡片 + 思考过程）——attach 到消息渲染
              const parts = (data as Record<string, unknown>)?.parts
              if (Array.isArray(parts) && parts.length > 0) {
                onMessage?.({ type: 'attach_parts', text: '', parts })
              }
              // 工具调用轨迹（RunLedger 展示）
              const usage = (data as Record<string, unknown>)?.token_usage
              // S100：会话累计 token（常驻用量条）
              if (usage && typeof usage === 'object') {
                const u = usage as Record<string, number>
                sessionTokensRef.current.prompt_tokens += u.prompt_tokens || 0
                sessionTokensRef.current.completion_tokens += u.completion_tokens || 0
                sessionTokensRef.current.total_tokens += u.total_tokens || 0
              }
              // S99 第二步：done 帧带 rounds（接力总轮数），替换硬编码 1
              const rounds = Number((data as Record<string, unknown>)?.rounds) || 1
              onMetrics?.({
                rounds,
                llm_calls: toolCallsRef.current + 1,
                tool_calls: toolCallsRef.current,
                tool_names: toolNamesRef.current,
                finish_reason: 'done',
                // S99：token 消耗（后端汇总每轮 usage，如 {prompt_tokens, completion_tokens, total_tokens}）
                tokens: usage && typeof usage === 'object'
                  ? (usage as Record<string, number>)
                  : undefined,
                // S100：会话累计 token + 模型名（常驻用量条 / 成本估算）
                session_tokens: { ...sessionTokensRef.current },
                model: String((data as Record<string, unknown>)?.model || ''),
              })
              onKnowledgeChanged?.()
            }
            break
          }
          case 'queue_consume': {
            // S99 第二步：接力轮开始——前端把该文本作为 user 消息显示、队列条同步减少
            onQueueConsume?.(data as Record<string, unknown>)
            break
          }
          case 'error':
            playFail()  // S155：失败提示音
            onError?.(new Error(String((data as Record<string, unknown>)?.message || '未知错误')), msg)
            break
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      onError?.(e instanceof Error ? e : new Error(String(e)), msg)
    } finally {
      if (idleTimer) clearTimeout(idleTimer)
      idleTimer = null
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
