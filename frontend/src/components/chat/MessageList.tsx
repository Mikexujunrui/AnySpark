import { useRef, useEffect, useState, memo } from 'react'
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
    <div className="markdown-body">
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

function ReasoningBlock({ text }) {
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
        思考过程{open ? '' : `（${text.length}字）`}
      </button>
      {open && (
        <div className="mt-1 text-[11px] text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded-md p-2 max-h-48 overflow-y-auto whitespace-pre-wrap italic">
          {text}
        </div>
      )}
    </div>
  )
}

function TurnParts({ parts }) {
  if (!parts || parts.length === 0) return null
  const toolCalls = parts.filter(p => p.type === 'tool_call')
  const diffs = parts.filter(p => p.type === 'chapter_diff')
  const reasoning = parts.filter(p => p.type === 'reasoning').map(p => p.text).join('')
  return (
    <div className="space-y-1 mb-2">
      {reasoning && <ReasoningBlock text={reasoning} />}
      {diffs.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {diffs.map((d, i) => <ChapterDiffBadge key={i} part={d} />)}
        </div>
      )}
      {toolCalls.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {toolCalls.map((tc, i) => <ToolCallCard key={i} part={tc} />)}
        </div>
      )}
    </div>
  )
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
  const bottomRef = useRef(null)
  const isAtBottomRef = useRef(true)
  const [editingIdx, setEditingIdx] = useState(null)

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  return (
    <div
      className="flex-1 overflow-y-auto px-6 py-5 space-y-5"
      ref={scrollContainerRef}
      onScroll={(e) => {
        const el = e.target as HTMLElement
        isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
      }}
    >
      {(Array.isArray(messages) ? messages : []).map((msg, i) => (
        <div key={i} className={`flex gap-3 group ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
          {msg.role === 'agent' && (
            <div className="w-7 h-7 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center shrink-0 mt-0.5">
              <Icon name="lightbulb" size={13} className="text-sky-400" />
            </div>
          )}
          <div className={`flex flex-col max-w-[min(640px,90%)] ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            {msg.role === 'user' && (
              <span className="text-[10px] text-zinc-500 mb-1 mr-1">你</span>
            )}
            <div className={`rounded-xl px-4 py-3 text-sm leading-relaxed ${
              msg.autopilot
                ? 'bg-purple-900/20 border border-purple-700/40 text-zinc-200'
                : msg.role === 'user'
                  ? 'bg-sky-900/20 border border-sky-800/40 text-zinc-100'
                  : 'bg-zinc-800/80 border border-zinc-700 text-zinc-200'
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
                  {showToolCalls !== false && msg.parts && <TurnParts parts={msg.parts} />}
                  <MemoizedMarkdown text={msg.text} />
                </>
              ) : (
                <span className="whitespace-pre-wrap">{msg.text}</span>
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
            {msg.role === 'agent' && msg.text && msg.text.startsWith('⚠️') && onRetry && (
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
        </div>
      ))}
      {(streaming || uploading) && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center shrink-0 mt-0.5">
            <Icon name="lightbulb" size={13} className="text-sky-400" />
          </div>
          <div className="bg-zinc-800/80 border border-zinc-700 rounded-xl px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-sky-400/70 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full bg-sky-400/70 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 rounded-full bg-sky-400/70 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-[11px] text-zinc-500">{uploading ? '上传中...' : '处理中...'}</span>
            </div>
          </div>
        </div>
      )}
      {progress && <ProgressIndicator progress={progress} />}
      {workflowData && <WorkflowProgress data={workflowData} />}
      {patchData && <PatchNotification data={patchData} />}
      {plotCards && <PlotCardSelector data={plotCards} onSelect={onPlotCardSelect} onReject={onPlotCardReject} />}
      {question && <QuestionCard question={question} onReply={onQuestionReply} onReject={onQuestionReject} />}
      <div ref={bottomRef} />
    </div>
  )
}
