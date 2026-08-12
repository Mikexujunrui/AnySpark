import Icon from '../ui/Icon'

// S98：运行进度条（真实计数，非猜测）
// progress = { stage, detail, turnIndex, maxIterations, doneSteps }
//  - turnIndex/maxIterations：core turn_start 携带的真实轮次（S108 起无硬上限，
//    maxIterations=null 时只显示"第 N 轮"不带百分比）
//  - doneSteps：已完成的工具执行步骤数（tool_execution_end ok 累计）
export default function ProgressIndicator({ progress }) {
  if (!progress) return null
  const { stage, detail, turnIndex, maxIterations, doneSteps } = progress
  // 轮次真实进度；完成时（done 事件）progress 置 null 隐藏，这里封顶 99 避免误导 100%
  const pct = maxIterations ? Math.min(Math.round(((turnIndex || 0) / maxIterations) * 100), 99) : null
  const roundLabel = maxIterations ? `第 ${turnIndex} / ${maxIterations} 轮` : `第 ${turnIndex} 轮`

  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-lg bg-sky-900/40 border border-sky-800/60 flex items-center justify-center shrink-0 mt-0.5">
        <Icon name="zap" size={13} className="text-sky-400" />
      </div>
      <div className="bg-zinc-800/80 border border-zinc-700 rounded-xl px-4 py-3 min-w-[360px]">
        <div className="flex items-center gap-2 mb-2">
          <Icon name="loader" size={13} className="text-accent animate-spin" />
          <span className="text-sm font-medium text-zinc-100">{stage || '处理中'}</span>
          <span className="ml-auto text-xs text-accent font-medium truncate max-w-[140px]">
            {pct !== null ? `${pct}%` : '运行中'}
          </span>
        </div>
        {detail && <p className="text-xs text-zinc-500 mb-2 truncate">{detail}</p>}
        <div className="h-1.5 bg-zinc-700/60 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-300"
            style={{ width: `${pct ?? 30}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-zinc-500 mt-1.5">
          <span>{turnIndex ? roundLabel : '推进中'}</span>
          <span>{doneSteps ? `已完成 ${doneSteps} 个工具步骤` : ''}</span>
        </div>
      </div>
    </div>
  )
}
