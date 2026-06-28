import { useState, useRef, useEffect } from 'react'
import Icon from './ui/Icon'
import { useSSE } from "../hooks/useSSE"
import MessageList from './chat/MessageList'
import MessageInput from './chat/MessageInput'
import ContextBar from './chat/ContextBar'
import WritingPreview from './chat/WritingPreview'
import TaskListPanel from './chat/TaskListPanel'
import WorkflowProgress from './chat/WorkflowProgress'
import ConfirmModal from './ui/ConfirmModal'
import BookTransformPanel from './BookTransformPanel'
import RunLedger from './chat/RunLedger'
import AutopilotConsole from './chat/AutopilotConsole'
import { api } from "../api"
import { triggerRefresh } from "../store"

export default function ChatPanel({ bookId, sessionId, autoModeEnabled, transformSignal }: { bookId: string; sessionId: string; autoModeEnabled: boolean; transformSignal: number }) {
  const welcomeMsg = { role: 'agent', text: '你好！我是你的 AI 写作助手 Agent。\n\n'
    + '🔍 **Plan 模式**: 只读 — 浏览知识库、检索数据、规划剧情\n'
    + '✍️ **Write 模式**: 读写 — 提取设定、章节书写、编辑知识库\n\n'
    + '我会先理解你的内容类型，再自动选择最佳处理方式。\n'
    + '在输入框输入 `/` 可查看所有快捷命令和技能。\n\n'
    + '💡 **提示**: 斜杠命令（如 `/w`、`/s`）走快速通道直达对应工具，自然语言描述走 Agent 智能路由。两者都能完成相同任务，选择你习惯的方式即可。' }

  const [messages, setMessages] = useState([welcomeMsg])
  const [loaded, setLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [uploading, setUploading] = useState(false)
  const [agentMode, setAgentMode] = useState('write')
  const [progress, setProgress] = useState(null)
  const [question, setQuestion] = useState(null)
  const [plotCards, setPlotCards] = useState(null)
  const [showSlash, setShowSlash] = useState(false)
  const [slashFilter, setSlashFilter] = useState('')
  const [slashIdx, setSlashIdx] = useState(0)
  const [skillCommands, setSkillCommands] = useState([])
  const [contextUsage, setContextUsage] = useState(null)
  const [writingState, setWritingState] = useState(null)
  const [taskList, setTaskList] = useState(null)
  const [workflowData, setWorkflowData] = useState(null)
  const [patchData, setPatchData] = useState(null)
  const [metrics, setMetrics] = useState(null)  // Agent run metrics for Run Ledger
  const [revertIdx, setRevertIdx] = useState(null)
  const [showTransform, setShowTransform] = useState(false)
  const [transformStyles, setTransformStyles] = useState([])
  const [autopilotState, setAutopilotState] = useState(null)
  const [autopilotBridge, setAutopilotBridge] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [autonomousMode, setAutonomousMode] = useState(false)
  const saveTimerRef = useRef(null)
  const hideTimerRef = useRef(null)
  const lastSentMsgRef = useRef('')

  const { sendMessage: sseSend, cancel: sseCancel, streaming } = useSSE({
    bookId,
    sessionId,
    agentMode,
    autoModeEnabled,
    onMessage: (event) => {
      if (event.type === 'start') {
        setMessages(prev => [...prev, { role: 'agent', text: event.text }])
      } else if (event.type === 'append') {
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'agent') {
            updated[updated.length - 1] = { ...last, text: last.text + event.text }
          }
          return updated
        })
      } else if (event.type === 'plain') {
        setMessages(prev => [...prev, { role: 'agent', text: event.text }])
      }
    },
    onProgress: setProgress,
    onPlotCards: setPlotCards,
    onQuestion: setQuestion,
    onWriting: (data) => {
      if (data.type === 'start') {
        // Writing started — set up preview and add chat notification
        setWritingState({ chapterTitle: data.chapter_title, text: '', saved: false })
        setMessages(prev => [...prev, { role: 'agent', text: `✍️ 开始写作: ${data.chapter_title}（见右侧预览）` }])
      } else if (data.type === 'end') {
        // Writing ended — update state and add chat notification
        setWritingState(prev => ({ ...prev, saved: true, wordCount: data.word_count, partial: data.partial }))
        const status = data.partial ? '⚠️ 部分保存' : '✅ 已保存'
        setMessages(prev => [...prev, { role: 'agent', text: `${status}到 ${data.chapter_title}，共 ${data.word_count || 0} 字` }])
        // Auto-hide side panel after 5s
        clearTimeout(hideTimerRef.current)
        hideTimerRef.current = setTimeout(() => {
          setWritingState(null)
          setTaskList(null)
        }, 5000)
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
            text: `⚠️ _模型在操作前输出了误导性文字，已纠正。实际工具调用正在执行中..._`,
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
      setMessages(prev => [...prev, { role: 'agent', text: errorText, retry: true }])
    },
    onMetrics: (data) => {
      setMetrics(data)
    }
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

  // ── Fetch skills on mount ──
  useEffect(() => {
    api.getSkills().then(data => {
      const skills = data?.skills || []
      setSkillCommands(skills.map(sk => ({
        cmd: '/' + sk.name,
        desc: sk.description,
        usage: '/' + sk.name,
        steps: sk.steps || [],
      })))
    }).catch(() => {})
  }, [])

  // ── Autopilot detection on mount ──
  useEffect(() => {
    if (!bookId || !sessionId || !autoModeEnabled) return
    api.getAutopilotStatus(bookId).then(data => {
      if (data.active && data.tasks.length > 0) {
        const task = data.tasks[0]
        setAutopilotState({
          taskId: task.task_id,
          status: task.status,
          audit_mode: task.audit_mode,
          progress: task.progress,
          chapters_completed: task.chapters_completed,
          total_chapters: task.total_chapters,
        })
        // Connect bridge SSE
        connectAutopilotBridge(task.task_id)
      }
    }).catch(() => {})
  }, [bookId, sessionId])

  function connectAutopilotBridge(taskId) {
    const response = fetch(`/api/books/${bookId}/autopilot/${taskId}/chat-bridge`)
    setAutopilotBridge(response)

    response.then(res => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) return
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                handleAutopilotEvent(eventType, data)
              } catch (e) {
                // plain text chunk
                if (eventType === 'chunk') {
                  handleAutopilotEvent('chunk', { text: line.slice(6) })
                }
              }
              eventType = ''
            }
          }
          read()
        }).catch(() => {})
      }
      read()
    }).catch(() => {})
  }

  function handleAutopilotEvent(type, data) {
    switch (type) {
      case 'autopilot_step':
        setAutopilotState(prev => prev ? { ...prev, progress: data.progress } : null)
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `✅ ${data.step_label || ''}`,
          autopilot: true,
          stepId: data.step_id,
        }])
        break
      case 'autopilot_error':
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `❌ ${data.step_label || ''}: ${data.error || ''}`,
          autopilot: true,
        }])
        break
      case 'autopilot_done':
        setAutopilotState(null)
        setAutopilotBridge(null)
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `🎉 Autopilot 完成！${data.summary || ''}`,
          autopilot: true,
        }])
        break
      case 'autopilot_failed':
        setAutopilotState(null)
        setAutopilotBridge(null)
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `❌ Autopilot 失败: ${data.error || ''}`,
          autopilot: true,
        }])
        break
      case 'autopilot_notify':
        setMessages(prev => [...prev, {
          role: 'agent',
          text: `📢 ${data.message || ''}`,
          autopilot: true,
        }])
        break
      case 'autopilot_progress':
        setProgress({ stage: data.stage || '', detail: data.detail || '' })
        break
      case 'chunk':
        break
    }
  }

  const SLASH_COMMANDS = [
    { cmd: '/s', desc: '强制提取设定', usage: '/s 文本内容' },
    { cmd: '/w', desc: '严格模式写作', usage: '/w 写作指令' },
    { cmd: '/ws', desc: '宽松模式写作', usage: '/ws 写作指令' },
    { cmd: '/help', desc: '显示所有命令', usage: '/help' },
    { cmd: '/skills', desc: '列出所有可用技能', usage: '/skills' },
    { cmd: '/style', desc: '选择/查看写作风格', usage: '/style 风格名' },
  ]

  const slashItems = SLASH_COMMANDS.filter(s =>
    slashFilter === '' || s.cmd.startsWith('/' + slashFilter.toLowerCase())
  )

  // Load history on session mount
  useEffect(() => {
    setMessages([welcomeMsg])
    setLoaded(false)
    if (!sessionId) return
    fetch(`/api/books/${bookId}/sessions/${sessionId}/messages`).then(r => r.json()).then(data => {
      if (data && data.length > 0) setMessages(data)
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [bookId, sessionId])

  // Auto-save debounce
  useEffect(() => {
    if (!loaded || !sessionId) return
    clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      fetch(`/api/books/${bookId}/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages }),
      }).catch(() => {})
    }, 500)
    return () => clearTimeout(saveTimerRef.current)
  }, [messages, bookId, sessionId, loaded])

  // Context usage poll
  useEffect(() => {
    if (!sessionId) return
    fetch(`/api/books/${bookId}/sessions/${sessionId}/context`)
      .then(r => r.ok ? r.json() : Promise.reject('not ok'))
      .then(data => setContextUsage(data))
      .catch(() => setContextUsage(null))
  }, [messages.length, sessionId, bookId])

  async function handleUpload(file) {
    if (!file || uploading) return
    setUploading(true)

    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    setMessages(prev => [...prev,
      { role: 'user', text: `📄 上传文档: ${file.name} (${sizeMB} MB)` },
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
      setMessages(prev => [...prev, {
        role: 'agent',
        text: `✅ ${data.message}\n\n现在可以给我指令处理这个文件，例如：\n• "帮我把第1章拆解并复写"\n• "提取这个文件的全部设定"\n• "分析这个小说的文风特征"`,
      }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'agent', text: `⚠️ 上传失败: ${e.message}` }])
    }
    setUploading(false)
  }

  async function handleValidate(text) {
    setMessages(prev => [...prev, { role: 'agent', text: '🔍 正在校验内容与知识库的一致性...' }])
    try {
      const res = await fetch(`/api/books/${bookId}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const result = await res.json()
      const lines = []
      if (result.valid) {
        lines.push('✅ 校验通过，未发现与知识库的冲突')
      } else {
        lines.push('⚠️ 发现以下问题：')
        for (const c of (result.conflicts || [])) {
          lines.push(`  · ${c}`)
        }
      }
      for (const n of (result.notes || [])) {
        lines.push(`  ℹ️ ${n}`)
      }
      setMessages(prev => [...prev, { role: 'agent', text: lines.join('\n') }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'agent', text: '⚠️ 校验失败，请重试' }])
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
    setInput(s.usage + ' ')
    setShowSlash(false)
    setSlashIdx(0)
  }

  async function sendMessage() {
    if (!input.trim() || streaming || question || plotCards) return
    const msg = input.trim()
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

  async function handleCancel() {
    await sseCancel()
    setProgress(null)
    setMessages(prev => [...prev, { role: 'agent', text: '⏹ 操作已中止' }])
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
    try {
      await fetch(`/api/books/${bookId}/sessions/${sessionId}/autonomous`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      })
    } catch (e) { /* ignore */ }
    setAutonomousMode(next)
  }

  async function handleOpenTransform() {
    try {
      const data = await api.getStyles()
      setTransformStyles(data.styles || [])
    } catch {
      setTransformStyles([])
    }
    setShowTransform(true)
  }

  // Open transform panel when signalled from AutopilotModal (sibling)
  useEffect(() => {
    if (transformSignal > 0) handleOpenTransform()
  }, [transformSignal])

  function handleTransformSend(message) {
    setMessages(prev => [...prev, { role: 'user', text: message }])
    sseSend(message)
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
  async function handleAutopilotCancel() {
    if (!autopilotState?.taskId) return
    if (!confirm('确认取消 Autopilot？')) return
    try { await api.cancelTask(bookId, autopilotState.taskId); setAutopilotState(null); setAutopilotBridge(null) } catch (e) { alert(e.message) }
  }
  async function handleAutopilotSkip() {
    if (!autopilotState?.taskId) return
    try { await api.retryTask(bookId, autopilotState.taskId) } catch (e) { alert(e.message) }
  }
  function handleAutopilotClose() {
    setAutopilotState(null)
    setAutopilotBridge(null)
  }

  const hasAutopilot = autopilotState && autopilotState.status !== 'completed'
  const hasSidePanel = hasAutopilot || writingState || (taskList && taskList.length > 0) || workflowData

  const filteredMessages = searchQuery
    ? messages.filter(m => (m.text || '').toLowerCase().includes(searchQuery.toLowerCase()))
    : messages

  return (
    <div className="h-full flex">
      {/* Main chat column */}
      <div className={`h-full flex flex-col transition-all duration-300 ${hasSidePanel ? 'w-[55%]' : 'w-full'}`}>
        <MessageList
          messages={filteredMessages}
          streaming={streaming}
          uploading={uploading}
          progress={progress}
          plotCards={plotCards}
          question={question}
          workflowData={workflowData}
          patchData={patchData}
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
            agentMode={agentMode}
            onSend={sendMessage}
            onCancel={handleCancel}
            onUpload={handleUpload}
            onTransform={handleOpenTransform}
            onModeToggle={() => setAgentMode(agentMode === 'write' ? 'plan' : 'write')}
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
        <div className="w-[45%] h-full border-l border-zinc-800 bg-zinc-950 flex flex-col overflow-hidden">
          {hasAutopilot && autopilotState ? (
            <AutopilotConsole
              state={autopilotState}
              taskId={autopilotState.taskId}
              bookId={bookId}
              sessionId={sessionId}
              onPause={handleAutopilotPause}
              onResume={handleAutopilotResume}
              onCancel={handleAutopilotCancel}
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
                <WritingPreview data={writingState} />
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
      )}

      <BookTransformPanel
        open={showTransform}
        onClose={() => setShowTransform(false)}
        onSend={handleTransformSend}
        styles={transformStyles}
      />

      <ConfirmModal
        open={revertIdx !== null}
        title="回退对话"
        message={`回退到此消息之前？包括此消息在内的 ${revertIdx !== null ? messages.length - revertIdx : 0} 条对话将被删除。`}
        danger
        onConfirm={confirmRevert}
        onCancel={() => setRevertIdx(null)}
      />
    </div>
  )
}
