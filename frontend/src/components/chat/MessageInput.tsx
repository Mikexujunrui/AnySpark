import { useRef, useEffect } from 'react'
import SlashMenu from './SlashMenu'
import Icon from '../ui/Icon'
import type { QueueItem } from '../../api/chat'

export default function MessageInput({
  input,
  setInput,
  streaming,
  uploading,
  autonomousMode,
  onAutonomousToggle,
  onSend,
  onCancel,
  onQueue,
  onSteer,
  onUpload,
  queue,
  onDequeue,
  onSteerQueued,
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

  const hasInput = input.trim().length > 0

  return (
    <div className="w-full">
      {/* S99 排队消息条：输入框上方一小排，可删除 / 转插入 */}
      {queue && queue.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 mb-1.5 px-1" data-queue-strip>
          <span className="text-[10px] text-zinc-500 flex items-center gap-0.5 shrink-0">
            <Icon name="list" size={10} /> 排队 {queue.length}
          </span>
          {queue.map((item) => (
            <span
              key={item.id}
              className="group inline-flex items-center gap-1 bg-zinc-800/80 border border-zinc-700 rounded-md pl-2 pr-1 py-0.5 text-[11px] text-zinc-300 max-w-[220px]"
              title={item.text}
            >
              <span className="truncate">{item.text}</span>
              <button
                onClick={() => onSteerQueued?.(item.id)}
                className="p-0.5 text-zinc-500 hover:text-sky-400 rounded shrink-0 transition-colors"
                title="转插入：立即注入当前运行轮（steer）"
                aria-label={`转插入：${item.text}`}
              >
                <Icon name="arrow-right-circle" size={11} />
              </button>
              <button
                onClick={() => onDequeue?.(item.id)}
                className="p-0.5 text-zinc-500 hover:text-red-400 rounded shrink-0 transition-colors"
                title="删除这条排队消息"
                aria-label={`删除排队：${item.text}`}
              >
                <Icon name="x" size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
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
        {onAutonomousToggle && (
          <button
            onClick={onAutonomousToggle}
            disabled={streaming || uploading}
            title={
              autonomousMode
                ? '全自动模式：所有工具免确认连续执行（含删除与修改原稿）'
                : '点击启用全自动模式；所有操作免确认，请谨慎开启'
            }
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
              // IME Enter confirms the current Chinese/Japanese candidate; it
              // must not send the message. keyCode 229 covers older WebViews.
              if (e.nativeEvent.isComposing || e.keyCode === 229) return
              if (showSlash && slashItems.length > 0) {
                const menuEl: any = document.querySelector('[data-slash-menu]')
                if (menuEl && menuEl._slashNav) {
                  const handled = menuEl._slashNav(e)
                  if (handled) return
                }
              }
              // S99：streaming 时输入框可用，回车 = 排队（接力执行，非发送）
              if (e.key === 'Enter' && !e.shiftKey) {
                if (streaming) { e.preventDefault(); onQueue?.() }
                else if (hasInput) { e.preventDefault(); onSend() }
              }
              if (e.key === 'Escape' && streaming) { onCancel(); }
            }}
            placeholder={
              streaming
                ? '任务运行中：回车排队下一条指令，或点「插入指导」即时干预'
                : '输入 / 查看所有命令，或用自然语言描述需求 (Shift+Enter 换行)'
            }
            disabled={uploading}
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
          <>
            {hasInput && onSteer && (
              <button
                onClick={onSteer}
                className="bg-sky-900/50 text-sky-300 border border-sky-800 rounded-lg px-3 h-7 text-sm font-medium hover:bg-sky-800/60 hover:text-sky-200 active:scale-95 transition-all shrink-0 flex items-center gap-1"
                title="立即把输入内容注入当前运行轮（工具结果后、下轮 LLM 前生效）"
              >
                <Icon name="arrow-right-circle" size={13} /> 插入指导
              </button>
            )}
            <button
              onClick={onCancel}
              className="bg-red-900/60 text-red-300 border border-red-800 rounded-lg px-3 h-7 text-sm font-medium hover:bg-red-800/60 hover:text-red-200 active:scale-95 transition-all shrink-0 flex items-center gap-1"
            >
              <Icon name="stop" size={13} /> 中止
            </button>
          </>
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
    </div>
  )
}
