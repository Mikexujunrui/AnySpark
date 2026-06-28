import Icon from '../ui/Icon.jsx'

export default function TaskListPanel({ items }) {
  if (!items || items.length === 0) return null

  const statusIcon = (status) => {
    switch (status) {
      case 'done': return <Icon name="check-circle" size={12} className="text-emerald-400" />
      case 'in_progress': return <Icon name="loader" size={12} className="text-blue-400" />
      case 'skipped': return <Icon name="chevron-right" size={12} className="text-zinc-500" />
      case 'failed': return <Icon name="x" size={12} className="text-red-400" />
      default: return <span className="inline-block w-3 h-3 rounded-full border border-zinc-600" />
    }
  }

  const doneCount = items.filter(i => i.status === 'done').length
  const totalCount = items.length

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-300 flex items-center gap-1"><Icon name="clipboard-list" size={12} /> 任务清单</span>
        <span className="ml-auto text-[10px] text-zinc-500">{doneCount}/{totalCount}</span>
      </div>
      <div className="px-4 py-2 space-y-1">
        {items.map((item, i) => (
          <div key={i} className={`flex items-start gap-2 text-xs py-1 ${
            item.status === 'done' ? 'text-zinc-500' : 
            item.status === 'in_progress' ? 'text-blue-300' :
            item.status === 'failed' ? 'text-red-400' : 'text-zinc-400'
          }`}>
            <span className="shrink-0">{statusIcon(item.status)}</span>
            <span className={item.status === 'done' ? 'line-through' : ''}>
              {item.label || `步骤 ${i}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
