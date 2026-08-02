// ChapterSidebar — chapter list sidebar for ChaptersPanel (extracted to slim
// the parent). Contains the search filter, volume-grouping and drag-drop logic.
import { useRef } from 'react'
import Icon from './ui/Icon'

interface Chapter {
  id: string
  title?: string
  content?: string
  is_extra?: boolean
  status?: string
  version_label?: string
  version_count?: number
}

interface Volume {
  id: string
  title?: string
  chapters?: { id: string }[]
}

interface Props {
  regularChapters: Chapter[]
  extraChapters: Chapter[]
  volumes: Volume[]
  chapterSearch: string
  setChapterSearch: (v: string) => void
  selectedId: string | null
  selectChapter: (ch: Chapter) => void
  handleCreate: (isExtra: boolean) => void
  showCreateMenu: boolean
  setShowCreateMenu: (v: boolean) => void
  createMenuRef: React.RefObject<HTMLDivElement | null>
  focusMode: boolean
  recentlyEdited: ReadonlySet<unknown>
  dragChapterId: string | null
  dragOverChapterId: string | null
  handleDragStart: (e: React.DragEvent, chId: string) => void
  handleDragOver: (e: React.DragEvent, chId: string) => void
  handleDragLeave: () => void
  handleDrop: (e: React.DragEvent, targetId: string) => void
  handleDragEnd: () => void
}

