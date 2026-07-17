import { useState, useEffect } from 'react'
import { api } from '../api'
import Modal from './ui/Modal'
import ConfirmModal from './ui/ConfirmModal'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'

const STEP_ICONS = {
  extract: 'search', write: 'pen-tool', validate: 'search', edit: 'edit',
  plan: 'globe', review: 'clipboard-list',
}

export default function WorkflowPoolPanel() {
  const [workflows, setWorkflows] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedWf, setSelectedWf] = useState(null)
  const [deleteWfId, setDeleteWfId] = useState(null)

  useEffect(() => { loadWorkflows() }, [])

  async function loadWorkflows() {
    setLoading(true)
    try {
      const data = await api.getGlobalWorkflows()
      setWorkflows(Array.isArray(data) ? data : [])
    } catch {
      showToast('加载工作流失败', 'error')
    }
    setLoading(false)
  }

  async function handleDelete() {
    if (!deleteWfId) return
    try {
      await api.deleteGlobalWorkflow(deleteWfId)
      setDeleteWfId(null)
      if (selectedWf?.id === deleteWfId) setSelectedWf(null)
      loadWorkflows()
      showToast('已删除', 'success')
    } catch (e) {
      console.error('Delete workflow failed:', e)
      showToast('删除失败: ' + (e?.message || '未知错误'), 'error')
    }
  }

  const formatTime = (iso) => {
    if (!iso) return ''
    return iso.slice(0, 16).replace('T', ' ')
  }

  if (loading) return <LoadingState text="加载工作流..." />

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Icon name="settings" size={28} className="text-sky-400" /> 工作流池
          </h1>
          <p className="text-zinc-500 mt-1 text-sm">全局共享的自动化工作流，在项目中订阅后即可使用</p>
        </div>
        {workflows.length > 0 && (
          <span className="text-xs text-zinc-500 bg-zinc-800 px-3 py-1.5 rounded-lg">
            {workflows.length} 个工作流
          </span>
        )}
      </header>

      {workflows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-zinc-600">
          <Icon name="settings" size={48} className="mb-4 text-zinc-700" />
          <p className="text-lg mb-2">工作流池为空</p>
          <p className="text-sm mb-6 text-center leading-relaxed">
            在项目对话中用自然语言描述你的工作流需求<br />
            AI 会自动生成并保存到全局池
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map(wf => (
            <div
              key={wf.id}
              onClick={() => setSelectedWf(wf)}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 hover:border-sky-800 cursor-pointer transition-all group hover:shadow-md"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center shrink-0">
                    <Icon name="settings" size={16} className="text-sky-400" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-zinc-200 font-semibold text-sm leading-snug truncate">{wf.name}</h3>
                    <p className="text-zinc-500 text-[10px] truncate">
                      {wf.steps?.length || 0} 步 · {formatTime(wf.createdAt)}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteWfId(wf.id) }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 text-xs transition-all ml-1 shrink-0"
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {(wf.steps || []).slice(0, 5).map((step, i) => (
                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 flex items-center gap-1">
                    <Icon name={STEP_ICONS[step.type] || 'list'} size={10} />
                    {step.label || step.type}
                  </span>
                ))}
                {wf.steps?.length > 5 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-600">+{wf.steps.length - 5}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedWf && (
        <Modal open onClose={() => setSelectedWf(null)} title={selectedWf.name} size="xl">
          <div className="p-6 max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center">
                  <Icon name="settings" size={20} className="text-sky-400" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-zinc-100">{selectedWf.name}</h2>
                  <p className="text-xs text-zinc-500">
                    {selectedWf.steps?.length || 0} 个步骤 · 创建于 {formatTime(selectedWf.createdAt)}
                  </p>
                </div>
              </div>
              <button onClick={() => setSelectedWf(null)}
                className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800" aria-label="关闭">
                <Icon name="x" size={16} />
              </button>
            </div>

            {/* Steps pipeline */}
            <div className="space-y-2 mb-4">
              {(selectedWf.steps || []).map((step, i) => (
                <div key={step.id || i}>
                  <div className="flex items-center gap-3 border border-zinc-700 bg-zinc-800/30 rounded-xl px-4 py-3">
                    <Icon name={STEP_ICONS[step.type] || 'list'} size={18} className="text-zinc-400" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-zinc-200 truncate">{step.label || step.type}</p>
                      <p className="text-[10px] text-zinc-500 truncate">
                        {step.type}
                        {step.config?.instruction && ` · ${step.config.instruction.slice(0, 80)}...`}
                      </p>
                    </div>
                    <span className="text-zinc-600 text-xs font-mono shrink-0">{i + 1}</span>
                  </div>
                  {i < selectedWf.steps.length - 1 && (
                    <div className="flex justify-center py-1">
                      <div className="w-0.5 h-4 bg-zinc-800" />
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
              <p className="text-[10px] text-zinc-600 font-mono">ID: {selectedWf.id}</p>
              <button
                onClick={() => setDeleteWfId(selectedWf.id)}
                className="text-xs text-red-400 hover:text-red-300 bg-red-950/40 border border-red-900 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5"
              >
                <Icon name="trash" size={12} /> 删除工作流
              </button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteWfId}
        title="删除工作流"
        message="确定从全局池删除此工作流？所有已订阅的此工作流的项目都将无法使用它。此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteWfId(null)}
      />
    </div>
  )
}
