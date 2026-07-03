import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import EmptyState from './ui/EmptyState'
import { showToast } from './ui/toast-utils'

interface Inspiration {
  id: string
  content: string
  tags: string[]
  linked_characters: string[]
  linked_chapters: string[]
  linked_foreshadows: string[]
  status: string
  created_at: string
  promoted_to: string
  promoted_at: string
}

export default function InspirationInbox({ bookId }: { bookId: string }) {
  const [inspirations, setInspirations] = useState<Inspiration[]>([])
  const [loading, setLoading] = useState(true)
  const [newContent, setNewContent] = useState('')
  const [newTags, setNewTags] = useState('')
  const [showInput, setShowInput] = useState(false)

  useEffect(() => { loadData() }, [bookId])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/inspirations`)
      if (res.ok) {
        const json = await res.json()
        setInspirations(json.inspirations || [])
      }
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function addInspiration() {
    if (!newContent.trim()) return
    try {
      await fetch(`/api/books/${bookId}/inspirations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newContent.trim(),
          tags: newTags.split(',').map(t => t.trim()).filter(Boolean),
        }),
      })
      setNewContent('')
      setNewTags('')
      setShowInput(false)
      loadData()
    } catch (e) {
      showToast('保存灵感失败', 'error')
    }
  }

  async function archiveInspiration(id: string) {
    await fetch(`/api/books/${bookId}/inspirations/${id}/archive`, { method: 'POST' })
    loadData()
  }

  async function deleteInspiration(id: string) {
    await fetch(`/api/books/${bookId}/inspirations/${id}`, { method: 'DELETE' })
    loadData()
  }

  async function promoteInspiration(id: string, targetType: string) {
    try {
      await fetch(`/api/books/${bookId}/inspirations/${id}/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_type: targetType }),
      })
      showToast('灵感已提升', 'success')
      loadData()
    } catch (e) {
      showToast('提升失败', 'error')
    }
  }

  const inboxItems = inspirations.filter(i => i.status === 'inbox')
  const promotedItems = inspirations.filter(i => i.status === 'promoted')
  const archivedItems = inspirations.filter(i => i.status === 'archived')

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-zinc-600 text-sm">
        <div className="w-5 h-5 border-2 border-zinc-700 border-t-amber-400 rounded-full animate-spin mr-2" /> 加载灵感...
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-zinc-800/60 bg-zinc-950/80 shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon name="lightbulb" size={16} className="text-amber-400" />
          <span className="text-sm font-medium text-zinc-300">灵感碎片</span>
          <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">{inspirations.length}</span>
        </div>
        <button
          onClick={() => setShowInput(!showInput)}
          className="flex items-center gap-1 text-xs bg-amber-600/80 hover:bg-amber-500 text-white rounded-lg px-2.5 py-1 transition-colors"
        >
          <Icon name="plus" size={12} /> 新灵感
        </button>
      </div>

      {/* Quick add input */}
      {showInput && (
        <div className="px-4 py-3 border-b border-zinc-800/60 bg-zinc-900/40 space-y-2">
          <textarea
            value={newContent}
            onChange={e => setNewContent(e.target.value)}
            placeholder="随手记下一个灵感碎片..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-600/50 resize-none"
            rows={2}
            autoFocus
          />
          <div className="flex gap-2 items-center">
            <input
              value={newTags}
              onChange={e => setNewTags(e.target.value)}
              placeholder="标签 (逗号分隔)"
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none"
            />
            <button
              onClick={() => { setShowInput(false); setNewContent(''); setNewTags('') }}
              className="text-[11px] text-zinc-500 hover:text-zinc-300 px-2 py-1.5"
            >取消</button>
            <button
              onClick={addInspiration}
              disabled={!newContent.trim()}
              className="text-[11px] bg-amber-600 hover:bg-amber-500 text-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-40"
            >保存</button>
          </div>
        </div>
      )}

      {/* Three-column kanban */}
      <div className="flex-1 overflow-y-auto p-4">
        {inspirations.length === 0 ? (
          <EmptyState
            icon="lightbulb"
            title="还没有灵感碎片"
            description="灵感转瞬即逝。随手记录，日后关联到角色、章节或伏笔"
          />
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {/* Inbox column */}
            <div>
              <h4 className="text-xs font-semibold text-amber-400 mb-2 flex items-center gap-1.5">
                <Icon name="inbox" size={12} /> 收件箱 ({inboxItems.length})
              </h4>
              <div className="space-y-2">
                {inboxItems.map(insp => (
                  <InspirationCard
                    key={insp.id}
                    insp={insp}
                    onArchive={archiveInspiration}
                    onDelete={deleteInspiration}
                    onPromote={promoteInspiration}
                  />
                ))}
              </div>
            </div>

            {/* Promoted column */}
            <div>
              <h4 className="text-xs font-semibold text-emerald-400 mb-2 flex items-center gap-1.5">
                <Icon name="check-circle" size={12} /> 已提升 ({promotedItems.length})
              </h4>
              <div className="space-y-2">
                {promotedItems.map(insp => (
                  <div key={insp.id}
                    className="bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-3 opacity-75"
                  >
                    <p className="text-xs text-zinc-400 whitespace-pre-wrap">{insp.content}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-[9px] bg-emerald-900/40 text-emerald-400 px-1.5 py-0.5 rounded">
                        → {insp.promoted_to}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Archived column */}
            <div>
              <h4 className="text-xs font-semibold text-zinc-500 mb-2 flex items-center gap-1.5">
                <Icon name="archive" size={12} /> 已归档 ({archivedItems.length})
              </h4>
              <div className="space-y-2">
                {archivedItems.map(insp => (
                  <div key={insp.id}
                    className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-3 opacity-60"
                  >
                    <p className="text-xs text-zinc-500 whitespace-pre-wrap line-through">{insp.content}</p>
                    <button
                      onClick={() => deleteInspiration(insp.id)}
                      className="text-[9px] text-zinc-700 hover:text-red-400 mt-1"
                    >删除</button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function InspirationCard({ insp, onArchive, onDelete, onPromote }: {
  insp: Inspiration
  onArchive: (id: string) => void
  onDelete: (id: string) => void
  onPromote: (id: string, type: string) => void
}) {
  return (
    <div className="bg-amber-950/15 border border-amber-900/30 rounded-lg p-3 hover:border-amber-700/40 transition-colors">
      <p className="text-xs text-zinc-200 whitespace-pre-wrap mb-2">{insp.content}</p>
      {insp.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {insp.tags.map(tag => (
            <span key={tag} className="text-[9px] bg-amber-900/30 text-amber-400/80 px-1.5 py-0.5 rounded-full">{tag}</span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 pt-2 border-t border-amber-900/15">
        <button
          onClick={() => onPromote(insp.id, 'outline_node')}
          className="text-[9px] text-emerald-600 hover:text-emerald-400 transition-colors"
        >提升</button>
        <button
          onClick={() => onArchive(insp.id)}
          className="text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors"
        >归档</button>
        <button
          onClick={() => onDelete(insp.id)}
          className="text-[9px] text-zinc-700 hover:text-red-400 transition-colors ml-auto"
        >删除</button>
      </div>
    </div>
  )
}
