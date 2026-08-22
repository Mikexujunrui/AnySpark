import { useRef, useEffect, useState, useCallback, memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ProgressIndicator from './ProgressIndicator'
import PlotCardSelector from './PlotCardSelector'
import QuestionCard from './QuestionCard'
import WorkflowProgress from './WorkflowProgress'
import PatchNotification from './PatchNotification'
import Icon from '../ui/Icon'

const MemoizedMarkdown = memo(function MarkdownContent({ text }: { text: string }) {
  return (
    // S80：去 whitespace-pre-wrap（它保留 markdown 渲染后 HTML 的换行，与段落间距叠加成双换行/大间隙）
    <div className="markdown-body min-w-0 break-words [overflow-wrap:anywhere] [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_code]:break-words [&>p]:my-0.5 [&_li]:my-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
})

function InlineEditor({ text, onSave, onCancel }) {
  const [value, setValue] = useState(text)
  const taRef = useRef(null)

  useEffect(() => {
    if (taRef.current) {
      taRef.current.focus()
      taRef.current.selectionStart = taRef.current.value.length
    }
  }, [])

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = 'auto'
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 500) + 'px'
    }
  }, [value])

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      onSave(value)
    }
  }

  return (
    <div className="w-full">
      <textarea
        ref={taRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="w-full bg-zinc-900 border border-zinc-600 rounded-lg px-3 py-2 text-sm text-zinc-200 resize-none focus:outline-none focus:border-sky-600"
        rows={4}
      />
      <div className="flex gap-2 mt-1.5">
        <button
          onClick={() => onSave(value)}
          className="text-[11px] px-2 py-0.5 bg-sky-700/60 hover:bg-sky-600/80 text-white rounded transition-colors"
        >
          保存 (Ctrl+Enter)
        </button>
        <button
          onClick={onCancel}
          className="text-[11px] px-2 py-0.5 text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          取消 (Esc)
        </button>
      </div>
    </div>
  )
}


// ── Structured parts rendering (tool calls, chapter diffs, reasoning) ───────
// Persisted turns carry a `parts` array so refresh/replay shows the full
// execution history inline, not just the final visible text.

function ToolCallCard({ part }) {
  let argsPreview: string
  try {
    const parsed = typeof part.arguments === 'string' ? JSON.parse(part.arguments) : part.arguments
    argsPreview = parsed ? JSON.stringify(parsed).slice(0, 80) : ''
  } catch { argsPreview = (part.arguments || '').slice(0, 80) }
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-zinc-400 bg-zinc-900/60 border border-zinc-700/60 rounded-md px-2 py-1">
      <Icon name="wrench" size={10} className="text-amber-400 shrink-0" />
      <span className="text-zinc-300 font-mono">{part.name}</span>
      {argsPreview && <span className="text-zinc-600 truncate">{argsPreview}</span>}
    </div>
  )
}

function ChapterDiffBadge({ part }) {
  const opLabel = {
    created: '新建', edited: '修改', patched: '补丁', deleted: '删除', reverted: '回退', imported: '导入',
  }[part.operation] || part.operation
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-emerald-300 bg-emerald-950/30 border border-emerald-800/40 rounded-md px-2 py-1">
      <Icon name="file-text" size={10} className="shrink-0" />
      <span>{part.chapter_title || part.chapter_id}</span>
      <span className="text-emerald-500">{opLabel}</span>
      {part.word_count > 0 && <span className="text-zinc-500">{part.word_count}字</span>}
      {part.patch_count > 0 && <span className="text-zinc-500">{part.patch_count}处</span>}
    </div>
  )
}

function ReasoningBlock({ text, index }: { text: string; index?: number }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={10} />
        <Icon name="brain" size={10} />
        思考过程{index ? ` ${index}` : ''}{open ? '' : `（${text.length}字）`}
      </button>
      {open && (
        <div className="mt-1 text-[11px] text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded-md p-2 max-h-48 overflow-y-auto whitespace-pre-wrap italic">
          {text}
        </div>
      )}
    </div>
  )
}

