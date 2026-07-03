import { useMemo } from 'react'
import Icon from './ui/Icon'
import { useSelectedTimeOrder, setTimeOrder, useMaxTimeOrder } from '../store'

const PHASE_COLORS = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b',
  '#10b981', '#06b6d4', '#ef4444', '#84cc16',
]

function isPhaseSnap(s: any) {
  return !!s.phase && s.phase !== '未分阶段'
}

export default function CharacterArcTimeline({ characters }: { characters: any[] }) {
  const selectedTimeOrder = useSelectedTimeOrder()
  const globalMaxTime = useMaxTimeOrder()

  // Build per-character phase data
  const charRows = useMemo(() => {
    const maxTo = Math.max(globalMaxTime, 1)
    return characters.map(c => {
      const allSnaps = [...(c.snapshots || [])].sort((a, b) => (a.timeOrder || 0) - (b.timeOrder || 0))
      const phases = allSnaps.filter(isPhaseSnap)
      const legacy = allSnaps.filter(s => !isPhaseSnap(s))

      // Build phase segments with start/end percentages
      const segments: { phase: string; label: string; timeOrder: number; endOrder: number; color: string; isCurrent: boolean; pct: number; widthPct: number }[] = []

      if (phases.length > 0) {
        phases.forEach((p, i) => {
          const startOrder = p.timeOrder || 0
          const endOrder = i < phases.length - 1 ? (phases[i + 1].timeOrder || maxTo) : maxTo
          const pct = (startOrder / maxTo) * 100
          const widthPct = Math.max(((endOrder - startOrder) / maxTo) * 100, 5)
          segments.push({
            phase: p.phase || `阶段${i + 1}`,
            label: p.label || p.phase || `阶段${i + 1}`,
            timeOrder: startOrder,
            endOrder,
            color: PHASE_COLORS[i % PHASE_COLORS.length],
            isCurrent: !!p.isCurrent,
            pct,
            widthPct,
          })
        })
      } else if (legacy.length > 0) {
        // Legacy snapshots without phase grouping
        legacy.forEach((p, i) => {
          const startOrder = p.timeOrder || 0
          const endOrder = i < legacy.length - 1 ? (legacy[i + 1].timeOrder || maxTo) : maxTo
          const pct = (startOrder / maxTo) * 100
          const widthPct = Math.max(((endOrder - startOrder) / maxTo) * 100, 5)
          segments.push({
            phase: '未分阶段',
            label: p.label || `快照${i + 1}`,
            timeOrder: startOrder,
            endOrder,
            color: '#71717a',
            isCurrent: !!p.isCurrent,
            pct,
            widthPct,
          })
        })
      } else {
        // No snapshots — show a single gray bar
        segments.push({
          phase: '无阶段',
          label: '无阶段数据',
          timeOrder: 0,
          endOrder: maxTo,
          color: '#3f3f46',
          isCurrent: false,
          pct: 0,
          widthPct: 100,
        })
      }

      return { char: c, segments }
    })
  }, [characters, globalMaxTime])

  const maxTo = Math.max(globalMaxTime, 1)
  const currentTimePct = selectedTimeOrder > 0 ? (selectedTimeOrder / maxTo) * 100 : -1

  // Time markers
  const timeMarkers = useMemo(() => {
    const count = Math.min(Math.max(Math.floor(maxTo / 2), 4), 12)
    const step = maxTo / count
    return Array.from({ length: count + 1 }, (_, i) => Math.round(i * step))
  }, [maxTo])

  const totalPhases = charRows.reduce((acc, r) => acc + r.segments.filter(s => s.phase !== '无阶段').length, 0)
  const charsWithPhases = charRows.filter(r => r.segments.some(s => s.phase !== '无阶段' && s.phase !== '未分阶段')).length

  return (
    <div className="h-full flex flex-col bg-zinc-950/30">
      {/* Header */}
      <div className="px-6 py-3 border-b border-zinc-800 flex items-center justify-between shrink-0">
        <div className="flex gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5">
            <Icon name="users" size={12} className="text-violet-400" />
            <b className="text-zinc-300">{charRows.length}</b> 角色
          </span>
          <span className="flex items-center gap-1.5">
            <Icon name="git-branch" size={12} className="text-blue-400" />
            <b className="text-zinc-300">{totalPhases}</b> 阶段
          </span>
          <span className="flex items-center gap-1.5">
            <Icon name="trending-up" size={12} className="text-emerald-400" />
            <b className="text-zinc-300">{charsWithPhases}</b> 有弧光
          </span>
        </div>
        <div className="text-[10px] text-zinc-600">
          点击阶段色块同步时间轴 · 当前 T={selectedTimeOrder > 0 ? selectedTimeOrder : '全部'}
        </div>
      </div>

      {/* Time axis ruler */}
      <div className="px-4 py-2 border-b border-zinc-800/60 shrink-0 flex items-center">
        <div className="w-24 shrink-0 text-[10px] text-zinc-600 text-right pr-3">时间→</div>
        <div className="flex-1 relative h-5">
          {timeMarkers.map(t => (
            <div key={t} className="absolute flex flex-col items-center" style={{ left: `${(t / maxTo) * 100}%`, transform: 'translateX(-50%)' }}>
              <span className="text-[9px] text-zinc-600 font-mono">T{t}</span>
              <div className="w-px h-2 bg-zinc-700 mt-0.5" />
            </div>
          ))}
          {/* Current time indicator */}
          {currentTimePct >= 0 && (
            <div className="absolute top-0 bottom-0 w-0.5 bg-cyan-500 z-10" style={{ left: `${currentTimePct}%` }}>
              <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-cyan-400 shadow-md shadow-cyan-500/50" />
            </div>
          )}
        </div>
      </div>

      {/* Character rows */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        {charRows.map(({ char, segments }) => (
          <div key={char.id} className="flex items-center h-8 mb-1 group hover:bg-zinc-800/30 rounded transition-colors">
            {/* Character name */}
            <div className="w-24 shrink-0 pr-3 text-right">
              <span className="text-[11px] text-zinc-300 truncate block font-medium">{char.name}</span>
            </div>
            {/* Phase segments */}
            <div className="flex-1 relative h-6 rounded bg-zinc-900/60 overflow-hidden">
              {segments.map((seg, i) => (
                <button
                  key={i}
                  onClick={() => setTimeOrder(seg.timeOrder)}
                  className="absolute top-0 bottom-0 rounded flex items-center justify-center overflow-hidden transition-all hover:brightness-125"
                  style={{
                    left: `${seg.pct}%`,
                    width: `${seg.widthPct}%`,
                    background: seg.color,
                    opacity: selectedTimeOrder > 0 && seg.timeOrder > selectedTimeOrder ? 0.25 : 0.7,
                    boxShadow: seg.isCurrent ? 'inset 0 0 0 2px rgba(255,255,255,0.4)' : 'none',
                    border: selectedTimeOrder > 0 && seg.timeOrder <= selectedTimeOrder && seg.endOrder > selectedTimeOrder
                      ? '1px solid #22d3ee' : 'none',
                  }}
                  title={`${char.name} · ${seg.label} (T${seg.timeOrder})`}
                >
                  <span className="text-[9px] text-white/90 font-medium truncate px-1 whitespace-nowrap">
                    {seg.widthPct > 12 ? seg.label : ''}
                  </span>
                </button>
              ))}
              {/* Current time vertical line through this row */}
              {currentTimePct >= 0 && (
                <div className="absolute top-0 bottom-0 w-0.5 bg-cyan-400/60 pointer-events-none z-10" style={{ left: `${currentTimePct}%` }} />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="px-6 py-2 border-t border-zinc-800 shrink-0 flex items-center gap-3 text-[10px] text-zinc-600">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded" style={{ background: PHASE_COLORS[0], opacity: 0.7 }} /> 阶段色块
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded border-2 border-white/40" style={{ background: PHASE_COLORS[0], opacity: 0.7 }} /> 当前阶段
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded" style={{ background: '#3f3f46', opacity: 0.7 }} /> 无阶段数据
        </span>
        <span className="flex items-center gap-1">
          <span className="w-0.5 h-3 bg-cyan-400" /> 当前时间
        </span>
        <span className="ml-auto">暗淡 = 未来阶段</span>
      </div>
    </div>
  )
}
