// ChapterOutlinePanel — chapter outline / detailed-outline viewer for
// ChaptersPanel (extracted to slim the parent). Pure presentational.
import Icon from './ui/Icon'

interface Props {
  chapterTitle: string
  viewMode: string
  setViewMode: (m: 'outline' | 'detailed') => void
  loading: boolean
  outline: {
    synopsis?: string
    key_events?: string[]
    characters?: string[]
    turning_point?: string
    notes?: string
  } | null
  detailedOutline: {
    chapter_function?: string
    plot_chain?: string[]
  } | null
  onClose: () => void
}

export default function ChapterOutlinePanel({
  chapterTitle,
  viewMode,
  setViewMode,
  loading,
  outline,
  detailedOutline,
  onClose,
}: Props) {
  return (
    <div className="border-b border-zinc-800 bg-zinc-900/80 max-h-80 overflow-y-auto">
      <div className="flex items-center justify-between px-6 py-2 border-b border-zinc-800/50">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-zinc-400">
            本章大纲: {chapterTitle || ''}
          </span>
          <div className="flex gap-0.5">
            <button
              onClick={() => setViewMode('outline')}
              className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                viewMode === 'outline' ? 'bg-amber-900/40 text-amber-300' : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              大纲
            </button>
            <button
              onClick={() => setViewMode('detailed')}
              className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                viewMode === 'detailed' ? 'bg-blue-900/40 text-blue-300' : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              细纲
            </button>
          </div>
        </div>
        <button onClick={onClose} className="text-xs text-zinc-600 hover:text-zinc-300 flex items-center gap-1">
          <Icon name="x" size={12} /> 关闭
        </button>
      </div>
      {loading ? (
        <div className="p-4 text-xs text-zinc-600 text-center">加载中...</div>
      ) : viewMode === 'detailed' ? (
        <div className="p-4 space-y-3">
          {detailedOutline ? (
            <>
              {detailedOutline.chapter_function && (
                <div className="bg-blue-900/20 border border-blue-900/30 rounded-lg p-3">
                  <div className="text-[10px] text-blue-400 mb-1 font-semibold">章节功能</div>
                  <p className="text-xs text-blue-200">{detailedOutline.chapter_function}</p>
                </div>
              )}
              {detailedOutline.plot_chain && detailedOutline.plot_chain.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] text-zinc-500 font-semibold">剧情骨架</div>
                  {detailedOutline.plot_chain.map((event, i) => (
                    <div key={i} className="flex gap-2 text-xs">
                      <span className="text-zinc-600 shrink-0 font-mono">{i + 1}.</span>
                      <span className="text-zinc-300">{event}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-xs text-zinc-600 text-center py-4">
              尚无细纲。使用 AI 的"生成细纲"功能创建。
            </p>
          )}
        </div>
      ) : (
        <div className="p-4 space-y-3">
          {outline ? (
            <>
              {outline.synopsis && (
                <div>
                  <div className="text-[10px] text-zinc-500 mb-1 font-semibold">概要</div>
                  <p className="text-xs text-zinc-300 leading-relaxed">{outline.synopsis}</p>
                </div>
              )}
              {outline.key_events && outline.key_events.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] text-zinc-500 font-semibold">关键事件</div>
                  <div className="flex flex-wrap gap-1">
                    {outline.key_events.map((ev, i) => (
                      <span key={i} className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">
                        {ev}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {outline.characters && outline.characters.length > 0 && (
                <div>
                  <div className="text-[10px] text-zinc-500 mb-1 font-semibold">出场角色</div>
                  <div className="flex flex-wrap gap-1">
                    {outline.characters.map((char, i) => (
                      <span key={i} className="text-[10px] bg-violet-900/30 text-violet-300 px-2 py-0.5 rounded">
                        {char}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {outline.turning_point && (
                <div className="bg-amber-900/20 border border-amber-900/30 rounded-lg p-3">
                  <div className="text-[10px] text-amber-400 mb-1 font-semibold">转折点</div>
                  <p className="text-xs text-amber-200">{outline.turning_point}</p>
                </div>
              )}
              {outline.notes && (
                <div>
                  <div className="text-[10px] text-zinc-500 mb-1 font-semibold">备注</div>
                  <p className="text-xs text-zinc-400">{outline.notes}</p>
                </div>
              )}
            </>
          ) : (
            <p className="text-xs text-zinc-600 text-center py-4">
              本章尚无大纲。使用 AI 的"生成大纲"功能创建。
            </p>
          )}
        </div>
      )}
    </div>
  )
}
