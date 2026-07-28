import { useState } from 'react'
import Icon from '../ui/Icon'

/**
 * @param {{ metrics: { llm_calls?: number, tool_calls?: number, rounds?: number, compactions?: number, finish_reason?: string, hallucination_hits?: Record<string, number>, drift_corrections?: number, subagent_spawned?: number } | null }} props
 */
export default function RunLedger({ metrics }) {
  const [expanded, setExpanded] = useState(false)

  if (!metrics || !metrics.rounds) return null

  // Enhanced: tool chain summary from metrics.tool_names
  const toolNames = metrics.tool_names || {}
  const topTools: [string, number][] = (Object.entries(toolNames) as [string, number][])
    .sort(([,a], [,b]) => b - a)
    .slice(0, 5)
  const hasToolChain = topTools.length > 0

  const hallucinationCount: number = metrics.hallucination_hits
    ? (Object.values(metrics.hallucination_hits) as number[]).reduce((a: number, b) => a + b, 0)
    : 0
  const hasIssues = hallucinationCount > 0 || ((metrics.drift_corrections as number) ?? 0) > 0

  const reasonLabels = {
    done: '完成',
    llm_error: 'LLM 错误',
    llm_empty: '空响应',
    review_result: '评审结束',
  }

  return (
    <div className="border-t border-zinc-800/60 px-3 py-1.5 bg-zinc-950/80 shrink-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Icon name={hasIssues ? 'alert-circle' : 'activity'} size={12}
          className={hasIssues ? 'text-amber-500' : 'text-zinc-500'} />
        <span className="flex items-center gap-1.5">
          <MetricBadge label="轮次" value={String(metrics.rounds)} />
          <span className="text-zinc-700">|</span>
          <MetricBadge label="LLM" value={String(metrics.llm_calls ?? 0)} />
          <span className="text-zinc-700">|</span>
          <MetricBadge label="工具" value={String(metrics.tool_calls ?? 0)} />
          {hasIssues && (
            <>
              <span className="text-zinc-700">|</span>
              <span className="text-amber-500">
                {hallucinationCount > 0 && `⚠幻觉×${hallucinationCount}`}
                {(metrics.drift_corrections ?? 0) > 0 && ` ⚡漂移×${metrics.drift_corrections}`}
              </span>
            </>
          )}
          {metrics.finish_reason && metrics.finish_reason !== 'done' && (
            <span className="text-zinc-600 ml-1">
              [{reasonLabels[metrics.finish_reason] || metrics.finish_reason}]
            </span>
          )}
        </span>
        <span className="ml-auto text-[10px] text-zinc-600">
          {expanded ? '收起 ▲' : '详情 ▼'}
        </span>
      </button>

      {expanded && (
        <div className="mt-2 grid grid-cols-3 gap-1.5 text-[10px]">
          <MetricTile label="LLM 调用" value={metrics.llm_calls ?? 0} />
          <MetricTile label="工具调用" value={`${metrics.tool_calls ?? 0}${hasToolChain ? ' (' + topTools.length + '种)' : ''}`} />
          <MetricTile label="总轮次" value={metrics.rounds ?? 0} />
          <MetricTile label="上下文压缩" value={metrics.compactions ?? 0} />
          <MetricTile label="漂移纠正" value={metrics.drift_corrections ?? 0} />
          <MetricTile label="子Agent" value={metrics.subagent_spawned ?? 0} />
          {hallucinationCount > 0 && (
            <div className="col-span-3 bg-amber-950/30 border border-amber-800/30 rounded px-2 py-1">
              <span className="text-amber-400">⚠ 幻觉检测: </span>
              <span className="text-amber-300/70">
                {Object.entries(metrics.hallucination_hits ?? {})
                  .map(([k, v]) => `${k}×${v}`)
                  .join(', ')}
              </span>
            </div>
          )}
          {hasToolChain && (
            <div className="col-span-3 bg-zinc-900/60 border border-zinc-800/40 rounded px-2 py-1.5">
              <div className="text-[10px] text-zinc-500 mb-1">工具调用分布</div>
              <div className="flex flex-wrap gap-1">
                {topTools.map(([name, count]) => (
                  <span key={name} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                    {name} ×{count}
                  </span>
                ))}
              </div>
            </div>
          )}
          {metrics.finish_reason && (
            <div className="col-span-3 text-zinc-500">
              完成原因: {reasonLabels[metrics.finish_reason] || metrics.finish_reason}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function MetricBadge({ label, value }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      <span className="text-zinc-600">{label}</span>
      <span className="text-zinc-400 font-medium">{value}</span>
    </span>
  )
}

function MetricTile({ label, value }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800/40 rounded px-2 py-1 text-center">
      <div className="text-zinc-400 font-medium">{value}</div>
      <div className="text-zinc-600 text-[9px]">{label}</div>
    </div>
  )
}
