import Icon from '../ui/Icon'
import { estimateCost, formatCost, formatTokens } from '../../lib/cost'

// S100：常驻用量条（pi footer 语义）——本轮/会话累计 tokens + 估算成本。
// metrics 来自 useSSE done 帧：{ tokens: 本轮 usage, session_tokens: 会话累计, model }
export default function UsageStrip({ metrics }: { metrics: Record<string, any> | null }) {
  const tokens = metrics?.tokens
  const session = metrics?.session_tokens
  if (!metrics || (!tokens?.total_tokens && !session?.total_tokens)) return null
  const model = String(metrics.model || '')
  const sessionCost = estimateCost(model, session)

  return (
    <div className="flex items-center gap-2.5 text-[10px] text-zinc-500">
      <span className="w-9 shrink-0">用量</span>
      <span className="shrink-0 tabular-nums">
        本轮 <span className="text-zinc-300 font-medium">{formatTokens(tokens?.total_tokens)}</span>
      </span>
      <span className="text-zinc-700">·</span>
      <span className="shrink-0 tabular-nums">
        累计 <span className="text-zinc-300 font-medium">{formatTokens(session?.total_tokens)}</span>
      </span>
      <span className="text-zinc-700">·</span>
      <span className="shrink-0 flex items-center gap-0.5 tabular-nums">
        <Icon name="coins" size={9} className="text-amber-500/70" />
        <span className="text-amber-400/80">{formatCost(sessionCost)}</span>
      </span>
      {model && <span className="ml-auto shrink-0 text-zinc-600 truncate max-w-[110px]">{model}</span>}
    </div>
  )
}