// S213：流式思考块——思考进行中实时显示（默认展开，带“思考中…”动画），done 后由 ReasoningBlock 替代
function StreamingReasoningBlock({ text }: { text: string }) {
  if (!text) return null
  return (
    <div className="mb-2">
      <div className="flex items-center gap-1 text-[10px] text-amber-400/70 mb-1">
        <Icon name="brain" size={10} className="animate-pulse" />
        <span>思考中…</span>
        <span className="text-zinc-600">（{text.length}字）</span>
      </div>
      <div className="text-[11px] text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded-md p-2 max-h-60 overflow-y-auto whitespace-pre-wrap italic">
        {text}
        <span className="inline-block w-1.5 h-3 bg-amber-400/60 ml-0.5 animate-pulse align-middle" />
      </div>
    </div>
  )
}

// S184：TurnParts 折叠——批量任务一轮可能有几十上百次工具调用，逐条渲染会刷满整个视口。
// 超过阈值默认只展开头部几条 + 一条聚合概要，点击展开全部。
const TOOL_CARD_COLLAPSE_THRESHOLD = 6

function TurnParts({ parts }) {
  const [showAll, setShowAll] = useState(false)
  if (!parts || parts.length === 0) return null
  // S98：按执行顺序逐条渲染——每条思维链独立折叠块（不再 join 成一个），
  // 工具调用卡片/章节徽章穿插在对应轮次之间，完整还原每轮「思考→调用→结果」链路
  let reasoningIdx = 0
  const toolCount = parts.filter(p => p && p.type === 'tool_call').length
  const collapsed = !showAll && toolCount > TOOL_CARD_COLLAPSE_THRESHOLD
  let toolSeen = 0
  let toolRendered = 0
  return (
    <div className="space-y-1 mb-2">
      {parts.map((p, i) => {
        if (!p) return null
        if (p.type === 'reasoning') {
          reasoningIdx += 1
          return <ReasoningBlock key={i} text={p.text} index={reasoningIdx} />
        }
        if (p.type === 'chapter_diff') return <ChapterDiffBadge key={i} part={p} />
        if (p.type === 'tool_call') {
          toolSeen += 1
          // 折叠态：只保留前 N 张卡片，其余由聚合按钮兜底
          if (collapsed && toolRendered >= TOOL_CARD_COLLAPSE_THRESHOLD) return null
          toolRendered += 1
          return <ToolCallCard key={i} part={p} />
        }
        return null
      })}
      {collapsed && (
        <button
          onClick={() => setShowAll(true)}
          className="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 bg-zinc-900/40 border border-dashed border-zinc-700/70 rounded-md px-2 py-1 transition-colors w-full"
        >
          <Icon name="wrench" size={10} className="text-amber-400/80 shrink-0" />
          <span>…还有 {toolCount - toolRendered} 条工具调用</span>
          <span className="ml-auto text-[10px] text-zinc-600">点击展开全部 ▾</span>
        </button>
      )}
    </div>
  )
}

