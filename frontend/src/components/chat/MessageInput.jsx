import { useRef, useEffect } from 'react'
import SlashMenu from './SlashMenu.jsx'
import Icon from '../ui/Icon.jsx'

export default function MessageInput({
  input,
  setInput,
  streaming,
  uploading,
  agentMode,
  autonomousMode,
  onAutonomousToggle,
  onSend,
  onCancel,
  onUpload,
  onTransform,
  onModeToggle,
  showSlash,
  setShowSlash,
  setSlashFilter,
  slashItems,
  slashIdx,
  setSlashIdx,
  skillCommands,
  onSlashSelect,
  onSlashNavigate,
  onSlashClose,
}) {
  const fileInputRef = useRef(null)
  const inputRef = useRef(null)

  // Keep textarea height in sync with the input value. Using an effect
  // rather than doing it inside onChange means the height also shrinks
  // back when input is cleared after send (onChange doesn't fire for
  // programmatic value changes).
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    // Short single-line input: force a fixed height without measuring
    // scrollHeight (measurement is unreliable on first mount and pins the
    // textarea to its max). Only grow for genuinely multi-line content.
    if (!input.includes('\n') && input.length < 60) {
      el.style.height = '28px'
      return
    }
    el.style.height = '28px'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }, [input])

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f) }}
        accept=".txt,.md,.docx"
        className="hidden"
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={streaming || uploading}
        className="text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg px-2.5 h-7 flex items-center justify-center transition-colors disabled:opacity-40 shrink-0"
        title="上传文档（txt / md / docx）"
      >
        <Icon name="paperclip" size={16} />
      </button>
      <button
        onClick={onModeToggle}
        disabled={streaming || uploading}
        title={agentMode === 'write' ? 'Write 模式：可提取设定、写章节、编辑知识库' : 'Plan 模式：只读，可检索浏览知识库'}
        className={`rounded-lg px-2.5 h-7 text-[11px] font-medium transition-colors shrink-0 flex items-center gap-1 ${
          agentMode === 'write'
            ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800'
            : 'bg-amber-900/40 text-amber-400 border border-amber-800'
        }`}
      >
        <Icon name={agentMode === 'write' ? 'pen-tool' : 'search'} size={12} />
        {agentMode === 'write' ? 'Write' : 'Plan'}
      </button>
      {onTransform && (
        <button
          onClick={onTransform}
          disabled={streaming || uploading}
          title="全书变换 — 对全书执行批量查找替换、文风调整等"
          className="rounded-lg px-2.5 h-7 text-[11px] font-medium transition-all shrink-0 flex items-center gap-1 bg-violet-900/30 text-violet-300 border border-violet-800/60 hover:bg-violet-900/50 hover:border-violet-700 active:scale-95 disabled:opacity-40"
        >
          <Icon name="layers" size={12} />
          全书变换
        </button>
      )}
      {onAutonomousToggle && (
        <button
          onClick={onAutonomousToggle}
          disabled={streaming || uploading}
          title={autonomousMode ? '自主模式：Agent 可直接执行删除等危险操作，点击关闭' : '点击启用自主模式：Agent 执行危险操作无需每次确认'}
          className={`rounded-lg px-2.5 h-7 text-[11px] font-medium transition-all shrink-0 flex items-center gap-1 ${
            autonomousMode
              ? 'bg-red-900/40 text-red-400 border border-red-800 hover:bg-red-900/60'
              : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700 hover:text-zinc-300'
          }`}
        >
          <Icon name="shield" size={12} />
          {autonomousMode ? '自主' : '自主'}
        </button>
      )}
      <div className="flex-1 relative">
        <textarea
          ref={inputRef}
          value={input}
          rows={1}
          onChange={(e) => {
            const v = e.target.value
            setInput(v)
            const isSlash = v.startsWith('/') && !v.includes(' ')
            setShowSlash(isSlash)
            setSlashFilter(isSlash ? v.slice(1) : '')
            setSlashIdx(0)
          }}
          onKeyDown={(e) => {
            if (showSlash && slashItems.length > 0) {
              const menuEl = document.querySelector('[data-slash-menu]')
              if (menuEl && menuEl._slashNav) {
                const handled = menuEl._slashNav(e)
                if (handled) return
              }
            }
            if (e.key === 'Enter' && !e.shiftKey && !streaming) { e.preventDefault(); onSend(); }
            if (e.key === 'Escape' && streaming) { onCancel(); }
          }}
          placeholder="输入 / 查看所有命令，或用自然语言描述需求 (Shift+Enter 换行)"
          disabled={streaming || uploading}
          className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500 disabled:opacity-50 placeholder-zinc-500 w-full resize-none overflow-y-auto box-border h-7 min-h-[28px] max-h-[120px] leading-tight"
        />
        {showSlash && (
          <SlashMenu
            items={slashItems}
            selectedIdx={slashIdx}
            allSkills={skillCommands}
            onSelect={(s) => { onSlashSelect(s); if (inputRef.current) inputRef.current.focus() }}
            onNavigate={(i) => onSlashNavigate(i)}
            onClose={onSlashClose}
          />
        )}
      </div>
      {streaming ? (
        <button
          onClick={onCancel}
          className="bg-red-900/60 text-red-300 border border-red-800 rounded-lg px-3 h-7 text-sm font-medium hover:bg-red-800/60 hover:text-red-200 active:scale-95 transition-all shrink-0 flex items-center gap-1"
        >
          <Icon name="stop" size={13} /> 中止
        </button>
      ) : (
        <button
          onClick={onSend}
          disabled={uploading || !input.trim()}
          className="bg-accent text-white rounded-lg px-3 h-7 text-sm font-medium hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-40 shrink-0 flex items-center gap-1 shadow-sm"
        >
          <Icon name="send" size={13} /> 发送
        </button>
      )}
    </div>
  )
}
