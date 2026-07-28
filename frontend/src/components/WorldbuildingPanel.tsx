import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import LoadingState from './ui/Skeleton'
import EmptyState from './ui/EmptyState'
import { useRefreshKey } from '../store'

function renderContent(text, onRefClick) {
  if (!text) return null
  const parts = text.split(/(@[\u4e00-\u9fff\w·]+)/g)
  return parts.map((p, i) =>
    p.startsWith('@') ? (
      <span key={i} onClick={() => onRefClick?.(p.slice(1))}
        className="text-cyan-400 cursor-pointer hover:underline">{p}</span>
    ) : <span key={i}>{p}</span>
  )
}

function CategoryTree({ categories, selectedId, onSelect, depth = 0 }) {
  const [expanded, setExpanded] = useState({})
  return (
    <div className={depth > 0 ? 'pl-3 border-l border-zinc-800/50' : ''}>
      {categories.map(cat => {
        const hasChildren = cat.children?.length > 0
        const isExp = expanded[cat.id] !== false
        const entryCount = (cat.entries?.length || 0)
        return (
          <div key={cat.id}>
            <button
              onClick={() => onSelect(cat.id)}
              className={`w-full text-left px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-colors ${
                selectedId === cat.id ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
              }`}
            >
              {hasChildren && (
                <span onClick={(e) => { e.stopPropagation(); setExpanded(p => ({...p, [cat.id]: !isExp})) }}
                  className="text-[10px] text-zinc-600 w-3">{isExp ? '▾' : '▸'}</span>
              )}
              {!hasChildren && <span className="w-3" />}
              <span>{cat.icon || '📁'}</span>
              <span className="truncate flex-1">{cat.name}</span>
              {entryCount > 0 && <span className="text-[10px] text-zinc-600">{entryCount}</span>}
            </button>
            {hasChildren && isExp && (
              <CategoryTree categories={cat.children} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function WorldbuildingPanel({ bookId }) {
  const refreshKey = useRefreshKey()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedCat, setSelectedCat] = useState(null)
  const [editingEntry, setEditingEntry] = useState(null)
  const [editDraft, setEditDraft] = useState({})
  const [addingEntry, setAddingEntry] = useState(false)
  const [newEntry, setNewEntry] = useState({ title: '', content: '', tags: '' })
  const [addingCat, setAddingCat] = useState(false)
  const [newCatName, setNewCatName] = useState('')
  const [deleteEntryId, setDeleteEntryId] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => { loadData() }, [bookId, refreshKey])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/worldbuilding`)
      const d = await res.json()
      setData(d)
      if (!selectedCat && d.categories?.length > 0) setSelectedCat(d.categories[0].id)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  function findCat(cats, id) {
    for (const c of cats) {
      if (c.id === id) return c
      const found = findCat(c.children || [], id)
      if (found) return found
    }
    return null
  }

  function handleRefClick(name) {
    const cats = data?.categories || []
    function search(list) {
      for (const cat of list) {
        const found = cat.entries?.find(e => e.title === name)
        if (found) { setSelectedCat(cat.id); return }
        search(cat.children || [])
      }
    }
    search(cats)
  }

  async function handleSaveEntry() {
    await fetch(`/api/books/${bookId}/worldbuilding/entries/${editingEntry}`, {
      method: 'PUT', headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify(editDraft),
    })
    setEditingEntry(null)
    loadData()
  }

  async function handleAddEntry() {
    if (!newEntry.title || !selectedCat) return
    await fetch(`/api/books/${bookId}/worldbuilding/entries`, {
      method: 'POST', headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify({
        category_id: selectedCat,
        title: newEntry.title,
        content: newEntry.content,
        tags: newEntry.tags ? newEntry.tags.split(/[,，\s]+/).filter(Boolean) : [],
      }),
    })
    setAddingEntry(false)
    setNewEntry({ title: '', content: '', tags: '' })
    loadData()
  }

  async function handleDeleteEntry(eid) {
    setDeleteEntryId(eid)
  }

  async function confirmDeleteEntry() {
    await fetch(`/api/books/${bookId}/worldbuilding/entries/${deleteEntryId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    setDeleteEntryId(null)
    loadData()
  }

  async function handleAddCategory() {
    if (!newCatName) return
    await fetch(`/api/books/${bookId}/worldbuilding/categories`, {
      method: 'POST', headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newCatName, icon: '📁', parent_id: null }),
    })
    setAddingCat(false)
    setNewCatName('')
    loadData()
  }

  if (loading) return <LoadingState text="加载世界观..." />

  const categories = data?.categories || []
  if (categories.length === 0) {
    return <EmptyState icon="globe" title="尚未生成世界观设定" description="在对话中输入 /worldbuilding 或直接告诉 AI「帮我生成世界观设定」来自动创建" />
  }

  const currentCat: any = selectedCat ? findCat(categories, selectedCat) : null
  const entries: any[] = currentCat?.entries || []

  return (
    <div className="h-full flex">
      {/* Left sidebar: category tree */}
      <div className="w-52 border-r border-zinc-800 bg-zinc-950/50 flex flex-col shrink-0">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1"><Icon name="globe" size={12} /> 世界观</span>
          <button onClick={() => setAddingCat(true)}
            className="text-xs text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-0.5">+</button>
        </div>
        {addingCat && (
          <div className="p-2 border-b border-zinc-800 flex gap-1">
            <input value={newCatName} onChange={e => setNewCatName(e.target.value)}
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none" placeholder="分类名" />
            <button onClick={handleAddCategory} className="text-xs bg-zinc-200 text-zinc-900 rounded px-2 py-1">✓</button>
            <button onClick={() => setAddingCat(false)} className="text-xs text-zinc-500 px-1"><Icon name="x" size={12} /></button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-2">
          <CategoryTree categories={categories} selectedId={selectedCat} onSelect={setSelectedCat} />
        </div>
      </div>

      {/* Main area: entries */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 space-y-2 shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-200">
              {currentCat?.icon || '📁'} {currentCat?.name || '选择分类'}
            </h3>
            <div className="flex gap-2">
              <span className="text-xs text-zinc-600">{entries.length} 个条目</span>
              {currentCat && (
                <button onClick={() => { setAddingEntry(true); setNewEntry({ title: '', content: '', tags: '' }) }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 rounded px-2 py-0.5">+ 新条目</button>
              )}
            </div>
          </div>
          {entries.length > 0 && (
            <div className="relative">
              <Icon name="search" size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索条目标题或内容..."
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-8 pr-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
              />
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {addingEntry && (
            <div className="bg-zinc-800/60 border border-zinc-700 rounded-xl p-4 space-y-2">
              <input value={newEntry.title} onChange={e => setNewEntry(d => ({...d, title: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:outline-none" placeholder="条目标题" />
              <textarea value={newEntry.content} onChange={e => setNewEntry(d => ({...d, content: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-300 focus:outline-none resize-none" rows={4}
                placeholder="条目描述（可用 @条目名 交叉引用）" />
              <input value={newEntry.tags} onChange={e => setNewEntry(d => ({...d, tags: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-400 focus:outline-none" placeholder="标签（逗号分隔）" />
              <div className="flex gap-2 justify-end">
                <button onClick={() => setAddingEntry(false)} className="text-xs text-zinc-500 px-3 py-1">取消</button>
                <button onClick={handleAddEntry} className="text-xs bg-zinc-200 text-zinc-900 rounded px-3 py-1 font-medium">添加</button>
              </div>
            </div>
          )}

          {(() => {
            const filteredEntries: any[] = searchQuery
              ? entries.filter(entry =>
                  entry.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                  (entry.content || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
                  (entry.tags || []).some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()))
                )
              : entries;

            if (filteredEntries.length === 0 && searchQuery) {
              return (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
                  <Icon name="search" size={24} className="text-zinc-700 mb-2" />
                  <p className="text-sm">未找到匹配的条目</p>
                  <button onClick={() => setSearchQuery('')} className="text-xs text-blue-400 hover:text-blue-300 mt-2">
                    清除搜索
                  </button>
                </div>
              );
            }

            return filteredEntries.map((entry: any) => (
              <div key={entry.id} className="bg-zinc-800/30 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors">
                {editingEntry === entry.id ? (
                  <div className="space-y-2">
                    <input value={(editDraft as any).title ?? (entry as any).title}
                      onChange={e => setEditDraft(d => ({...d, title: e.target.value}))}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:outline-none" />
                    <textarea value={(editDraft as any).content ?? (entry as any).content}
                      onChange={e => setEditDraft(d => ({...d, content: e.target.value}))}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-300 focus:outline-none resize-none" rows={4} />
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setEditingEntry(null)} className="text-xs text-zinc-500 px-3 py-1">取消</button>
                      <button onClick={handleSaveEntry} className="text-xs bg-zinc-200 text-zinc-900 rounded px-3 py-1 font-medium">保存</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <h4 className="text-sm font-semibold text-zinc-200">{entry.title}</h4>
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => { setEditingEntry(entry.id); setEditDraft({}) }}
                          className="text-[10px] text-zinc-600 hover:text-zinc-300">编辑</button>
                        <button onClick={() => handleDeleteEntry(entry.id)}
                          className="text-[10px] text-zinc-700 hover:text-red-400">删除</button>
                      </div>
                    </div>
                    <p className="text-sm text-zinc-400 leading-relaxed whitespace-pre-wrap">
                      {renderContent(entry.content, handleRefClick)}
                    </p>
                    {entry.tags?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-3">
                        {entry.tags.map((t, i) => (
                          <span key={i} className="text-[10px] bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded">{t}</span>
                        ))}
                      </div>
                    )}
                    {entry.chapter_refs?.length > 0 && (
                      <p className="text-[10px] text-zinc-600 mt-2 flex items-center gap-1"><Icon name="book-open" size={10} /> {entry.chapter_refs.join(', ')}</p>
                    )}
                  </>
                )}
              </div>
            ));
          })()}

          {entries.length === 0 && !addingEntry && !searchQuery && (
            <div className="text-center text-zinc-600 text-sm py-12">
              此分类下暂无条目
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!deleteEntryId}
        title="删除条目"
        message="确定删除此世界观条目？"
        danger
        onConfirm={confirmDeleteEntry}
        onCancel={() => setDeleteEntryId(null)}
      />
    </div>
  )
}
