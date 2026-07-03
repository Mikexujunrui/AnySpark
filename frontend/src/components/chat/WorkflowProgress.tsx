import { useState, useEffect } from 'react'
import Icon from '../ui/Icon'

const STEP_ICONS = {
  extract: 'search', write: 'pen-tool', validate: 'search', edit: 'edit',
  plan: 'globe', review: 'clipboard-list',
  read: 'book-open', decompose: 'list', annotate: 'tag', rewrite: 'refresh-cw',
  ask_user: 'help-circle', search: 'search', compare_plot: 'git-compare',
  diff: 'file-text', generate_outline: 'map',
}
const STEP_COLORS = {
  pending: 'border-zinc-700 bg-zinc-800/30 text-zinc-500',
  running: 'border-sky-700 bg-sky-950/30 text-sky-400',
  completed: 'border-emerald-700 bg-emerald-950/30 text-emerald-400',
  failed: 'border-red-700 bg-red-950/30 text-red-400',
}

export default function WorkflowProgress({ data }) {
  const [workflow, setWorkflow] = useState(null)

  useEffect(() => {
    if (!data) return

    if (data.action === 'generated' || data.action === 'executing') {
      // Initialize workflow with all steps as pending
      setWorkflow({
        name: data.name,
        id: data.id,
        steps: data.steps.map(s => ({ ...s, status: 'pending' })),
        completed: 0,
        total: data.steps.length,
        done: false,
      })
    } else if (data.action === 'step_start') {
      setWorkflow(prev => {
        if (!prev) return prev
        const steps = [...prev.steps]
        if (data.index >= 0 && data.index < steps.length) {
          steps[data.index] = { ...steps[data.index], status: 'running' }
        }
        return { ...prev, steps }
      })
    } else if (data.action === 'step_done') {
      setWorkflow(prev => {
        if (!prev) return prev
        const steps = [...prev.steps]
        const idx = data.index >= 0 ? data.index : steps.findIndex(s => s.status === 'running')
        if (idx >= 0 && idx < steps.length) {
          steps[idx] = { ...steps[idx], status: 'completed' }
        }
        return { ...prev, steps, completed: prev.completed + 1 }
      })
    } else if (data.action === 'step_error') {
      setWorkflow(prev => {
        if (!prev) return prev
        const steps = [...prev.steps]
        const idx = data.index >= 0 ? data.index : steps.findIndex(s => s.status === 'running')
        if (idx >= 0 && idx < steps.length) {
          steps[idx] = { ...steps[idx], status: 'failed', error: data.error }
        }
        return { ...prev, steps, completed: prev.completed + 1 }
      })
    } else if (data.action === 'done') {
      setWorkflow(prev => prev ? { ...prev, done: true, completed: data.completed, total: data.total } : prev)
    }
  }, [data])

  if (!workflow) return null

  const allPending = workflow.steps.every(s => s.status === 'pending')
  const isGenerating = allPending && !workflow.done

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-3 my-2">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon name="settings" size={14} />
          <span className="text-xs font-semibold text-zinc-300 truncate">
            {workflow.name || '工作流'}
          </span>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          workflow.done
            ? 'bg-emerald-900/50 text-emerald-400'
            : isGenerating
            ? 'bg-amber-900/50 text-amber-400'
            : 'bg-sky-900/50 text-sky-400'
        }`}>
          {workflow.done
            ? `完成 ${workflow.completed}/${workflow.total}`
            : isGenerating
            ? '已生成'
            : `执行中 ${workflow.completed}/${workflow.total}`}
        </span>
      </div>

      {/* Steps */}
      <div className="space-y-1">
        {workflow.steps.map((step, i) => {
          const status = step.status || 'pending'
          return (
            <div key={i}
              className={`flex items-center gap-2 border rounded-lg px-2.5 py-1.5 text-xs transition-colors ${STEP_COLORS[status]}`}>
              <Icon name={STEP_ICONS[step.type] || 'list'} size={12} />
              <span className="flex-1 truncate">{step.label}</span>
              <span className={`shrink-0 ${
                status === 'completed' ? 'text-emerald-400' :
                status === 'running' ? 'text-sky-400 animate-pulse' :
                status === 'failed' ? 'text-red-400' : 'text-zinc-600'
              }`}>
                {status === 'completed' ? '✓' : status === 'running' ? '⋯' : status === 'failed' ? '✗' : '○'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
