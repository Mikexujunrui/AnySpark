import { useState, useRef, useEffect, useCallback } from 'react'
import { showToast } from './ui/toast-utils'
import Icon from './ui/Icon'
import { openTab } from '../stores/tabStore'
import { triggerRefresh } from '../store'

// V4 适配版 SearchPanel：前端本地搜索
// 章节：GET /api/chapters?book_id=main 全量 → 关键词过滤 title/content（命中片段高亮）
// 实体：GET /api/graph/entities 全量 → 关键词过滤 name/entity_type/description
interface ChapterHit {
  id: string
  title: string
  content?: string
  order_index?: number
  snippet?: string
}
interface EntityHit {
  id: string
  name: string
  entity_type?: string
  description?: string
  snippet?: string
}

// 高亮命中词（简单包裹 <mark>，避免 dangerouslySetInnerHTML 的 XSS 风险用转义）
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function highlight(text: string, needle: string, maxLen = 160): string {
  const lower = text.toLowerCase()
  const q = needle.toLowerCase()
  const idx = lower.indexOf(q)
  if (idx === -1) return escapeHtml(text.slice(0, maxLen))
  const start = Math.max(0, idx - 40)
  const end = Math.min(text.length, idx + q.length + 80)
  const before = start > 0 ? '…' : ''
  const after = end < text.length ? '…' : ''
  const seg = text.slice(start, end)
  const esc = escapeHtml(seg)
  const escQ = escapeHtml(needle)
  // 不区分大小写替换命中段
  const re = new RegExp(escQ.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  const highlighted = esc.replace(re, m => `<mark class="bg-amber-500/30 text-amber-200 rounded px-0.5">${m}</mark>`)
  return before + highlighted + after
}

export default function SearchPanel({ bookId, onClose }: { bookId: string; onClose?: () => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ chapters: ChapterHit[]; entities: EntityHit[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeGroup, setActiveGroup] = useState('all')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const doSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) {
      setResults(null)
      return
    }
    setLoading(true)
    try {
      const [chaptersRes, entitiesRes] = await Promise.all([
        fetch(`/api/chapters?book_id=${encodeURIComponent(bookId)}`),
        fetch(`/api/graph/entities?book_id=${encodeURIComponent(bookId)}`),
      ])
      const chapters: any[] = await chaptersRes.json()
      const entities: any[] = await entitiesRes.json()

      const needle = q.toLowerCase()
      const chapterHits: ChapterHit[] = (Array.isArray(chapters) ? chapters : [])
        .filter(ch => (ch.title || '').toLowerCase().includes(needle) || (ch.content || '').toLowerCase().includes(needle))
        .slice(0, 20)
        .map(ch => {
          const content = ch.content || ''
          const idx = content.toLowerCase().indexOf(needle)
          const snippet = idx === -1
            ? ''
            : content.slice(Math.max(0, idx - 40), idx + q.length + 80)
          return {
            id: ch.id,
            title: ch.title || '无标题',
            content,
            order_index: ch.order_index,
            snippet: snippet ? highlight(snippet, q) : undefined,
          }
        })

      const entityHits: EntityHit[] = (Array.isArray(entities) ? entities : [])
        .filter(ent => {
          const hay = [ent.name, ent.entity_type, ent.description, ...(ent.aliases || [])].filter(Boolean).join(' ').toLowerCase()
          return hay.includes(needle)
        })
        .slice(0, 20)
        .map(ent => {
          const desc = ent.description || ''
          const idx = desc.toLowerCase().indexOf(needle)
          const snippet = idx === -1
            ? ''
            : desc.slice(Math.max(0, idx - 40), idx + q.length + 80)
          return {
            id: ent.id,
            name: ent.name || '未命名',
            entity_type: ent.entity_type,
            description: desc,
            snippet: snippet ? highlight(snippet, q) : undefined,
          }
        })

      setResults({ chapters: chapterHits, entities: entityHits })

      if (chapterHits.length === 0 && entityHits.length === 0) {
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

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      onClose?.()
    }
    if (e.key === 'Enter') {
      doSearch()
    }
  }

  function handleChapterClick(ch: ChapterHit) {
    openTab(ch.id, ch.title, bookId)
    onClose?.()
  }

  function handleEntityClick(entity: EntityHit) {
    // 实体点击：切到知识库面板由用户细看（本面板仅搜索展示）
    triggerRefresh()
    onClose?.()
  }

  const chapters = results?.chapters || []
  const entities = results?.entities || []
  const hasChapters = chapters.length > 0
  const hasEntities = entities.length > 0
  const total = chapters.length + entities.length

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
            <p className="text-[10px] text-zinc-700">支持搜索章节内容、角色名、地点等（本地检索）</p>
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
                key={ch.id || i}
                onClick={() => handleChapterClick(ch)}
                className="w-full text-left px-4 py-2.5 hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/50"
              >
                <div className="flex items-center gap-2">
                  <Icon name="file-text" size={12} className="text-zinc-600 shrink-0" />
                  <span className="text-xs font-medium text-zinc-300 truncate">
                    {ch.title}
                  </span>
                  {ch.order_index != null && (
                    <span className="text-[10px] text-zinc-600 shrink-0">第 {ch.order_index + 1} 章</span>
                  )}
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
                key={ent.id || i}
                onClick={() => handleEntityClick(ent)}
                className="w-full text-left px-4 py-2.5 hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/50"
              >
                <div className="flex items-center gap-2">
                  <EntityIcon type={ent.entity_type} />
                  <span className="text-xs font-medium text-zinc-300 truncate">
                    {ent.name}
                  </span>
                  {ent.entity_type && (
                    <span className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">
                      {ent.entity_type}
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

function GroupHeader({ icon, label, count }: { icon: string; label: string; count: number }) {
  return (
    <div className="px-4 py-2 bg-zinc-900/60 border-b border-zinc-800 flex items-center gap-2">
      <Icon name={icon} size={12} className="text-zinc-500" />
      <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className="text-[10px] text-zinc-600">({count})</span>
    </div>
  )
}

function EntityIcon({ type }: { type?: string }) {
  const map: Record<string, { icon: string; color: string }> = {
    character: { icon: 'user', color: 'text-violet-400' },
    location: { icon: 'map-pin', color: 'text-emerald-400' },
    item: { icon: 'box', color: 'text-amber-400' },
    organization: { icon: 'users', color: 'text-blue-400' },
    concept: { icon: 'lightbulb', color: 'text-yellow-400' },
    event: { icon: 'calendar', color: 'text-red-400' },
  }
  const key = (type || '').toLowerCase()
  const cfg = map[key] || { icon: 'circle', color: 'text-zinc-500' }
  return <Icon name={cfg.icon} size={12} className={`${cfg.color} shrink-0`} />
}
