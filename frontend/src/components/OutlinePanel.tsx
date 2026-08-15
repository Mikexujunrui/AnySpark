// OutlinePanel — V4 适配版（大纲 ≈ 章节计划 /api/plan）
// 壳原版绑定对端 outline/detailed-outline/continuity/flavor 6 视图（全部对端专属端点），
// 重写为 V4 计划列表（chapter_order/title/content/status）+ 增删改。
import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import EmptyState from './ui/EmptyState'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'
import ConfirmModal from './ui/ConfirmModal'
import { useRefreshKey } from "../store"

interface PlanItem {
  id: string
  chapter_order: number
  title: string
  content: string
  status: string
  created_at?: string
}

const STATUS_LABELS: Record<string, string> = {
  planned: '计划中',
  writing: '写作中',
  done: '已完成',
}
const STATUS_COLORS: Record<string, string> = {
  planned: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  writing: 'bg-sky-900/40 text-sky-300 border-sky-800/50',
  done: 'bg-emerald-900/40 text-emerald-300 border-emerald-800/50',
}

export default function OutlinePanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [plans, setPlans] = useState<PlanItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newOrder, setNewOrder] = useState(1)
  const [newTitle, setNewTitle] = useState('')
  const [newContent, setNewContent] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editStatus, setEditStatus] = useState('planned')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  async function loadPlans() {
    setLoading(true)
    try {
      const res = await fetch(`/api/plan?book_id=${bookId}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPlans(Array.isArray(data) ? data : [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => { loadPlans() }, [bookId, refreshKey])

  async function handleAdd() {
    if (!newTitle.trim()) { showToast('请输入章节标题', 'error'); return }
    try {
      const res = await fetch('/api/plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chapter_order: newOrder, title: newTitle.trim(), content: newContent.trim() }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      showToast('计划已添加', 'success')
      setShowAdd(false); setNewTitle(''); setNewContent('')
      loadPlans()
    } catch (e) { showToast('添加失败', 'error') }
  }

  async function handleSave(id: string) {
    try {
      const res = await fetch(`/api/plan/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle, content: editContent, status: editStatus }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      showToast('已保存', 'success')
      setEditingId(null)
      loadPlans()
    } catch (e) { showToast('保存失败', 'error') }
  }

  async function handleDelete(id: string) {
    setPendingDelete(id)
  }

  async function handleDeleteConfirm() {
    if (!pendingDelete) return
    try {
      await fetch(`/api/plan/${pendingDelete}`, { method: 'DELETE', headers: { 'X-Confirm-Delete': 'true' } })
      showToast('已删除', 'success')
      loadPlans()
    } catch (e) { showToast('删除失败', 'error') }
    setPendingDelete(null)
  }

  const sorted = [...plans].sort((a, b) => (a.chapter_order ?? 0) - (b.chapter_order ?? 0))

  if (loading) return <LoadingState text="加载大纲..." />

  if (sorted.length === 0) {
    return <EmptyState
      icon="list"
      title="暂无章节计划"
      description="在对话中让 AI 帮你规划章节，或点击右上角手动添加计划"
      action={() => setShowAdd(true)}
      actionLabel="添加计划"
    />
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="px-4 py-2.5 border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-sm shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon name="clipboard-list" size={16} className="text-zinc-400" />
          <span className="text-sm font-medium text-zinc-300">大纲</span>
          <span className="text-[11px] text-zinc-600">{sorted.length} 条计划</span>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 text-[11px] bg-sky-700/60 hover:bg-sky-600/60 text-sky-200 rounded-lg px-2.5 py-1 transition-colors"
        >
          <Icon name="plus" size={11} /> 添加计划
        </button>
      </div>

      {/* 新增表单 */}
      {showAdd && (
        <div className="px-4 py-3 border-b border-zinc-800/60 bg-zinc-900/40 space-y-2">
          <div className="flex items-center gap-2">
            <input
              type="number" min={1}
              value={newOrder}
              onChange={e => setNewOrder(parseInt(e.target.value) || 1)}
              className="w-16 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none"
              placeholder="章序"
            />
            <input
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none"
              placeholder="章节标题"
            />
          </div>
          <textarea
            value={newContent}
            onChange={e => setNewContent(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none resize-none"
            rows={3}
            placeholder="章节计划内容（要写什么、推进什么）..."
          />
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowAdd(false); setNewTitle(''); setNewContent('') }}
              className="text-[11px] text-zinc-500 hover:text-zinc-300 px-2.5 py-1">取消</button>
            <button onClick={handleAdd}
              className="text-[11px] bg-sky-600 hover:bg-sky-500 text-white rounded-lg px-3 py-1 font-medium transition-colors">添加</button>
          </div>
        </div>
      )}

      {/* 计划列表 */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-3 space-y-1 py-4">
          {sorted.map(p => {
            const isEditing = editingId === p.id
            return (
              <div key={p.id} className={`rounded-xl transition-all ${
                isEditing
                  ? 'bg-zinc-900/60 border border-sky-700/40 ring-1 ring-sky-600/20'
                  : 'bg-zinc-900/30 border border-zinc-800/50 hover:border-zinc-700/50'
              }`}>
                <div className="px-3.5 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[10px] font-mono text-zinc-600 bg-zinc-800/70 px-1.5 py-0.5 rounded">#{p.chapter_order}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_COLORS[p.status] || STATUS_COLORS.planned}`}>
                          {STATUS_LABELS[p.status] || p.status}
                        </span>
                        {isEditing ? (
                          <input
                            value={editTitle}
                            onChange={e => setEditTitle(e.target.value)}
                            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-xs text-zinc-200 focus:outline-none"
                            placeholder="章节标题"
                          />
                        ) : (
                          <span className="text-xs font-semibold text-zinc-200 truncate">{p.title || '无标题'}</span>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="space-y-2 mt-2">
                          <select
                            value={editStatus}
                            onChange={e => setEditStatus(e.target.value)}
                            className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-[11px] text-zinc-300 focus:outline-none"
                          >
                            <option value="planned">计划中</option>
                            <option value="writing">写作中</option>
                            <option value="done">已完成</option>
                          </select>
                          <textarea
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-600/50 resize-none transition-colors"
                            rows={3}
                            placeholder="计划内容..."
                          />
                          <div className="flex gap-2 justify-end">
                            <button onClick={() => setEditingId(null)}
                              className="text-[11px] text-zinc-500 hover:text-zinc-300 px-2.5 py-1">取消</button>
                            <button onClick={() => handleSave(p.id)}
                              className="text-[11px] bg-sky-600 hover:bg-sky-500 text-white rounded-lg px-3 py-1 font-medium transition-colors">保存</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          {p.content && <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap">{p.content}</p>}
                          {p.created_at && (
                            <p className="text-[10px] text-zinc-600 mt-1.5">{new Date(p.created_at).toLocaleDateString()}</p>
                          )}
                        </>
                      )}
                    </div>

                    {!isEditing && (
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => { setEditingId(p.id); setEditTitle(p.title); setEditContent(p.content); setEditStatus(p.status || 'planned') }}
                          className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-300 bg-zinc-800/60 hover:bg-zinc-700/60 rounded-lg px-2 py-1 transition-colors"
                        >
                          <Icon name="pen" size={10} /> 编辑
                        </button>
                        <button
                          onClick={() => handleDelete(p.id)}
                          className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-red-400 bg-zinc-800/60 hover:bg-zinc-700/60 rounded-lg px-2 py-1 transition-colors"
                        >
                          <Icon name="trash-2" size={10} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 删除确认 */}
      <ConfirmModal
        open={!!pendingDelete}
        title="删除章节计划"
        message="确定删除这条章节计划？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDeleteConfirm}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
