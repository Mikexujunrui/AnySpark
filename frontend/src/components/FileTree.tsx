import { useState, useEffect } from 'react'
import { showToast } from './ui/toast-utils'
import Icon from './ui/Icon'
import { openTab } from '../stores/tabStore'

export default function FileTree({ bookId, onSelectChapter }: { bookId: string; onSelectChapter?: (ch: any) => void }) {
  const [volumes, setVolumes] = useState([])
  const [ungrouped, setUngrouped] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState({})
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!bookId) return
    loadVolumes()
  }, [bookId])

  async function loadVolumes() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/volumes`)
      const data = await res.json()
      setVolumes(data.volumes || [])
      setUngrouped(data.ungrouped_chapters || [])
      // Expand first volume by default
      if (data.volumes?.length > 0) {
        setExpanded({ [data.volumes[0].id]: true })
      }
    } catch (e) {
      showToast('加载文件树失败', 'error')
    }
    setLoading(false)
  }

  function toggleVolume(id) {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }

  function handleChapterClick(chapter) {
    openTab(chapter.id, chapter.title, bookId)
    onSelectChapter?.(chapter)
  }

  const filteredVolumes = search
    ? volumes.map(v => ({
        ...v,
        chapters: (v.chapters || []).filter(c =>
          c.title.toLowerCase().includes(search.toLowerCase())
        ),
      })).filter(v => v.chapters.length > 0 || v.title.toLowerCase().includes(search.toLowerCase()))
    : volumes

  const filteredUngrouped = search
    ? ungrouped.filter(c => c.title.toLowerCase().includes(search.toLowerCase()))
    : ungrouped

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-600 text-xs">
        加载中...
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-zinc-950/50">
      {/* Search */}
      <div className="p-3 border-b border-zinc-800">
        <div className="relative">
          <Icon name="search" size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索章节..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {/* Volumes */}
        {filteredVolumes.map(vol => (
          <div key={vol.id}>
            <button
              onClick={() => toggleVolume(vol.id)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors"
            >
              <Icon
                name={expanded[vol.id] ? 'chevron-down' : 'chevron-right'}
                size={10}
                className="text-zinc-600 shrink-0"
              />
              <Icon name="folder" size={12} className="text-amber-500 shrink-0" />
              <span className="font-medium truncate">{vol.title || '未命名分卷'}</span>
              <span className="text-zinc-600 text-[10px] ml-auto">
                {(vol.chapters || []).length}章
              </span>
            </button>
            {expanded[vol.id] && (vol.chapters || []).map((ch, i) => (
              <button
                key={ch.id}
                onClick={() => handleChapterClick(ch)}
                className="w-full flex items-center gap-2 pl-8 pr-2 py-1.5 rounded text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
              >
                <Icon name="file-text" size={12} className="text-zinc-600 shrink-0" />
                <span className="truncate">{ch.title || `第${i + 1}章`}</span>
              </button>
            ))}
          </div>
        ))}

        {/* Ungrouped chapters */}
        {filteredUngrouped.length > 0 && (
          <>
            {filteredVolumes.length > 0 && (
              <div className="flex items-center gap-2 px-2 py-2 mt-1">
                <div className="flex-1 h-px bg-zinc-800" />
                <span className="text-[10px] text-zinc-600">未分类</span>
                <div className="flex-1 h-px bg-zinc-800" />
              </div>
            )}
            {filteredUngrouped.map((ch, i) => (
              <button
                key={ch.id}
                onClick={() => handleChapterClick(ch)}
                className="w-full flex items-center gap-2 pl-4 pr-2 py-1.5 rounded text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
              >
                <Icon name="file-text" size={12} className="text-zinc-600 shrink-0" />
                <span className="truncate">{ch.title || `未分类章节 ${i + 1}`}</span>
              </button>
            ))}
          </>
        )}

        {filteredVolumes.length === 0 && filteredUngrouped.length === 0 && (
          <p className="text-xs text-zinc-600 text-center py-8">
            {search ? '未找到匹配的章节' : '暂无分卷，在章节面板中创建'}
          </p>
        )}
      </div>
    </div>
  )
}
