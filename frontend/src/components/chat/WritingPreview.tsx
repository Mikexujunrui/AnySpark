import { useRef, useEffect, useState } from 'react'
import Icon from '../ui/Icon'

export default function WritingPreview({ data, onClose }) {
  const scrollRef = useRef(null)
  const isAtBottomRef = useRef(true)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [data?.text])

  if (!data) return null

  const { chapterTitle, text, saved, wordCount, partial, failed, error } = data

  return (
    <div className="flex flex-col border-b border-zinc-800 min-w-0" style={collapsed ? undefined : { minHeight: '40%', maxHeight: '60%' }}>
      <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-300 truncate"><Icon name="edit" size={12} className="inline mr-1" />写作: {chapterTitle || '...'}</span>
        {saved && (
          <span className={`ml-auto shrink-0 text-[10px] px-1.5 py-0.5 rounded flex items-center gap-0.5 ${partial ? 'bg-amber-900/50 text-amber-400' : 'bg-green-900/50 text-green-400'}`}>
            {partial ? <><Icon name="alert-circle" size={10} /> 部分保存</> : <><Icon name="check-circle" size={10} /> 已保存 {wordCount || 0}字</>}
          </span>
        )}
        {failed && <span className="ml-auto shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-red-950/60 text-red-400 flex items-center gap-0.5"><Icon name="alert-circle" size={10} /> 未保存</span>}
        {!saved && !failed && text && <span className="ml-auto shrink-0 text-[10px] text-zinc-500">{text.length}字</span>}
        <button
          onClick={() => setCollapsed(v => !v)}
          className="p-0.5 text-zinc-500 hover:text-zinc-200 rounded"
          title={collapsed ? '展开写作预览' : '收起写作预览'}
        >
          <Icon name={collapsed ? 'chevron-down' : 'chevron-up'} size={13} />
        </button>
        <button onClick={onClose} className="p-0.5 text-zinc-500 hover:text-zinc-200 rounded" title="关闭写作预览">
          <Icon name="x" size={13} />
        </button>
      </div>
      {!collapsed && (
        <div
          ref={scrollRef}
          className="flex-1 min-w-0 overflow-y-auto px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-zinc-300 font-serif"
          onScroll={(e) => {
            const el = e.target as HTMLElement
            isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
          }}
        >
          {error && <div className="mb-2 rounded border border-red-900/60 bg-red-950/30 p-2 text-xs text-red-300 break-words">{error}</div>}
          {text || (failed ? '本次未生成可保存的正文。' : '等待生成...')}
        </div>
      )}
    </div>
  )
}
