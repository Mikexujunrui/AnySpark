import { useState, useRef, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import { useApproval } from './approval/ApprovalContext'
import { SLASH_COMMANDS as COMMAND_REGISTRY, handleSlashInput } from '../lib/commands'
import { useSSE } from "../hooks/useSSE"
import MessageList from './chat/MessageList'
import MessageInput from './chat/MessageInput'
import ContextBar from './chat/ContextBar'
import UsageStrip from './chat/UsageStrip'
import WritingPreview from './chat/WritingPreview'
import TaskListPanel from './chat/TaskListPanel'
import WorkflowProgress from './chat/WorkflowProgress'
import ConfirmModal from './ui/ConfirmModal'
import RunLedger from './chat/RunLedger'
import AutopilotConsole from './chat/AutopilotConsole'
import { api } from "../api"
import { triggerRefresh } from "../store"
import { enqueueChat, dequeueChat, steerQueuedChat, steerChat, fetchQueues, type QueueItem } from '../api/chat'
import { listWorkflows, runWorkflow, getWorkflowTask } from '../api/workflow'
import { listChapters } from '../api/chapters'
import { runCheck } from '../api/check'
import { listSkillDrafts, promoteSkillDraft, deleteSkillDraft } from '../api/skills'

const DIAG_PREFIX = '[CONN-DIAG]'

// ── Autopilot noise filter ──
// Autopilot status messages are persisted as user/agent pairs with
// user text "[autopilot]" or "[autopilot 干预] ...", or as standalone
// agent messages with autopilot:true. Filter them out so the chat history
// stays clean.
function filterAutopilotNoise(messages: { role: string; text: string; autopilot?: boolean }[]): typeof messages {
  return messages.filter((_msg, i, arr) => {
    // S107：过滤历史遗留的空气泡——agent 工具轮空文本被持久化（无文本无 parts 的纯空消息）
    if (_msg.role === 'agent' && !(_msg.text || '').trim() && !((_msg as any).parts && (_msg as any).parts.length)) {
      return false
    }
    // Standalone autopilot agent message (autopilot:true flag)
    if ((_msg as any).autopilot === true) return false
    // User message starting with "[autopilot]" → skip the pair
    if (_msg.role === 'user' && _msg.text?.startsWith('[autopilot]')) return false
    // Agent message that follows an autopilot user message
    if (i > 0 && arr[i - 1].role === 'user' && arr[i - 1].text?.startsWith('[autopilot]')) return false
    return true
  })
}

// ── SSE chunk throttling: batch append updates to avoid per-chunk re-renders ──
const CHUNK_FLUSH_MS = 50  // flush buffered chunks at most every 50ms
export default function ChatPanel({ bookId, sessionId, autoModeEnabled, transformSignal }: { bookId: string; sessionId: string; autoModeEnabled: boolean; transformSignal: number }) {
  const { setAutoMode: setGlobalAutoMode, requestApproval } = useApproval()
  const welcomeMsg = { role: 'agent', text: '你好！我是你的 AI 写作助手 Agent。\n\n'
    + '在输入框输入 `/` 可查看命令菜单。\n\n'
    + '**命令分两类**：\n'
    + '· UI 命令（`/tree` 叙事树、`/graph` 图谱、`/outline` 大纲、`/review` 评审…）——直接打开面板，不经 AI\n'
    + '· AI 命令（`/w` 写作、`/s` 提取设定、`/style` 文风…）——翻译为明确指令交给 AI\n'
    + '自然语言描述则走 Agent 智能路由。' }

  const [messages, setMessages] = useState([welcomeMsg])
  const [loaded, setLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(null)
  const [question, setQuestion] = useState(null)
  const [plotCards, setPlotCards] = useState(null)
  const [showSlash, setShowSlash] = useState(false)
  const [slashFilter, setSlashFilter] = useState('')
  const [slashIdx, setSlashIdx] = useState(0)
  const [skillCommands, setSkillCommands] = useState([])
  const [contextUsage, setContextUsage] = useState(null)
  const [showAutopilotCancel, setShowAutopilotCancel] = useState(false)
  const [writingState, setWritingState] = useState(null)
  const [sidePanelWidth, setSidePanelWidth] = useState(45)
  const [taskList, setTaskList] = useState(null)
  const [workflowData, setWorkflowData] = useState(null)
  const [patchData, setPatchData] = useState(null)
  const [metrics, setMetrics] = useState(null)  // Agent run metrics for Run Ledger
  const [revertIdx, setRevertIdx] = useState(null)
  const [autopilotState, setAutopilotState] = useState(null)
  const [autopilotBridge, setAutopilotBridge] = useState(null)
  const autopilotAbortRef = useRef(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [autonomousMode, setAutonomousMode] = useState(false)
  const [showToolCalls, setShowToolCalls] = useState(true)  // toggle for tool call / thinking display
  // S99：会话消息队列（排队接力第一步——排队/查看/删/转插入；接力执行=第二步）
  const [pendingQueue, setPendingQueue] = useState<QueueItem[]>([])
  // S102：批量提议（agent 调 batch_rewrite/batch_review 后待批准弹窗）
  const batchProposalRef = useRef<{ name: string; arguments: Record<string, unknown> } | null>(null)
  // S104：技能草稿生成（agent 调 skill_refine 后弹窗确认采纳）
  const skillRefineRef = useRef<boolean>(false)
  const saveTimerRef = useRef(null)
  const hideTimerRef = useRef(null)
  const lastSentMsgRef = useRef('')
  // ── Chunk buffering: avoid per-chunk setMessages during streaming ──
  const chunkBufferRef = useRef('')
  const chunkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const streamingRef = useRef(false)

  const flushChunks = useCallback(() => {
    const text = chunkBufferRef.current
    if (!text) return
    chunkBufferRef.current = ''
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (last && last.role === 'agent') {
        updated[updated.length - 1] = { ...last, text: last.text + text }
      }
      return updated
    })
  }, [])

  const { sendMessage: sseSend, cancel: sseCancel, streaming } = useSSE({
    bookId,
    sessionId,
    agentMode: 'write',
    autoModeEnabled,
    onMessage: (event) => {
      if (event.type === 'start') {
        streamingRef.current = true
        if (event.text) setMessages(prev => [...prev, { role: 'agent', text: event.text }])
      } else if (event.type === 'append') {
        if (event.text) {
          // Buffer chunks and flush at throttled rate to avoid per-chunk re-renders
          chunkBufferRef.current += event.text
          if (!chunkTimerRef.current) {
            chunkTimerRef.current = setTimeout(() => {
              chunkTimerRef.current = null
              flushChunks()
            }, CHUNK_FLUSH_MS)
          }
        }
      } else if (event.type === 'plain') {
        if (event.text) {
          setMessages(prev => [...prev, {
            role: 'agent',
            text: event.text,
            parts: event.parts,
            metrics: event.metrics,
          }])
        }
      } else if (event.type === 'tool') {
        // V4 工具调用轨迹（精简展示：不污染正文流）
        if (event.text) {
          setMessages(prev => [...prev, { role: 'tool', text: event.text }])
        }
      } else if (event.type === 'attach_parts') {
        // Attach parts to the last streaming agent message
        // (e.g. tool calls, reasoning, chapter diffs from the done event).
        // This fires even when the done text is trivial, so the showToolCalls
        // toggle always has data to work with.
        if (event.parts || event.metrics) {
          setMessages(prev => {
            const updated = [...prev]
            // S82：从末尾往前找最后一条 agent 消息（末尾可能是 tool 提示消息）
            let idx = updated.length - 1
            while (idx >= 0 && updated[idx].role !== 'agent') idx--
            if (idx >= 0) {
              const target = updated[idx] as any
              updated[idx] = {
                ...target,
                parts: event.parts || target.parts,
                metrics: event.metrics || target.metrics,
              }
            }
            return updated
          })
        }
        if (event.metrics) {
          setMetrics(event.metrics)
        }
      }
    },
    onProgress: setProgress,
    onPlotCards: setPlotCards,
    onQuestion: setQuestion,
    onWriting: (data) => {
      if (data.type === 'start') {
        // Writing started — set up preview and add chat notification
        setWritingState({ chapterTitle: data.chapter_title, text: '', saved: false })
        setMessages(prev => [...prev, { role: 'agent', text: `[写作] 开始: ${data.chapter_title}（见右侧预览）` }])
      } else if (data.type === 'end') {
        const saved = Boolean(data.saved)
        const error = String(data.error || '')
        setWritingState(prev => ({
          ...(prev || {}),
          chapterTitle: data.chapter_title || prev?.chapterTitle,
          saved,
          failed: !saved,
          error,
          wordCount: data.word_count,
          partial: data.partial,
        }))
        const status = saved ? (data.partial ? '[部分保存]' : '[已保存]') : '[写作失败·未保存]'
        const detail = saved
          ? `到 ${data.chapter_title || '章节'}，共 ${data.word_count || 0} 字`
          : (error || '写作工具未生成可保存的章节')
        setMessages(prev => [...prev, { role: 'agent', text: `${status} ${detail}` }])
        clearTimeout(hideTimerRef.current)
        if (saved) {
          hideTimerRef.current = setTimeout(() => {
            setWritingState(null)
            setTaskList(null)
          }, 5000)
        }
      } else if (data.text) {
        // Streaming chunk — append to preview
        setWritingState(prev => prev ? { ...prev, text: prev.text + data.text } : null)
      }
    },
    onTaskList: (data) => {
      const items = (data as Record<string, unknown[]>).items || []
      setTaskList(items as any[])
      clearTimeout(hideTimerRef.current)
      if (items.length > 0 && items.every((i: any) => i.status === 'done' || i.status === 'skipped' || i.status === 'failed')) {
        hideTimerRef.current = setTimeout(() => setTaskList(null), 6000)
      }
    },
    onWorkflow: (data) => {
      setWorkflowData(data)
      // Keep workflow visible during execution
      clearTimeout(hideTimerRef.current)
      // Auto-hide 8 seconds after workflow completes
      if (data.action === 'done') {
        hideTimerRef.current = setTimeout(() => setWorkflowData(null), 8000)
      }
    },
    onPatch: (data) => {
      setPatchData(data)
      // Auto-hide after 10 seconds
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = setTimeout(() => setPatchData(null), 10000)
    },
    onKnowledgeChanged: triggerRefresh,
    onCorrection: (data) => {
      // Replace misleading pre-tool-call text with a warning
      setMessages(prev => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'agent') {
          updated[updated.length - 1] = {
            ...last,
            text: `_模型在操作前输出了误导性文字，已纠正。实际工具调用正在执行中..._`,
            corrected: true,
          } as typeof last
        }
        return updated
      })
    },
    onError: (e, msg) => {
      let errorText = '⚠️ 请求失败，请检查后端'
      if (msg?.startsWith('/s ')) errorText = '⚠️ 提取失败'
      if (msg?.startsWith('/w ') || msg?.startsWith('/ws ')) errorText = '⚠️ 连接出错，请重试'
      const detail = e?.message?.trim()
      if (detail) errorText = `${errorText}\n\n${detail}`
      setMessages(prev => [...prev, { role: 'agent', text: errorText, retry: true }])
    },
    onMetrics: (data) => {
      setMetrics(data)
    },
    // S99 第二步：接力轮开始——把队列消息作为 user 消息显示、队列条同步减少
    onQueueConsume: (data) => {
      const text = String((data as Record<string, unknown>)?.text || '')
      if (text) {
        setMessages(prev => [...prev, { role: 'user', text }])
      }
      setPendingQueue(prev => prev.slice(1))
    },
    // S102：批量提议——记住最新申请，等本轮结束后弹批准窗
    onBatchProposal: (data) => {
      const name = String((data as Record<string, unknown>)?.name || '')
      const args = (data as Record<string, unknown>)?.arguments as Record<string, unknown> | undefined
      if (name && args) batchProposalRef.current = { name, arguments: args }
    },
    // S104：技能草稿生成 → 本轮结束后弹确认窗
    onSkillRefine: () => {
      skillRefineRef.current = true
    },
  })

  // ── Global Escape key to cancel streaming ──
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape' && streaming) {
        e.preventDefault()
        handleCancel()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [streaming])

  // ── Cancel session on page unload (refresh / close) ──
  useEffect(() => {
    function onBeforeUnload() {
      if (streaming && sessionId) {
        // Use sendBeacon for reliable delivery during page unload
        navigator.sendBeacon(`/api/chat/cancel`, new Blob([JSON.stringify({ conversation_id: sessionId })], { type: 'application/json' }))
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [streaming, sessionId])


  // 命令注册表驱动（真正的命令系统：ui 前端执行 / ai 翻译指令）
  const slashItems = COMMAND_REGISTRY
    .filter(c => slashFilter === '' || c.cmd.toLowerCase().includes(slashFilter.toLowerCase()))
    .map(c => ({ name: '/' + c.cmd, description: c.desc, usage: c.usage || ('/' + c.cmd) }))

  // Load history on session mount
  useEffect(() => {
    setMessages([welcomeMsg])
    setLoaded(false)
    if (!sessionId) return
    const url = `/api/conversations/${sessionId}/messages`
    console.log(`${DIAG_PREFIX} ChatPanel — 加载历史消息 | session=%s | url=%s`, sessionId, url)
    fetch(url)
      .then(r => {
        console.log(`${DIAG_PREFIX} ChatPanel — 历史消息响应 | status=%d | content-type=%s`, r.status, r.headers.get('content-type'))
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        const isArray = Array.isArray(data)
        const count = isArray ? data.length : 0
        console.log(`${DIAG_PREFIX} ChatPanel — 历史消息解析完成 | isArray=%s | count=%d | type=%s`,
          isArray, count, typeof data)
        if (isArray && count > 0) {
          // S107b：后端返回 {role, content}，前端渲染用 {role, text}——映射字段（历史恢复空气泡根因）
          const mapped = data
            .map((m: any) => ({ ...m, text: (m.content ?? m.text ?? '') }))
            // S145b：过滤空文本消息（工具轮 assistant 声明/历史残留）——防空气泡兜底
            .filter((m: any) => m.role !== 'agent' || (m.text && m.text.trim().length > 0))
          // Filter autopilot status messages (user text starts with "[autopilot]")
          // These are internal status records, not real user messages.
          const filtered = filterAutopilotNoise(mapped)
          // S145b：历史里陈旧的"[批量X执行中]"消息 = 轮询中断残留（任务实际早已结束，
          // done 会更新为完成态；没更新说明刷新/切页中断了轮询）——纠正为结束提示，
          // 避免重开后误以为任务还在 running
          const corrected = filtered.map((m: any) => {
            const t = String(m.text || '')
            if (m.role === 'agent' && /^\[批量(改写|审读)执行中\]/.test(t)) {
              return { ...m, text: t.replace(/^\[批量(改写|审读)执行中\]/, '[批量$1任务已结束（详情见批量面板）]') }
            }
            return m
          })
          if (corrected.length > 0) setMessages(corrected)
        }
        setLoaded(true)
      })
      .catch(e => {
        console.error(`${DIAG_PREFIX} ChatPanel — 历史消息加载失败: %s`, e.message)
        setLoaded(true)
      })
  }, [bookId, sessionId])

  // S99：会话切换时拉取该会话的排队消息
  useEffect(() => {
    if (!sessionId) return
    fetchQueues()
      .then(s => setPendingQueue(s.queues[sessionId] || []))
      .catch(() => { /* 静默：队列拉取失败不影响主流程 */ })
  }, [sessionId])

  // Auto-save debounce
  useEffect(() => {
    if (!loaded || !sessionId) return
    clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      fetch(`/api/conversations/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: messages.map(m => ({ role: m.role === 'agent' ? 'assistant' : m.role, content: m.text || '' })) }),
      }).catch(e => console.error(`${DIAG_PREFIX} ChatPanel — 消息保存失败: %s`, e.message))
    }, 500)
    return () => clearTimeout(saveTimerRef.current)
  }, [messages, bookId, sessionId, loaded])

  // S80：context 用量统计后端无此端点，移除（ContextBar 已能处理 null）

  async function handleUpload(file) {
    if (!file || uploading) return
    setUploading(true)

    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    console.log(`${DIAG_PREFIX} ChatPanel — 上传文件 | name=%s | size=%sMB`, file.name, sizeMB)
    setMessages(prev => [...prev,
      { role: 'user', text: `[上传] 上传文档: ${file.name} (${sizeMB} MB)` },
    ])

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('session_id', sessionId)

      const res = await fetch(`/api/books/${bookId}/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      console.log(`${DIAG_PREFIX} ChatPanel — 上传完成 | status=%d`, res.status)
      setMessages(prev => [...prev, {
        role: 'agent',
        text: `[完成] ${data.message}\n\n现在可以给我指令处理这个文件，例如：\n• "帮我把第1章拆解并复写"\n• "提取这个文件的全部设定"\n• "分析这个小说的文风特征"`,
      }])
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 上传失败: %s`, e.message)
      setMessages(prev => [...prev, { role: 'agent', text: `上传失败: ${e.message}` }])
    }
    setUploading(false)
  }

  async function handleValidate(text) {
    setMessages(prev => [...prev, { role: 'agent', text: '正在校验内容与知识库的一致性...' }])
    try {
      // S145（第三方评审 P0-2）：此前调 /api/books/{bookId}/validate——后端无此路由，
      // 点击必 404。改为接真实能力 /api/check（多检测者审读 + 图谱证据 + 时序校验）。
      const result = await runCheck(text, '当前章节')
      const lines = []
      if (result.hard_count === 0 && result.findings.length === 0 && !result.temporal_warnings?.length) {
        lines.push('✅ 校验通过，未发现与知识库的硬伤冲突')
      } else {
        if (result.hard_count > 0) {
          lines.push(`发现 ${result.hard_count} 处硬伤：`)
          for (const f of result.findings) {
            if (f.severity === 'hard') lines.push(`  · [${f.category}] ${f.message}`)
          }
        }
        for (const f of result.findings) {
          if (f.severity !== 'hard') lines.push(`  [${f.category}] ${f.message}`)
        }
      }
      for (const w of (result.temporal_warnings || [])) {
        lines.push(`  ⏱ 时序警告: ${w}`)
      }
      if (result.graph_evidence) {
        lines.push(`\n图谱证据：\n${result.graph_evidence.slice(0, 500)}`)
      }
      if (lines.length === 1) {
        lines.push('（无其他发现项）')
      }
      setMessages(prev => [...prev, { role: 'agent', text: lines.join('\n') }])
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 校验失败: %s`, e.message)
      setMessages(prev => [...prev, { role: 'agent', text: '校验失败，请重试' }])
    }
  }

  async function handleQuestionReply(answers) {
    if (!question) return
    const qid = question.id
    setProgress({ stage: "处理中...", detail: "已收到你的选择" })
    try {
      await fetch(`/api/books/${bookId}/questions/${qid}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      })
      setQuestion(null)
      setProgress(null) // Clear progress — let backend SSE events drive updates
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 问题回复失败: %s`, e.message)
      setProgress({ stage: "提交失败", detail: "请重试" })
    }
  }

  async function handleQuestionReject() {
    if (!question) return
    const qid = question.id
    try {
      await fetch(`/api/books/${bookId}/questions/${qid}/reject`, { method: 'POST' })
      setQuestion(null)
      setMessages(prev => [...prev, { role: 'agent', text: '已取消。' }])
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 问题拒绝失败: %s`, e.message)
      setProgress({ stage: "提交失败", detail: "请重试" })
    }
  }

  async function handlePlotCardSelect(text) {
    if (!plotCards) return
    const qid = plotCards.id
    setProgress({ stage: "处理中...", detail: "已收到你的选择" })
    setMessages(prev => [...prev, { role: 'user', text: `选择方向: ${text.slice(0, 100)}${text.length > 100 ? '...' : ''}` }])
    try {
      await fetch(`/api/books/${bookId}/questions/${qid}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers: [[text]] }),
      })
      setPlotCards(null)
      setProgress(null) // Clear progress — let backend SSE events drive updates
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 剧情卡片选择失败: %s`, e.message)
      setProgress({ stage: "提交失败", detail: "请重试" })
    }
  }

  async function handlePlotCardReject() {
    if (!plotCards) return
    const qid = plotCards.id
    try {
      await fetch(`/api/books/${bookId}/questions/${qid}/reject`, { method: 'POST' })
      setPlotCards(null)
      setMessages(prev => [...prev, { role: 'user', text: '拒绝所有选项，请重新引导' }])
    } catch (e) {
      console.error(`${DIAG_PREFIX} ChatPanel — 剧情卡片拒绝失败: %s`, e.message)
      setProgress({ stage: "提交失败", detail: "请重试" })
    }
  }

  function handleRevert(idx) {
    setRevertIdx(idx)
  }

  function confirmRevert() {
    const msg = messages[revertIdx]
    setMessages(prev => prev.slice(0, revertIdx))
    setInput(msg.text || '')
    setRevertIdx(null)
  }

  function handleEdit(idx, newText) {
    setMessages(prev => {
      const updated = [...prev]
      const msg = { ...updated[idx] }
      msg.text = newText
      // Also update final_text for structured Turn records
      // so LLM context reconstruction uses the edited version
      if ((msg as any).final_text !== undefined) {
        (msg as any).final_text = newText
      }
      updated[idx] = msg
      return updated
    })
  }

  function handleSlashSelect(s) {
    const name = s.name.replace(/^\//, '')  // 去掉 / 前缀
    const cmd = COMMAND_REGISTRY.find(c => c.cmd === name)
    if (cmd && cmd.type === 'ui') {
      // UI 命令：选中直接执行（不填输入框）
      handleSlashInput('/' + name)
      setInput('')
      setShowSlash(false)
      setSlashIdx(0)
      return
    }
    // AI 命令：填 usage 让用户补参数
    setInput(s.usage ? (s.usage + ' ') : ('/' + s.name + ' '))
    setShowSlash(false)
    setSlashIdx(0)
  }

  async function sendMessage() {
    if (!input.trim() || streaming || question || plotCards) return
    const raw = input.trim()
    // 真正的命令系统：UI 命令前端执行（不经过 AI），AI 命令翻译为明确指令
    const { consumed, send } = handleSlashInput(raw)
    if (consumed && !send) {
      // UI 命令已在前端执行（如切 tab），无需发消息
      setInput('')
      setShowSlash(false)
      setSlashFilter('')
      return
    }
    const msg = send || raw
    setInput('')
    setShowSlash(false)
    setSlashFilter('')
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setMetrics(null)  // Reset metrics from previous run
    lastSentMsgRef.current = msg

    // ── Autopilot intervention routing ──
    if (autopilotState && autopilotState.status === 'running') {
      // Intervention detected: send through normal chat (backend handles routing)
      await sseSend(msg)
      setProgress(null)
      return
    }

    if (msg.startsWith('/s ')) {
      setProgress({ stage: "开始提取...", detail: "" })
    }

    await sseSend(msg)
    setProgress(null)
  }

  // ── S99 队列操作：排队（回车） / 插入指导 / 删队 / 转插入 ──
  async function handleQueue() {
    const msg = input.trim()
    if (!msg || !sessionId) return
    try {
      const res = await enqueueChat(sessionId, msg)
      setPendingQueue(res.queue)
      setInput('')
      setShowSlash(false)
      setSlashFilter('')
    } catch {
      setMessages(prev => [...prev, { role: 'agent', text: '⚠️ 排队失败，请检查后端' }])
    }
  }

  async function handleSteer() {
    const msg = input.trim()
    if (!msg || !sessionId) return
    try {
      await steerChat(sessionId, msg)
      setInput('')
      setShowSlash(false)
      setSlashFilter('')
      setMessages(prev => [...prev, { role: 'agent', text: `[已插入指导] ${msg}` }])
    } catch {
      setMessages(prev => [...prev, { role: 'agent', text: '⚠️ 插入失败：会话可能已结束（可等它完成后直接发送）' }])
    }
  }

  async function handleDequeue(itemId: string) {
    if (!sessionId) return
    try {
      const res = await dequeueChat(sessionId, itemId)
      setPendingQueue(res.queue)
    } catch { /* 静默 */ }
  }

  async function handleSteerQueued(itemId: string) {
    if (!sessionId) return
    try {
      const res = await steerQueuedChat(sessionId, itemId)
      if (res.queue) setPendingQueue(res.queue)
      if (!res.ok) {
        setMessages(prev => [...prev, { role: 'agent', text: `⚠️ 转插入失败：${res.reason || '未知原因'}（已保留在队列）` }])
      }
    } catch { /* 静默 */ }
  }

  // ── S102 批量批准：本轮结束有批量提议 → 弹窗 → 批准执行 + 轮询进度 ──
  useEffect(() => {
    if (streaming || !batchProposalRef.current) return
    const proposal = batchProposalRef.current
    batchProposalRef.current = null  // 防重复弹
    void handleBatchProposal(proposal)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming])

  // ── S104 技能草稿确认：本轮结束 skill_refine 生成过草稿 → 弹窗采纳/拒绝 ──
  useEffect(() => {
    if (streaming || !skillRefineRef.current) return
    skillRefineRef.current = false
    void handleSkillRefineProposal()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming])

  async function handleSkillRefineProposal() {
    const ok = await requestApproval({
      title: 'AI 生成了技能草稿',
      desc: '写作过程中 AI 从参考内容提炼了叙事技法候选（已存草稿）。\n\n批准 = 全部采纳转正为可用技能；拒绝 = 删除草稿。\n也可稍后去「叙述」面板逐条确认。',
      estSeconds: 1,
      cost: 'low',
    })
    try {
      if (ok) {
        const drafts = await listSkillDrafts()
        for (const d of drafts) await promoteSkillDraft(d.id)
        setMessages(prev => [...prev, { role: 'agent', text: `✅ 已采纳 ${drafts.length} 条技能草稿（可在「叙述」面板查看使用）` }])
      } else {
        const drafts = await listSkillDrafts()
        for (const d of drafts) await deleteSkillDraft(d.id)
        setMessages(prev => [...prev, { role: 'agent', text: '[技能草稿已拒绝] 未采纳，草稿已清理' }])
      }
    } catch {
      setMessages(prev => [...prev, { role: 'agent', text: '⚠️ 技能草稿处理失败（可去「叙述」面板手动确认）' }])
    }
  }

  async function handleBatchProposal(proposal: { name: string; arguments: Record<string, unknown> }) {
    const isRewrite = proposal.name === 'batch_rewrite'
    const label = isRewrite ? '批量改写' : '批量审读'
    const titlesRaw = String(proposal.arguments?.chapter_titles || '')
    const instruction = String(proposal.arguments?.instruction || '').trim()
    // 标题解析：JSON 数组字符串或逗号分隔
    let titles: string[] = []
    try {
      const parsed = JSON.parse(titlesRaw)
      if (Array.isArray(parsed)) titles = parsed.map(String)
    } catch { /* 非 JSON */ }
    if (titles.length === 0) titles = titlesRaw.split(/[,，、;；\n]/).map(s => s.trim()).filter(Boolean)
    if (titles.length === 0) {
      setMessages(prev => [...prev, { role: 'agent', text: `⚠️ ${label}申请参数异常：未解析到章节` }])
      return
    }

    const ok = await requestApproval({
      title: `AI 请求${label}`,
      desc: `${label}以下 ${titles.length} 章：\n${titles.join('、')}`
        + (isRewrite && instruction ? `\n\n指令：${instruction}` : '')
        + `\n\n批准后将${isRewrite ? '修改原稿（旧版进版本历史可回退）' : '运行检测网审读'}`,
      estSeconds: titles.length * (isRewrite ? 20 : 8),
      cost: 'high',
    })
    if (!ok) {
      setMessages(prev => [...prev, { role: 'agent', text: `[${label}已拒绝] 未执行` }])
      return
    }

    // 批准 → 章节标题解析为 id → 提交批量
    try {
      const chs = await listChapters()
      const ids = chs
        .filter(c => titles.some(t => c.title.includes(t) || t.includes(c.title)))
        .map(c => c.id)
      if (ids.length === 0) {
        setMessages(prev => [...prev, { role: 'agent', text: `⚠️ ${label}提交失败：章节标题未匹配到任何章节` }])
        return
      }
      setMessages(prev => [...prev, { role: 'agent', text: `[${label}已提交] 共 ${ids.length} 章，正在执行…` }])
      // S140：/api/batch/* 已收编——agent 提议批准后走预置 workflow 模板执行
      // （断点恢复/确认闸门/批级回滚，S138 安全网）；轮询任务状态替代旧内存 batch
      const wfs = await listWorkflows()
      const tmpl = wfs.find((w) => w.name === label)
      if (!tmpl) {
        setMessages(prev => [...prev, { role: 'agent', text: `⚠️ ${label}模板不存在` }])
        return
      }
      const r = await runWorkflow(tmpl.id, 'main', {
        chapter_ids: JSON.stringify(ids),
        ...(isRewrite && instruction ? { instruction } : {}),
      })
      const taskId = r.task_id
      // 轮询进度 → 替换进度消息（找到以 [label 开头的最新 agent 消息）
      const timer = window.setInterval(async () => {
        try {
          const t = await getWorkflowTask(taskId)
          const states = t.node_states ?? []
          const done = states.filter((s) => s.status === 'done').length
          const total = states.length || 0
          const text = ['done', 'failed', 'cancelled'].includes(t.status)
            ? `[${label}完成] ${done}/${total} 节点`
            : t.status === 'waiting_approval'
              ? `[${label}待确认] 覆盖原稿需在批量操作面板确认`
              : `[${label}执行中] ${done}/${total} 节点…`
          setMessages(prev => {
            const idx = prev.findIndex(m => m.role === 'agent' && m.text?.startsWith(`[${label}`))
            const msg = { role: 'agent', text }
            if (idx >= 0) {
              const next = [...prev]; next[idx] = msg; return next
            }
            return [...prev, msg]
          })
          if (['done', 'failed', 'cancelled'].includes(t.status)) window.clearInterval(timer)
        } catch {
          window.clearInterval(timer)
        }
      }, 3000)
    } catch {
      setMessages(prev => [...prev, { role: 'agent', text: `⚠️ ${label}提交失败，请检查后端` }])
    }
  }

  async function handleCancel() {
    // Flush any buffered chunks before cancelling
    if (chunkTimerRef.current) {
      clearTimeout(chunkTimerRef.current)
      chunkTimerRef.current = null
    }
    flushChunks()
    streamingRef.current = false
    await sseCancel()
    setProgress(null)
    setWritingState(prev => prev && !prev.saved
      ? { ...prev, failed: true, error: '用户已中止，本次预览内容未保证写入章节。' }
      : prev)
    setMessages(prev => [...prev, { role: 'agent', text: '操作已中止' }])
  }

  function handlePanelResizeStart(e) {
    e.preventDefault()
    const root = e.currentTarget.parentElement
    if (!root) return
    const rect = root.getBoundingClientRect()
    const onMove = (event) => {
      const width = ((rect.right - event.clientX) / rect.width) * 100
      setSidePanelWidth(Math.min(70, Math.max(28, width)))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  async function handleRetry() {
    const msg = lastSentMsgRef.current
    if (!msg) return
    setMessages(prev => {
      const updated = [...prev]
      const lastAgent = updated.length - 1
      if (lastAgent >= 0 && updated[lastAgent].role === 'agent' && (updated[lastAgent] as any).retry) {
        updated.splice(lastAgent, 1)
      }
      return updated
    })
    await sseSend(msg)
    setProgress(null)
  }

  async function handleAutonomousToggle() {
    const next = !autonomousMode
    // 接入全局审批节点：自主模式开启 → 审批自动同意（不再调对端端点）
    setGlobalAutoMode(next)
    setAutonomousMode(next)
  }


  // ── Autopilot control handlers ──
  async function handleAutopilotPause() {
    if (!autopilotState?.taskId) return
    try { await api.pauseTask(bookId, autopilotState.taskId); setAutopilotState(prev => ({ ...prev, status: 'paused' })) } catch (e) { alert(e.message) }
  }
  async function handleAutopilotResume() {
    if (!autopilotState?.taskId) return
    try { await api.resumeTask(bookId, autopilotState.taskId); setAutopilotState(prev => ({ ...prev, status: 'running' })) } catch (e) { alert(e.message) }
  }
  function handleAutopilotCancel() {
    // 弹确认窗（原 confirm）——确认后执行真实取消
    setShowAutopilotCancel(true)
  }
  async function doAutopilotCancel() {
    setShowAutopilotCancel(false)
    if (!autopilotState?.taskId) return
    try {
      await api.cancelTask(bookId, autopilotState.taskId)
      cleanupAutopilot()
    } catch (e) { alert(e.message) }
  }
  async function handleAutopilotForceStop() {
    if (!autopilotState?.taskId) return
    try {
      // Force-stop: abort SSE bridge + call stop API + full cleanup
      if (autopilotAbortRef.current) {
        autopilotAbortRef.current.abort()
        autopilotAbortRef.current = null
      }
      await api.stopAutopilot(bookId, autopilotState.taskId).catch(() => {})
      cleanupAutopilot()
      setMessages(prev => [...prev, {
        role: 'system',
        text: '🚫 Autopilot 已强制中止',
        autopilot: true,
      }])
    } catch (e) { alert(e.message) }
  }
  function cleanupAutopilot() {
    if (autopilotAbortRef.current) {
      autopilotAbortRef.current.abort()
      autopilotAbortRef.current = null
    }
    // Also cancel any lingering chat SSE to unstick the streaming state
    sseCancel()
    setAutopilotState(null)
    setAutopilotBridge(null)
  }
  async function handleAutopilotSkip() {
    if (!autopilotState?.taskId) return
    try { await api.retryTask(bookId, autopilotState.taskId) } catch (e) { alert(e.message) }
  }
  function handleAutopilotClose() {
    cleanupAutopilot()
  }

  const hasAutopilot = autopilotState && autopilotState.status !== 'completed'
  const hasSidePanel = Boolean(hasAutopilot || writingState || (taskList && taskList.length > 0) || workflowData)

  const filteredMessages = searchQuery
    ? messages.filter(m => (m.text || '').toLowerCase().includes(searchQuery.toLowerCase()))
    : messages

  return (
    <div className="h-full flex">
      {/* Main chat column */}
      <div className="h-full min-w-0 flex flex-col" style={{ width: hasSidePanel ? `${100 - sidePanelWidth}%` : '100%' }}>
        <MessageList
          messages={filteredMessages}
          streaming={streaming}
          uploading={uploading}
          progress={progress}
          plotCards={plotCards}
          question={question}
          workflowData={workflowData}
          patchData={patchData}
          showToolCalls={showToolCalls}
          onRevert={handleRevert}
          onEdit={handleEdit}
          onValidate={handleValidate}
          onPlotCardSelect={handlePlotCardSelect}
          onPlotCardReject={handlePlotCardReject}
          onQuestionReply={handleQuestionReply}
          onQuestionReject={handleQuestionReject}
          onRetry={handleRetry}
        />

        <div className="px-3 py-1.5 border-t border-zinc-800 bg-zinc-950 shrink-0 space-y-1">
          {/* Compact toolbar: context usage + search toggle */}
          <div className="flex items-center gap-2">
            <div className="flex-1 min-w-0">
              <ContextBar contextUsage={contextUsage} />
              <UsageStrip metrics={metrics as any} />
              <RunLedger metrics={metrics} />
            </div>
            {searchQuery && (
              <span className="text-[10px] text-zinc-500 shrink-0">{filteredMessages.length} 条匹配</span>
            )}
            <button
              onClick={() => { setSearchOpen(v => !v); if (searchOpen) setSearchQuery('') }}
              className={`shrink-0 rounded-lg p-1.5 transition-colors ${
                searchOpen || searchQuery
                  ? 'bg-accent/15 text-accent border border-accent/30'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 border border-transparent'
              }`}
              title="搜索历史消息"
              aria-label="搜索历史消息"
            >
              <Icon name="search" size={14} />
            </button>
            <button
              onClick={() => setShowToolCalls(v => !v)}
              className={`shrink-0 rounded-lg p-1.5 transition-colors ${
                showToolCalls
                  ? 'text-amber-400 hover:text-amber-300 border border-amber-700/40'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 border border-transparent'
              }`}
              title={showToolCalls ? '隐藏工具调用和思考过程' : '显示工具调用和思考过程'}
              aria-label="切换工具调用显示"
            >
              <Icon name="wrench" size={14} />
            </button>
          </div>

          {/* Collapsible search input */}
          {searchOpen && (
            <div className="relative animate-fade-in">
              <Icon name="search" size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                autoFocus
                placeholder="搜索历史消息..."
                className="w-full bg-zinc-800/60 border border-zinc-700 rounded-lg pl-8 pr-7 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500 placeholder-zinc-500"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                  aria-label="清除搜索"
                >
                  <Icon name="x" size={11} />
                </button>
              )}
            </div>
          )}
              <MessageInput
                input={input}
                setInput={setInput}
                streaming={streaming}
                uploading={uploading}
                onSend={sendMessage}
                onCancel={handleCancel}
                onQueue={handleQueue}
                onSteer={handleSteer}
                onUpload={handleUpload}
                queue={pendingQueue}
                onDequeue={handleDequeue}
                onSteerQueued={handleSteerQueued}
                autonomousMode={autonomousMode}
                onAutonomousToggle={handleAutonomousToggle}
                showSlash={showSlash}
                setShowSlash={setShowSlash}
                setSlashFilter={setSlashFilter}
                slashItems={slashItems}
                slashIdx={slashIdx}
                setSlashIdx={setSlashIdx}
                skillCommands={skillCommands}
                onSlashSelect={handleSlashSelect}
                onSlashNavigate={(i) => setSlashIdx(i)}
                onSlashClose={() => setShowSlash(false)}
              />
        </div>
      </div>

      {/* Right side panel */}
      {hasSidePanel && (
        <>
        <div
          role="separator"
          aria-label="调整右侧面板宽度"
          onPointerDown={handlePanelResizeStart}
          className="w-1 h-full shrink-0 cursor-col-resize bg-zinc-900 hover:bg-sky-700 transition-colors"
          title="拖动调整右侧面板宽度"
        />
        <div className="h-full min-w-0 bg-zinc-950 flex flex-col overflow-hidden" style={{ width: `${sidePanelWidth}%` }}>
          {hasAutopilot && autopilotState ? (
            <AutopilotConsole
              state={autopilotState}
              taskId={autopilotState.taskId}
              bookId={bookId}
              sessionId={sessionId}
              onPause={handleAutopilotPause}
              onResume={handleAutopilotResume}
              onCancel={handleAutopilotCancel}
              onForceStop={handleAutopilotForceStop}
              onSkip={handleAutopilotSkip}
              onClose={handleAutopilotClose}
            />
          ) : (
            <>
          {workflowData && (
            <div className="shrink-0 p-3 border-b border-zinc-800">
              <WorkflowProgress data={workflowData} />
            </div>
          )}
          {writingState && (
            <>
              <div className="shrink-0">
                <WritingPreview data={writingState} onClose={() => setWritingState(null)} />
              </div>
              <div className="flex-1 overflow-y-auto">
                {taskList && taskList.length > 0 && <TaskListPanel items={taskList} />}
              </div>
            </>
          )}
          {!writingState && taskList && taskList.length > 0 && (
            <div className="flex-1 overflow-y-auto p-4">
              <TaskListPanel items={taskList} />
            </div>
          )}
            </>
          )}
        </div>
        </>
      )}

      <ConfirmModal
        open={revertIdx !== null}
        title="回退对话"
        message={`回退到此消息之前？包括此消息在内的 ${revertIdx !== null ? messages.length - revertIdx : 0} 条对话将被删除。`}
        danger
        onConfirm={confirmRevert}
        onCancel={() => setRevertIdx(null)}
      />

      {/* 取消 Autopilot 确认 */}
      <ConfirmModal
        open={showAutopilotCancel}
        title="取消 Autopilot"
        message="确认取消 Autopilot 自主写作？当前运行中的任务将终止。"
        confirmText="取消"
        danger
        onConfirm={doAutopilotCancel}
        onCancel={() => setShowAutopilotCancel(false)}
      />
    </div>
  )
}
