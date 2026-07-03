export default function ContextBar({ contextUsage }) {
  if (!contextUsage) return null

  return (
    <div className="flex items-center gap-2.5">
      <span className="text-[10px] text-zinc-500 w-9 shrink-0">上下文</span>
      <div className="flex-1 h-1.5 bg-zinc-700/70 rounded-full overflow-hidden relative max-w-[160px]">
        <div className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(contextUsage.ratio || 0, 100)}%`,
            background: contextUsage.ratio > 80 ? '#ef4444' : contextUsage.ratio > 50 ? '#f59e0b' : '#10b981'
          }} />
      </div>
      <span className="text-[10px] text-zinc-400 shrink-0 tabular-nums">
        {contextUsage.tokens >= 1000 ? `${(contextUsage.tokens/1000).toFixed(1)}K` : contextUsage.tokens}
        {' / 1M'}
      </span>
    </div>
  )
}