export default function ChapterSidebar({
  regularChapters,
  extraChapters,
  volumes,
  chapterSearch,
  setChapterSearch,
  selectedId,
  selectChapter,
  handleCreate,
  showCreateMenu,
  setShowCreateMenu,
  createMenuRef,
  focusMode,
  recentlyEdited,
  dragChapterId,
  dragOverChapterId,
  handleDragStart,
  handleDragOver,
  handleDragLeave,
  handleDrop,
  handleDragEnd,
}: Props) {
  const menuRef = useRef<HTMLDivElement | null>(null)

  return (
    <div className={`w-56 border-r border-zinc-800 bg-zinc-950/50 flex flex-col shrink-0 transition-all duration-300 ${focusMode ? 'w-0 overflow-hidden border-r-0' : ''}`}>
      <div className="p-3 border-b border-zinc-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Icon name="file-text" size={14} /> 章节 ({regularChapters.length})
          </span>
          <div className="relative" ref={createMenuRef ?? menuRef}>
            <button
              onClick={() => setShowCreateMenu(!showCreateMenu)}
              className="text-xs text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-0.5 transition-colors flex items-center gap-1"
            >
              <Icon name="plus" size={12} /> 新建
            </button>
            {showCreateMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden min-w-28">
                <button
                  onClick={() => handleCreate(false)}
                  className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors flex items-center gap-2"
                >
                  <Icon name="file-text" size={12} /> 新建章节
                </button>
                <button
                  onClick={() => handleCreate(true)}
                  className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors flex items-center gap-2 border-t border-zinc-700"
                >
                  <Icon name="star" size={12} /> 新建番外
                </button>
              </div>
            )}
          </div>
        </div>
        {/* Search input */}
        <div className="relative">
          <Icon name="search" size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={chapterSearch}
            onChange={(e) => setChapterSearch(e.target.value)}
            placeholder="搜索章节..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {(() => {
          const filteredRegular = chapterSearch
            ? regularChapters.filter(c =>
                (c.title || '').toLowerCase().includes(chapterSearch.toLowerCase()) ||
                (c.content || '').toLowerCase().includes(chapterSearch.toLowerCase())
              )
            : regularChapters;
          const filteredExtra = chapterSearch
            ? extraChapters.filter(c =>
                (c.title || '').toLowerCase().includes(chapterSearch.toLowerCase()) ||
                (c.content || '').toLowerCase().includes(chapterSearch.toLowerCase())
              )
            : extraChapters;

          if (filteredRegular.length === 0 && filteredExtra.length === 0) {
            return (
              <p className="text-xs text-zinc-600 text-center py-8">
                {chapterSearch ? '未找到匹配的章节' : '暂无章节'}
              </p>
            );
          }

          // Build volume→chapters mapping from filtered results
          const volColors = ['bg-sky-500', 'bg-violet-500', 'bg-amber-500', 'bg-emerald-500', 'bg-rose-500', 'bg-blue-500', 'bg-purple-500']
          const volBgColors = ['bg-sky-950/30', 'bg-violet-950/30', 'bg-amber-950/30', 'bg-emerald-950/30', 'bg-rose-950/30', 'bg-blue-950/30', 'bg-purple-950/30']
          const volBorderColors = ['border-sky-800/40', 'border-violet-800/40', 'border-amber-800/40', 'border-emerald-800/40', 'border-rose-800/40', 'border-blue-800/40', 'border-purple-800/40']
          const groupedByVol: Record<string, Chapter[]> = {}
          const ungrouped: Chapter[] = []
          const groupedIds = new Set<string>()
          volumes.forEach(v => {
            const volChapters = (v.chapters || []).map((vc: any) => vc.id)
            filteredRegular.forEach(ch => {
              if (volChapters.includes(ch.id)) {
                if (!groupedByVol[v.id]) groupedByVol[v.id] = []
                groupedByVol[v.id].push(ch)
                groupedIds.add(ch.id)
              }
            })
          })
          filteredRegular.forEach(ch => {
            if (!groupedIds.has(ch.id)) ungrouped.push(ch)
          })

          // Global chapter index for #N display
          let globalIdx = 0

          function renderChapterButton(ch: any, idx: number, isExtra = false) {
            globalIdx++
            const isDragging = dragChapterId === ch.id
            const isDragOver = dragOverChapterId === ch.id && dragChapterId !== ch.id
            return (
              <button
                key={ch.id}
                onClick={() => selectChapter(ch)}
                draggable
                onDragStart={(e) => handleDragStart(e, ch.id)}
                onDragOver={(e) => handleDragOver(e, ch.id)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, ch.id)}
                onDragEnd={handleDragEnd}
                className={`group w-full text-left px-3 py-2 rounded-lg text-xs transition-all relative ${
                  selectedId === ch.id
                    ? isExtra
                      ? 'bg-violet-900/40 text-zinc-100 border border-violet-700/30 shadow-sm'
                      : 'bg-zinc-700 text-zinc-100 shadow-sm'
                    : isExtra
                      ? 'text-zinc-500 hover:text-zinc-300 hover:bg-violet-950/30'
                      : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
                } ${isDragging ? 'opacity-40' : ''} ${isDragOver ? 'border-t-2 border-t-sky-400 bg-zinc-800/60' : ''}`}
              >
                {selectedId === ch.id && (
                  <span className={`absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-r ${isExtra ? 'bg-violet-400' : 'bg-sky-400'}`} />
                )}
                <div className="flex items-center gap-1.5">
                  {isExtra && <Icon name="star" size={10} className="text-violet-400 shrink-0" />}
                  <Icon name="grip-vertical" size={10} className="text-zinc-700 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab" />
                  <p className="font-medium truncate flex-1">{ch.title || '无标题'}</p>
                  {recentlyEdited.has(ch.id) && (
                    <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shrink-0" title="刚刚编辑" />
                  )}
                </div>
                <div className="flex items-center gap-2 text-zinc-600 text-[10px] mt-0.5">
                  <span className={`${isExtra ? 'text-violet-700' : 'text-zinc-700'} font-mono`}>#{isExtra ? `E${idx + 1}` : idx + 1}</span>
                  <span>{(ch.content || '').replace(/\s/g, '').length || 0} 字</span>
                  <span className={`px-1 rounded font-mono ${
                    ch.version_label?.includes('.')
                      ? 'bg-sky-900/50 text-sky-400'
                      : ch.version_count > 1 ? 'bg-zinc-700 text-zinc-300' : 'bg-zinc-800/50 text-zinc-600'
                  }`}>{ch.version_label || `v${ch.version_count || 1}`}</span>
                  {ch.status === 'final' && (
                    <span className="text-[10px] bg-emerald-900/40 text-emerald-400 px-1 rounded ml-1 inline-flex items-center gap-0.5" title="定稿"><Icon name="check" size={10} /></span>
                  )}
                </div>
              </button>
            )
          }

          return (
            <>
              {/* Volume-grouped chapters */}
              {volumes.length > 0 && volumes.map((vol, vi) => {
                const volChapters = groupedByVol[vol.id] || []
                if (volChapters.length === 0) return null
                const colorIdx = vi % volColors.length
                return (
                  <div key={vol.id} className="mb-1">
                    <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${volBgColors[colorIdx]} border ${volBorderColors[colorIdx]}`}>
                      <span className={`w-1.5 h-4 rounded-full ${volColors[colorIdx]}`} />
                      <span className="text-[11px] font-semibold text-zinc-300 truncate flex-1">{vol.title || '未命名卷'}</span>
                      <span className="text-[9px] text-zinc-500 shrink-0">{volChapters.length}章</span>
                    </div>
                    <div className="ml-2 mt-0.5 space-y-0.5 border-l border-zinc-800/50 pl-2">
                      {volChapters.map(ch => {
                        return renderChapterButton(ch, globalIdx)
                      })}
                    </div>
                  </div>
                )
              })}

              {/* Ungrouped chapters */}
              {ungrouped.length > 0 && (
                <div className="mb-1">
                  {volumes.length > 0 && (
                    <div className="flex items-center gap-2 px-2 py-1.5">
                      <span className="w-1.5 h-4 rounded-full bg-zinc-600" />
                      <span className="text-[11px] font-semibold text-zinc-500">未分卷</span>
                      <span className="text-[9px] text-zinc-600">{ungrouped.length}章</span>
                    </div>
                  )}
                  <div className={`ml-2 mt-0.5 space-y-0.5 ${volumes.length > 0 ? 'border-l border-zinc-800/50 pl-2' : ''}`}>
                    {ungrouped.map(ch => renderChapterButton(ch, globalIdx))}
                  </div>
                </div>
              )}

              {/* Extras */}
              {filteredExtra.length > 0 && (
                <>
                  <div className="flex items-center gap-2 px-2 py-2 mt-2">
                    <div className="flex-1 h-px bg-zinc-800" />
                    <span className="text-[10px] text-zinc-600 font-medium">番外 ({filteredExtra.length})</span>
                    <div className="flex-1 h-px bg-zinc-800" />
                  </div>
                  {filteredExtra.map((ch, i) => renderChapterButton(ch, i, true))}
                </>
              )}
            </>
          );
        })()}
      </div>
    </div>
  )
}
