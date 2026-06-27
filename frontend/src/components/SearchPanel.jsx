import { useState, useRef, useEffect, useCallback } from 'react'
import { showToast } from './ui/Toast.jsx'
import Icon from './ui/Icon.jsx'
import { openTab } from '../stores/tabStore.js'
import { triggerRefresh } from '../store.js'

export default function SearchPanel({ bookId, onClose }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeGroup, setActiveGroup] = useState('all')
  const inputRef = useRef(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const doSearch = useCallback(async () => {
    const q = query.trim()
    if (!q || q.length < 1) {
      setResults(null)
      return
    }
    setLoading(true)
    try {
      const [chaptersRes, entitiesRes] = await Promise.all([
        fetch(`/api/books/${bookId}/search/chapters?q=${encodeURIComponent(q)}&limit=20`),
        fetch(`/api/books/${bookId}/search/entities?q=${encodeURIComponent(q)}&limit=20`),
      ])
      const chapters = await chaptersRes.json()
      const entities = await entitiesRes.json()

      const chapterResults = Array.isArray(chapters) ? chapters : (chapters.results || [])
      const entityResults = Array.isArray(entities) ? entities : (entities.results || [])

      setResults({
        chapters: chapterResults,
        entities: entityResults,
        total: chapterResults.length + entityResults.length,
      })

      if (chapterResults.length === 0 && entityResults.length === 0) {
        showToast('未找到匹配结果', 'info')
      }
    } catch (e) {
      showToast('搜索失败', 'error')
    }
    setLoading(false)
  }, [query, bookId])

  useEffect(() => {
    const timer = setTimeout(doSearch, 300)
    return () => clearTimeout(timer)
  }, [query, doSearch])

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      onClose?.()
    }
    if (e.key === 'Enter') {
      doSearch()
    }
  }

  function handleChapterClick(ch) {
    openTab(ch.id || ch.chapter_id, ch.title || '章节', bookId)
    onClose?.()
  }

  function handleEntityClick(entity) {
    triggerRefresh()
    onClose?.()
  }

  const chapters = results?.chapters || []
  const entities = results?.entities || []
  const hasChapters = chapters.length > 0
  const hasEntities = entities.length > 0
  const total = results?.total || 0

  return (
    <div className="flex flex-col h-full bg-zinc-950">
      {/* Header with search input */}
      <div className="p-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="搜索章节内容、角色、地点..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-9 pr-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-sky-500 transition-colors"
            />
            {loading && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <span className="w-3 h-3 border-2 border-zinc-500 border-t-sky-400 rounded-full animate-spin inline-block" />
              </div>
            )}
          </div>
          {onClose && (
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors">
              <Icon name="x" size={16} />
            </button>
          )}
        </div>

        {/* Result group tabs */}
        {results && total > 0 && (
          <div className="flex gap-1 mt-2">
            {[
              { key: 'all', label: `全部 (${total})` },
              { key: 'chapters', label: `章节 (${chapters.length})`, show: hasChapters },
              { key: 'entities', label: `实体 (${entities.length})`, show: hasEntities },
            ].filter(g => g.show !== false).map(g => (
              <button
                key={g.key}
                onClick={() => setActiveGroup(g.key)}
                className={`text-[10px] px-2 py-1 rounded transition-colors ${
                  activeGroup === g.key
                    ? 'bg-sky-900/40 text-sky-300'
                    : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {!results && !loading && (
          <div className="flex flex-col items-center justify-center h-48 text-zinc-600 gap-2">
            <Icon name="search" size={24} className="text-zinc-700" />
            <p className="text-xs">输入关键词搜索</p>
            <p className="text-[10px] text-zinc-700">支持搜索章节内容、角色名、地点等</p>
          </div>
        )}

        {loading && !results && (
          <div className="flex items-center justify-center h-32 text-zinc-600 text-xs">
            搜索中...
          </div>
        )}

        {results && total === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-zinc-600 gap-2">
            <Icon name="search" size={24} className="text-zinc-700" />
            <p className="text-xs">未找到 &quot;{query}&quot; 相关的结果</p>
          </div>
        )}

        {(activeGroup === 'all' || activeGroup === 'chapters') && hasChapters && (
          <div>
            {activeGroup === 'all' && <GroupHeader icon="file-text" label="章节" count={chapters.length} />}
            {chapters.map((ch, i) => (
              <button
                key={ch.id || ch.chapter_id || i}
                onClick={() => handleChapterClick(ch)}
                className="w-full text-left px-4 py-2.5 hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/50"
              >
                <div className="flex items-center gap-2">
                  <Icon name="file-text" size={12} className="text-zinc-600 shrink-0" />
                  <span className="text-xs font-medium text-zinc-300 truncate">
                    {ch.title || ch.chapter_title || '无标题'}
                  </span>
                </div>
                {ch.snippet && (
                  <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-2 ml-5"
                     dangerouslySetInnerHTML={{ __html: ch.snippet }} />
                )}
              </button>
            ))}
          </div>
        )}

        {(activeGroup === 'all' || activeGroup === 'entities') && hasEntities && (
          <div>
            {activeGroup === 'all' && <GroupHeader icon="users" label="实体" count={entities.length} />}
            {entities.map((ent, i) => (
              <button
                key={ent.id || ent.entity_id || i}
                onClick={() => handleEntityClick(ent)}
                className="w-full text-left px-4 py-2.5 hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/50"
              >
                <div className="flex items-center gap-2">
                  <EntityIcon type={ent.type || ent.entity_type} />
                  <span className="text-xs font-medium text-zinc-300 truncate">
                    {ent.name || ent.entity_name || '未命名'}
                  </span>
                  {ent.type && (
                    <span className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">
                      {ent.type}
                    </span>
                  )}
                </div>
                {ent.snippet && (
                  <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-1 ml-5"
                     dangerouslySetInnerHTML={{ __html: ent.snippet }} />
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Status bar */}
      {results && total > 0 && (
        <div className="px-4 py-1.5 border-t border-zinc-800 text-[10px] text-zinc-600">
          共 {total} 条结果
        </div>
      )}
    </div>
  )
}

function GroupHeader({ icon, label, count }) {
  return (
    <div className="px-4 py-2 bg-zinc-900/60 border-b border-zinc-800 flex items-center gap-2">
      <Icon name={icon} size={12} className="text-zinc-500" />
      <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className="text-[10px] text-zinc-600">({count})</span>
    </div>
  )
}

function EntityIcon({ type }) {
  const map = {
    character: { icon: 'user', color: 'text-violet-400' },
    location: { icon: 'map-pin', color: 'text-emerald-400' },
    item: { icon: 'box', color: 'text-amber-400' },
    organization: { icon: 'users', color: 'text-blue-400' },
    concept: { icon: 'lightbulb', color: 'text-yellow-400' },
    event: { icon: 'calendar', color: 'text-red-400' },
  }
  const cfg = map[type] || { icon: 'circle', color: 'text-zinc-500' }
  return <Icon name={cfg.icon} size={12} className={`${cfg.color} shrink-0`} />
}
