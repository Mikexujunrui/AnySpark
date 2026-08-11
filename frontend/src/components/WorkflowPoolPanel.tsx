// WorkflowPoolPanel — 书架工作流池（V4 适配版：/api/workflows 列表）
import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import { showToast } from './ui/toast-utils'

interface WfSummary { id: string; name: string; description?: string; created_at?: string }

export default function WorkflowPoolPanel() {
  const [workflows, setWorkflows] = useState<WfSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [pendingDelete, setPendingDelete] = useState<WfSummary | null>(null)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const res = await fetch('/api/workflows')
      const d = await res.json()
      setWorkflows(Array.isArray(d) ? d : [])
    } catch { showToast('加载工作流失败', 'error') }
    setLoading(false)
  }

  function handleDelete(id: string, name: string) {
    setPendingDelete({ id, name })
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    const { id, name } = pendingDelete
    setPendingDelete(null)
    try {
      await fetch(`/api/workflows/${id}`, { method: 'DELETE', headers: { 'X-Confirm-Delete': 'true' } })
      setWorkflows(prev => prev.filter(w => w.id !== id))
      showToast(`已删除「${name}」`, 'success')
    } catch { showToast('删除失败', 'error') }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-12 text-zinc-500 text-sm gap-2">
      <div className="w-5 h-5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
      加载工作流...
    </div>
  }

  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2">
          <Icon name="settings" size={14} /> 工作流池
        </h3>
        <span className="text-[11px] text-zinc-500">{workflows.length} 个</span>
      </div>
      {workflows.length === 0 ? (
        <div className="text-center py-10">
          <Icon name="settings" size={28} className="text-zinc-700 mx-auto mb-2" />
          <p className="text-sm text-zinc-600">暂无工作流——进入书籍 → 「工作流」面板创建或 AI 生成</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {workflows.map(w => (
            <div key={w.id} className="p-4 bg-zinc-900/60 rounded-xl border border-zinc-800 hover:border-zinc-700 transition-colors group">
              <div className="flex items-start justify-between">
                <h4 className="text-sm text-zinc-200 font-medium truncate flex-1">{w.name}</h4>
                <button
                  onClick={() => handleDelete(w.id, w.name)}
                  className="p-1 text-zinc-600 hover:text-red-400 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  title="删除"
                >
                  <Icon name="trash" size={12} />
                </button>
              </div>
              {w.description && <p className="text-xs text-zinc-500 mt-1 truncate">{w.description}</p>}
              {w.created_at && (
                <p className="text-[10px] text-zinc-600 mt-2">{new Date(w.created_at).toLocaleDateString()}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <ConfirmModal
        open={!!pendingDelete}
        title="删除工作流"
        message={`确定删除工作流「${pendingDelete?.name || ''}」？此操作不可恢复。`}
        confirmText="删除"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
