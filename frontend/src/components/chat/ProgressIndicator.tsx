import Icon from '../ui/Icon'

export default function ProgressIndicator({ progress }) {
  if (!progress) return null
  const pct = progress.total ? Math.round(((progress.done || 0) / progress.total) * 100) : null
  const inferredPct = progress.stage?.includes('Step 1') ? 25 : progress.stage?.includes('Step 2') ? 50 : progress.stage?.includes('Step 3') ? 75 : 40

  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center shrink-0 mt-0.5">
        <Icon name="zap" size={13} className="text-sky-400" />
      </div>
      <div className="bg-zinc-800/80 border border-zinc-700 rounded-xl px-4 py-3 min-w-[360px]">
        <div className="flex items-center gap-2 mb-2">
          <Icon name="loader" size={13} className="text-accent animate-spin" />
          <span className="text-sm font-medium text-zinc-100">{progress.stage || '处理中'}</span>
          <span className="ml-auto text-xs text-accent font-medium truncate max-w-[120px]">
            {pct !== null ? `${pct}%` : '运行中'}
          </span>
        </div>
        {progress.detail && <p className="text-xs text-zinc-500 mb-2 truncate">{progress.detail}</p>}
        <div className="h-1.5 bg-zinc-700/60 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-300"
            style={{ width: `${pct ?? inferredPct}%` }}
          />
        </div>
        {progress.total && (
          <div className="flex justify-between text-[10px] text-zinc-500 mt-1.5">
            <span>进度</span>
            <span>{progress.done || 0} / {progress.total}</span>
          </div>
        )}
      </div>
    </div>
  )
}
