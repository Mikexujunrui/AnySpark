// ChapterOutlinePanel — 章节大纲面板（V4 适配版）
// 数据：getOutline（/api/plan → {outline: [...]}）→ outline.chapters[chIdx]
import Icon from './ui/Icon'

interface Props {
  chapterTitle?: string
  viewMode?: string
  setViewMode?: (v: string) => void
  loading?: boolean
  outline?: Record<string, any> | null
  detailedOutline?: Record<string, any> | null
  onClose?: () => void
}

export default function ChapterOutlinePanel({
  chapterTitle = '', viewMode = 'outline', setViewMode,
  loading = false, outline, detailedOutline, onClose,
}: Props) {
  const items = outline?.items || outline?.sections || (outline && typeof outline === 'object' ? Object.entries(outline).filter(([k]) => !['id', 'title', 'book_id'].includes(k)).map(([k, v]) => ({ title: k, content: String(v) })) : [])

  return (
    <div className="border-b border-zinc-800 bg-zinc-900/50 px-3 py-2 shrink-0">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[11px] font-medium text-zinc-300 truncate flex-1">
          <Icon name="list" size={11} className="inline mr-1 text-zinc-500" />
          {chapterTitle || '章节'} · 大纲
        </span>
        <div className="flex bg-zinc-800 rounded p-0.5">
          {(['outline', 'detail'] as const).map(m => (
            <button
              key={m}
              onClick={() => setViewMode?.(m)}
              className={`px-2 py-0.5 rounded text-[10px] ${viewMode === m ? 'bg-zinc-600 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              {m === 'outline' ? '大纲' : '详细'}
            </button>
          ))}
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 text-zinc-500 hover:text-zinc-300">
            <Icon name="x" size={13} />
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-2 text-zinc-500 text-[11px]">
          <div className="w-3.5 h-3.5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
          加载大纲...
        </div>
      ) : Array.isArray(items) && items.length > 0 ? (
        <div className="space-y-0.5 max-h-40 overflow-y-auto pr-1">
          {items.map((it: any, i: number) => (
            <div key={i} className="flex items-start gap-1.5 py-0.5">
              <span className="text-[10px] text-zinc-600 mt-0.5 shrink-0">{i + 1}.</span>
              <div className="min-w-0">
                <span className="text-[11px] text-zinc-300">{it.title || it.content || String(it)}</span>
                {viewMode === 'detail' && it.content && (
                  <p className="text-[10px] text-zinc-500 truncate">{it.content}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-zinc-600 py-1">暂无大纲数据（可在「大纲」面板添加章节计划）</p>
      )}
    </div>
  )
}
