import { useRef, useEffect } from 'react'
import Icon from '../ui/Icon.jsx'

export default function WritingPreview({ data }) {
  const scrollRef = useRef(null)
  const isAtBottomRef = useRef(true)

  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [data?.text])

  if (!data) return null

  const { chapterTitle, text, saved, wordCount, partial } = data

  return (
    <div className="flex flex-col border-b border-zinc-800" style={{ minHeight: '40%', maxHeight: '60%' }}>
      <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-300">✍️ 写作: {chapterTitle || '...'}</span>
        {saved && (
          <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded flex items-center gap-0.5 ${partial ? 'bg-amber-900/50 text-amber-400' : 'bg-green-900/50 text-green-400'}`}>
            {partial ? <><Icon name="alert-circle" size={10} /> 部分保存</> : <><Icon name="check-circle" size={10} /> 已保存 {wordCount || 0}字</>}
          </span>
        )}
        {!saved && text && (
          <span className="ml-auto text-[10px] text-zinc-500">{text.length}字</span>
        )}
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-zinc-300 font-serif"
        onScroll={(e) => {
          const el = e.target
          isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
        }}
      >
        {text || '等待生成...'}
      </div>
    </div>
  )
}
