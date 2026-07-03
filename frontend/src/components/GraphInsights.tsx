import { useState, useEffect, useMemo } from 'react'
import Icon from './ui/Icon'

interface Dimension {
  name: string; score: number; finding: string; icon: string
}

interface CausalChain {
  cause: string; effect: string; link: string; severity: string; suggestion: string
}

interface ActionItem {
  priority: string; action: string; category: string
}

interface DiagnosisData {
  health_score: number
  summary: string
  dimensions: Dimension[]
  causal_chains: CausalChain[]
  action_items: ActionItem[]
  raw_data: {
    forgotten_count: number; foreshadow_count: number; disconnected_count: number
    bridge_count: number; unused_location_count: number; constraint_count: number; hard_constraint_count: number
  }
}

const DIMENSION_COLORS: Record<string, string> = {
  '角色连贯性': 'bg-sky-500',
  '伏笔管理': 'bg-amber-500',
  '关系网络': 'bg-violet-500',
  '地点利用': 'bg-emerald-500',
  '设定可信度': 'bg-blue-500',
  '约束合规': 'bg-red-500',
}

const SEVERITY_STYLES: Record<string, string> = {
  high: 'border-red-800/50 bg-red-950/20',
  medium: 'border-yellow-800/50 bg-yellow-950/20',
  low: 'border-blue-800/50 bg-blue-950/20',
}

const SEVERITY_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

const PRIORITY_BADGE: Record<string, string> = {
  high: 'bg-red-600/20 text-red-400 border-red-800/50',
  medium: 'bg-yellow-600/20 text-yellow-400 border-yellow-800/50',
  low: 'bg-blue-600/20 text-blue-400 border-blue-800/50',
}

const CATEGORY_ICONS: Record<string, string> = {
  '角色连贯性': 'users',
  '伏笔管理': 'target',
  '关系网络': 'git-merge',
  '地点利用': 'map-pin',
  '设定可信度': 'microscope',
  '约束合规': 'shield',
}

// ── SWR cache for instant panel switching ──
interface InsightsCache {
  diagnosis: DiagnosisData | null
  causalChain: any
  linkPred: any[]
}
const _insightsCache = new Map<string, InsightsCache>()