// S184：连续 role:'tool' 消息聚合渲染——流式阶段每个 tool_call 事件都追加一条 tool 消息，
// 批量任务几百次调用会刷出几百行小灰字。把相邻的 tool 消息合并为一条紧凑聚合徽章，
// 默认显示「工具调用 ×N + 各工具次数」，点击展开逐条明细。
function ToolTraceGroup({ texts }: { texts: string[] }) {
  const [open, setOpen] = useState(false)
  if (!texts || texts.length === 0) return null
  const counts: Record<string, number> = {}
  for (const t of texts) {
    const label = String(t || '').replace(/^\[|\]$/g, '')
    const idx = label.indexOf(':')
    if (idx > 0) {
      const name = label.slice(idx + 1).trim().replace(/…$/, '')
      if (name) counts[name] = (counts[name] || 0) + 1
    }
  }
  const summary = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([n, c]) => `${n}×${c}`)
    .join(', ')
  return (
    <div className="w-full flex justify-center my-1">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 text-[10px] text-zinc-500 bg-zinc-800/50 hover:bg-zinc-700/60 border border-zinc-700/60 px-2 py-0.5 rounded-full transition-colors max-w-full"
        title={open ? '收起' : '展开工具调用明细'}
      >
        <Icon name="wrench" size={10} className="text-amber-400/80 shrink-0" />
        <span className="font-mono text-zinc-400">工具调用 ×{texts.length}</span>
        {!open && summary && <span className="text-zinc-600 truncate">{summary}</span>}
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={10} className="text-zinc-600 shrink-0" />
      </button>
      {open && (
        <div className="mt-1 mx-auto max-w-md text-left bg-zinc-900/70 border border-zinc-800 rounded-lg px-3 py-2 max-h-72 overflow-y-auto">
          {texts.map((t, i) => (
            <div
              key={i}
              className="text-[10px] text-zinc-500 font-mono py-1 border-b border-zinc-800/50 last:border-0"
            >
              <span className="text-zinc-600 mr-2">{i + 1}</span>
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// 把连续 tool 消息聚合成一个逻辑条目，其余消息保留原索引语义（编辑/回退/重试按原消息下标操作）
function groupToolMessages(messages) {
  const items = []
  let i = 0
  const list = Array.isArray(messages) ? messages : []
  const toolSeq = { n: 0 }
  while (i < list.length) {
    if (list[i] && list[i].role === 'tool') {
      const texts = []
      while (i < list.length && list[i] && list[i].role === 'tool') {
        texts.push(list[i].text)
        i += 1
      }
      items.push({ kind: 'toolRun', key: `tool-run-${toolSeq.n++}`, texts })
    } else {
      items.push({ kind: 'msg', key: i, index: i, msg: list[i] })
      i += 1
    }
  }
  return items
}

export default function MessageList({
  messages,
  streaming,
  uploading,
  progress,
  plotCards,
  question,
  workflowData,
  patchData,
  showToolCalls,
  onRevert,
  onEdit,
  onValidate,
  onPlotCardSelect,
  onPlotCardReject,
  onQuestionReply,
  onQuestionReject,
  onRetry,
}) {
  const scrollContainerRef = useRef(null)
  const isAtBottomRef = useRef(true)
  const [showJumpDown, setShowJumpDown] = useState(false)
  const [editingIdx, setEditingIdx] = useState(null)

  // S184：滚动跟随。原实现用 smooth scrollIntoView 逐 chunk 触发，动画被高频更新反复打断
  // 且 isAtBottom 一旦被任意滚动事件置 false（含浏览器恢复历史滚动位置）就永不自动跟底。
  // 改为：停留在底部（或从未主动上滚）时同步 scrollTop 直达最新，无动画就不存在打断；
  // 用户明确上滚后显示「回到底部」悬浮按钮，点击才用平滑滚动。
  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollContainerRef.current
    if (!el) return
    if (smooth) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    } else {
      el.scrollTop = el.scrollHeight
    }
    isAtBottomRef.current = true
    setShowJumpDown(false)
  }, [])

  // 内容变化（含流式 tool 消息/进度/卡片等任何可能撑高列表的状态）→ 在底部则跟到最新
  useEffect(() => {
    if (isAtBottomRef.current) scrollToBottom(false)
  }, [messages, streaming, uploading, progress, workflowData, patchData, plotCards, question, scrollToBottom])

  // 首次挂载后浏览器可能恢复历史滚动位置（触发的 scroll 事件会把 isAtBottom 置 false），
  // 下一帧兜底一次：无操作用户应看到最新底部。
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      if (isAtBottomRef.current) scrollToBottom(false)
    })
    return () => cancelAnimationFrame(raf)
  }, [scrollToBottom])

  const handleScroll = (e) => {
    const el = e.target as HTMLElement
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    isAtBottomRef.current = near
    if (near) setShowJumpDown(false)
    else setShowJumpDown(true)
  }

  const items = groupToolMessages(messages)

  return (
    <div className="flex-1 min-h-0 relative">
      <div
        className="h-full overflow-y-auto px-6 py-5 space-y-6"
        ref={scrollContainerRef}
        onScroll={handleScroll}
      >
        {items.map((item) => {
          if (item.kind === 'toolRun') {
            return <ToolTraceGroup key={item.key} texts={item.texts} />
          }
          const msg = item.msg
          const i = item.index
          return (
            <div key={i} className={`flex min-w-0 gap-3 group ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              {msg.role === 'tool' ? (
                <div className="w-full text-center">
                  <span className="inline-block text-[10px] text-zinc-600 bg-zinc-800/40 px-2 py-0.5 rounded">{msg.text}</span>
                </div>
              ) : (
              <>
              {msg.role === 'agent' && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-800/60 to-sky-900/80 border border-sky-700/50 flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
                  <Icon name="lightbulb" size={14} className="text-sky-300" />
                </div>
              )}
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-zinc-700/80 to-zinc-800/90 border border-zinc-600/60 flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
                  <Icon name="user" size={14} className="text-zinc-300" />
                </div>
              )}
              <div className={`flex min-w-0 flex-col ${msg.role === 'user' ? 'items-end max-w-[min(640px,88%)]' : 'items-start max-w-[min(46rem,92%)]'}`}>
                <div className={`min-w-0 max-w-full text-sm leading-normal break-words [overflow-wrap:anywhere] ${
                  msg.autopilot
                    ? 'border-l-2 border-purple-500/60 pl-3 py-0.5 text-zinc-300'
                    : msg.role === 'user'
                      ? 'rounded-2xl rounded-tr-sm bg-sky-800/40 border border-sky-700/50 px-4 py-2.5 text-zinc-100 shadow-sm'
                      : 'text-zinc-200'
                }`}>
                  {editingIdx === i ? (
                    <InlineEditor
                      text={msg.text || ''}
                      onSave={(newText) => {
                        setEditingIdx(null)
                        onEdit(i, newText)
                      }}
                      onCancel={() => setEditingIdx(null)}
                    />
                  ) : msg.role === 'agent' ? (
                    <>
                      {msg.streamingReasoning && (
                        <StreamingReasoningBlock text={msg.streamingReasoning} />
                      )}
                      {showToolCalls !== false && msg.parts && <TurnParts parts={msg.parts} />}
                      <MemoizedMarkdown text={msg.text} />
                    </>
                  ) : (
                    <span className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{msg.text}</span>
                  )}
                </div>
                {msg.role === 'user' && i < messages.length - 1 && (
                  <button
                    onClick={() => onRevert(i)}
                    className="mt-1 text-[10px] text-zinc-600 hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-0.5 flex items-center gap-1"
                    title="回退到此消息"
                  >
                    <Icon name="undo" size={10} /> 回退
                  </button>
                )}
                {!streaming && msg.text && editingIdx !== i && (
                  <button
                    onClick={() => setEditingIdx(i)}
                    className="mt-1 text-[10px] text-zinc-600 hover:text-sky-400 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-0.5 flex items-center gap-1"
                    title="编辑此消息"
                  >
                    <Icon name="edit" size={10} /> 编辑
                  </button>
                )}
                {msg.role === 'agent' && onRetry && ((msg as any).retry || (msg.text && msg.text.startsWith('⚠️'))) && (
                  <button
                    onClick={() => onRetry(i)}
                    className="mt-1 text-[10px] text-zinc-500 hover:text-amber-400 transition-colors px-2 py-0.5 flex items-center gap-1"
                  >
                    <Icon name="refresh" size={10} /> 重试
                  </button>
                )}
                {msg.role === 'agent' && msg.text && msg.text.length > 100 && !msg.text.startsWith('✅') && !msg.text.startsWith('⚠️') && !msg.text.startsWith('🔍') && (
                  <button
                    onClick={() => onValidate(msg.text)}
                    className="mt-1 text-[10px] text-zinc-600 hover:text-zinc-400 px-2 py-0.5 transition-colors flex items-center gap-1"
                  >
                    <Icon name="search" size={10} /> 校验一致性
                  </button>
                )}
              </div>
              </>
              )}
            </div>
          )
        })}
        {(streaming || uploading) && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-800/60 to-sky-900/80 border border-sky-700/50 flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
              <Icon name="lightbulb" size={14} className="text-sky-300" />
            </div>
            <div className="flex items-center gap-2.5 mt-1.5">
              <Icon name="loader" size={14} className="text-sky-400/80 animate-spin" />
              <span className="text-[11px] text-zinc-500">{uploading ? '上传中…' : '思考中…'}</span>
            </div>
          </div>
        )}
        {progress && <ProgressIndicator progress={progress} />}
        {workflowData && <WorkflowProgress data={workflowData} />}
        {patchData && <PatchNotification data={patchData} />}
        {plotCards && <PlotCardSelector data={plotCards} onSelect={onPlotCardSelect} onReject={onPlotCardReject} />}
        {question && <QuestionCard question={question} onReply={onQuestionReply} onReject={onQuestionReject} />}
      </div>
      {showJumpDown && (
        <button
          onClick={() => scrollToBottom(true)}
          className="absolute bottom-4 right-6 flex items-center gap-1.5 text-[11px] text-zinc-300 bg-zinc-800/95 border border-zinc-600/70 rounded-full px-3 py-1.5 shadow-lg hover:bg-zinc-700 transition-colors"
          title="回到最新消息"
        >
          <Icon name="arrow-down" size={11} />
          回到底部
        </button>
      )}
    </div>
  )
}