export default function GraphInsights({ bookId }: { bookId: string }) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisData | null>(null)
  const [causalChain, setCausalChain] = useState<any>(null)
  const [linkPred, setLinkPred] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAll()
  }, [bookId])

  async function loadAll() {
    const cached = _insightsCache.get(bookId)
    if (cached) {
      // Stale-while-revalidate: show cached data immediately, refresh in background
      setDiagnosis(cached.diagnosis)
      setCausalChain(cached.causalChain)
      setLinkPred(cached.linkPred)
      setLoading(false)
    } else {
      setLoading(true)
    }
    try {
      const [dRes, ccRes, lpRes] = await Promise.all([
        fetch(`/api/books/${bookId}/graph/diagnosis`),
        fetch(`/api/books/${bookId}/graph/event-causal-chain`),
        fetch(`/api/books/${bookId}/graph/link-prediction?top_n=8`),
      ])
      let newDiagnosis: DiagnosisData | null = null
      let newCC: any = null
      let newLP: any[] = []
      if (dRes.ok) { newDiagnosis = await dRes.json(); setDiagnosis(newDiagnosis) }
      if (ccRes.ok) { newCC = await ccRes.json(); setCausalChain(newCC) }
      if (lpRes.ok) { newLP = await lpRes.json() || []; setLinkPred(newLP) }
      // Update cache
      _insightsCache.set(bookId, {
        diagnosis: newDiagnosis,
        causalChain: newCC,
        linkPred: newLP,
      })
    } catch (e) {
      console.error('Insights fetch failed:', e)
    }
    setLoading(false)
  }

  const healthColor = useMemo(() => {
    if (!diagnosis) return 'text-zinc-500'
    if (diagnosis.health_score >= 80) return 'text-emerald-400'
    if (diagnosis.health_score >= 60) return 'text-yellow-400'
    return 'text-red-400'
  }, [diagnosis])

  const healthRing = useMemo(() => {
    if (!diagnosis) return 0
    const radius = 36; const circumference = 2 * Math.PI * radius
    return circumference * (1 - diagnosis.health_score / 100)
  }, [diagnosis])

  const avgScore = useMemo(() => {
    if (!diagnosis?.dimensions?.length) return 0
    return Math.round(diagnosis.dimensions.reduce((a, d) => a + d.score, 0) / diagnosis.dimensions.length)
  }, [diagnosis])

  if (loading) return (
    <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
      <div className="w-4 h-4 border-2 border-zinc-700 border-t-sky-400 rounded-full animate-spin mr-2" /> 分析中...
    </div>
  )
  if (!diagnosis) return <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">无法加载诊断数据</div>

  return (
    <div className="flex-1 w-full overflow-y-auto p-4 space-y-4">
      {/* ── 健康评分横幅 ── */}
      <div className="bg-zinc-900/40 backdrop-blur-sm border border-zinc-800/60 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <Icon name="brain" size={16} /> 叙事诊断
          </h2>
          <button onClick={loadAll} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <Icon name="refresh" size={12} />
          </button>
        </div>
        <div className="flex items-center gap-4">
          {/* 环形评分 */}
          <div className="relative shrink-0">
            <svg width={88} height={88} viewBox="0 0 88 88">
              <circle cx={44} cy={44} r={36} fill="none" stroke="#27272a" strokeWidth={6} />
              <circle
                cx={44} cy={44} r={36} fill="none"
                stroke={diagnosis.health_score >= 80 ? '#34d399' : diagnosis.health_score >= 60 ? '#fbbf24' : '#f87171'}
                strokeWidth={6} strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 36}`}
                strokeDashoffset={healthRing}
                transform="rotate(-90 44 44)"
                style={{ transition: 'stroke-dashoffset 0.8s ease' }}
              />
              <text x={44} y={40} textAnchor="middle" fill="currentColor" className={`text-lg font-bold ${healthColor}`} style={{ dominantBaseline: 'central' }}>
                {diagnosis.health_score}
              </text>
              <text x={44} y={58} textAnchor="middle" fill="#71717a" fontSize={9} style={{ dominantBaseline: 'central' }}>
                健康分
              </text>
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-sm text-zinc-300 leading-relaxed">{diagnosis.summary}</p>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {diagnosis.raw_data.hard_constraint_count > 0 && (
                <span className="text-[9px] px-2 py-0.5 rounded bg-red-600/20 text-red-400 border border-red-800/50">
                  硬约束 ×{diagnosis.raw_data.hard_constraint_count}
                </span>
              )}
              {diagnosis.raw_data.foreshadow_count > 0 && (
                <span className="text-[9px] px-2 py-0.5 rounded bg-yellow-600/20 text-yellow-400 border border-yellow-800/50">
                  伏笔 ×{diagnosis.raw_data.foreshadow_count}
                </span>
              )}
              {diagnosis.raw_data.unused_location_count > 0 && (
                <span className="text-[9px] px-2 py-0.5 rounded bg-zinc-700/30 text-zinc-400 border border-zinc-700/50">
                  地点 ×{diagnosis.raw_data.unused_location_count}
                </span>
              )}
              {diagnosis.raw_data.bridge_count > 0 && (
                <span className="text-[9px] px-2 py-0.5 rounded bg-blue-600/20 text-blue-400 border border-blue-800/50">
                  枢纽 ×{diagnosis.raw_data.bridge_count}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 六维评分仪表盘 ── */}
      <div className="bg-zinc-900/40 backdrop-blur-sm border border-zinc-800/60 rounded-xl p-4">
        <h3 className="text-xs font-medium text-zinc-400 flex items-center gap-2 mb-3">
          <Icon name="bar-chart" size={14} /> 维度评分
        </h3>
        <div className="space-y-2.5">
          {diagnosis.dimensions.map(dim => {
            const scoreColor = dim.score >= 80 ? 'bg-emerald-500' : dim.score >= 60 ? 'bg-yellow-500' : 'bg-red-500'
            const textColor = dim.score >= 80 ? 'text-emerald-400' : dim.score >= 60 ? 'text-yellow-400' : 'text-red-400'
            return (
              <div key={dim.name}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <Icon name={dim.icon} size={11} className={textColor} />
                    <span className="text-[10px] text-zinc-400">{dim.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-zinc-600">{dim.finding}</span>
                    <span className={`text-[11px] font-bold ${textColor}`}>{dim.score}</span>
                  </div>
                </div>
                <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-500 ${scoreColor}`} style={{ width: `${dim.score}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── 事件因果链 — 故事脊柱 ── */}
      {causalChain?.critical_path?.length > 0 && (
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-cyan-800/40 rounded-xl p-4">
          <h3 className="text-xs font-medium text-cyan-400 flex items-center gap-2 mb-2">
            <Icon name="git-branch" size={14} /> 故事脊柱 — 事件因果链
          </h3>
          <p className="text-[10px] text-zinc-500 mb-3">{causalChain.summary}</p>
          <div className="space-y-1">
            {causalChain.critical_path.map((ev: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-[10px]">
                <span className="text-cyan-400 font-mono shrink-0 w-8">T{ev.time_order}</span>
                {i > 0 && <span className="text-zinc-700">→</span>}
                <span className="text-zinc-300 truncate flex-1">{ev.label}</span>
                {ev.chapter_ref && <span className="text-zinc-600 shrink-0">{ev.chapter_ref}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 链接预测建议 ── */}
      {linkPred.length > 0 && (
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-amber-800/40 rounded-xl p-4">
          <h3 className="text-xs font-medium text-amber-400 flex items-center gap-2 mb-2">
            <Icon name="link" size={14} /> 关系预测建议
          </h3>
          <p className="text-[10px] text-zinc-500 mb-3">基于共同邻居分析，以下角色对可能需要建立直接关系</p>
          <div className="space-y-2">
            {linkPred.slice(0, 6).map((pred, i) => (
              <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-zinc-800/30 border border-zinc-800">
                <span className="text-[11px] font-medium text-violet-300">{pred.char_a_name}</span>
                <Icon name="arrow-right" size={10} className="text-zinc-600" />
                <span className="text-[11px] font-medium text-emerald-300">{pred.char_b_name}</span>
                <span className="text-[9px] text-zinc-600 ml-auto">{pred.common_neighbors}共同</span>
                <div className="w-12 h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-amber-600 to-amber-400 rounded-full" style={{ width: `${Math.min(pred.adamic_adar * 20, 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 推理链 ── */}
      {diagnosis.causal_chains.length > 0 && (
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-zinc-800/60 rounded-xl p-4">
          <h3 className="text-xs font-medium text-zinc-400 flex items-center gap-2 mb-3">
            <Icon name="git-merge" size={14} className="text-violet-400" /> 推理链
          </h3>
          <div className="space-y-3">
            {diagnosis.causal_chains.map((chain, i) => (
              <div key={i} className={`border rounded-lg p-3 ${SEVERITY_STYLES[chain.severity] || SEVERITY_STYLES.low}`}>
                {/* Severity badge */}
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border ${chain.severity === 'high' ? 'text-red-400 border-red-800/50 bg-red-600/20' : chain.severity === 'medium' ? 'text-yellow-400 border-yellow-800/50 bg-yellow-600/20' : 'text-blue-400 border-blue-800/50 bg-blue-600/20'}`}>
                    {SEVERITY_LABELS[chain.severity]}风险
                  </span>
                </div>
                {/* Cause → Effect → Link → Suggestion */}
                <div className="space-y-1.5">
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-zinc-600 shrink-0 mt-0.5">因</span>
                    <span className="text-[11px] text-zinc-300">{chain.cause}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-zinc-600 shrink-0 mt-0.5">果</span>
                    <span className="text-[11px] text-zinc-400">{chain.effect}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-[10px] text-zinc-600 shrink-0 mt-0.5">析</span>
                    <span className="text-[10px] text-zinc-500 italic">{chain.link}</span>
                  </div>
                  <div className="flex items-start gap-2 pt-1 border-t border-zinc-800/50">
                    <Icon name="lightbulb" size={11} className="text-amber-400 shrink-0 mt-0.5" />
                    <span className="text-[11px] text-amber-300">{chain.suggestion}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 行动建议 ── */}
      {diagnosis.action_items.length > 0 && (
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-zinc-800/60 rounded-xl p-4">
          <h3 className="text-xs font-medium text-zinc-400 flex items-center gap-2 mb-3">
            <Icon name="clipboard-list" size={14} className="text-amber-400" /> 行动建议
          </h3>
          <div className="space-y-2">
            {diagnosis.action_items.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="flex items-center gap-2 shrink-0 mt-0.5">
                  <span className="text-[10px] text-zinc-600 w-5 text-right">{i + 1}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border ${PRIORITY_BADGE[item.priority] || PRIORITY_BADGE.low}`}>
                    {item.priority === 'high' ? '高' : item.priority === 'medium' ? '中' : '低'}
                  </span>
                </div>
                <div className="flex-1">
                  <p className="text-[11px] text-zinc-300">{item.action}</p>
                  <span className="text-[9px] text-zinc-600 flex items-center gap-1 mt-0.5">
                    <Icon name={CATEGORY_ICONS[item.category] || 'info'} size={9} />
                    {item.category}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 全部正常时 ── */}
      {diagnosis.causal_chains.length === 0 && diagnosis.action_items.length === 0 && (
        <div className="bg-zinc-900/40 backdrop-blur-sm border border-emerald-800/30 rounded-xl p-6 text-center">
          <Icon name="check-circle" size={28} className="text-emerald-400 mx-auto mb-2" />
          <p className="text-sm text-emerald-400 font-medium">叙事结构健康</p>
          <p className="text-[10px] text-zinc-500 mt-1">所有维度评分良好，无推理链或行动建议</p>
        </div>
      )}
    </div>
  )
}