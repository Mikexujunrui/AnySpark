import { useState, useEffect, useMemo, useCallback } from 'react'
import Icon from './ui/Icon'

interface MetricsData {
  entity_count: number
  relation_count: number
  density: number
  isolated_entities: { name: string; type: string }[]
  isolated_count: number
  largest_component_size: number
  fragmentation_ratio: number
  health_assessment: string
  health_score?: number
}

interface InsightsData {
  forgotten_characters: { entity_id: string; name: string; last_seen_time_order: number; important: boolean }[]
  unresolved_foreshadows: { id: string; text: string; related_entities: string[] }[]
  disconnected_pairs: { entity_a: { id: string; name: string }; entity_b: { id: string; name: string }; warning: string }[]
  bridge_characters: { entity_id: string; entity_name: string; bridge_count: number; would_disconnect: string[][] }[]
  underutilized_locations: string[]
  suggestions: { type: string; priority: string; message: string }[]
  confidence_scores?: { entity_id: string; entity_name: string; entity_type: string; confidence: number; stars: number; recommendation: string }[]
  constraint_violations?: { constraint_id: string; description: string; severity: string; violations: Record<string, string>[] }[]
}

interface LocationImportance {
  entity_id: string; name: string; composite_score: number; role: string
  degree: number; event_count: number; character_visits: number
}

interface OrgImportance {
  entity_id: string; name: string; composite_score: number; role: string
  degree: number; member_count: number; event_count: number
}

interface ClusteringCoef {
  entity_id: string; name: string; clustering_coefficient: number
  neighbor_count: number; edges_among_neighbors: number
}

interface LinkPrediction {
  char_a_id: string; char_a_name: string; char_b_id: string; char_b_name: string
  common_neighbors: number; adamic_adar: number; jaccard: number
}

const CARD_BASE = 'bg-zinc-900/40 backdrop-blur-sm border border-zinc-800/60 rounded-xl'
const CARD_HEADER = 'flex items-center gap-2 mb-2.5'

// ── SWR cache for instant panel switching ──
interface MetricsCache {
  metrics: MetricsData | null
  insights: InsightsData | null
  locImportance: LocationImportance[]
  orgImportance: OrgImportance[]
  clustering: ClusteringCoef[]
  linkPred: LinkPrediction[]
}
const _metricsCache = new Map<string, MetricsCache>()

const HEALTH_COLORS: Record<string, string> = {
  '良好': 'text-emerald-400',
  '一般': 'text-yellow-400',
  '稀疏': 'text-red-400',
}

const HEALTH_BG: Record<string, string> = {
  '良好': 'bg-emerald-950/30 border-emerald-800/40',
  '一般': 'bg-yellow-950/30 border-yellow-800/40',
  '稀疏': 'bg-red-950/30 border-red-800/40',
}

const ROLE_GRADIENTS: Record<string, string> = {
  '主角': 'from-violet-600/30 to-purple-600/10 border-violet-500/30',
  '核心地点': 'from-emerald-600/30 to-teal-600/10 border-emerald-500/30',
  '核心势力': 'from-blue-600/30 to-indigo-600/10 border-blue-500/30',
}

export default function WorldbuildingMetrics({ bookId }: { bookId: string }) {
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [insights, setInsights] = useState<InsightsData | null>(null)
  const [locImportance, setLocImportance] = useState<LocationImportance[]>([])
  const [orgImportance, setOrgImportance] = useState<OrgImportance[]>([])
  const [clustering, setClustering] = useState<ClusteringCoef[]>([])
  const [linkPred, setLinkPred] = useState<LinkPrediction[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'characters' | 'locations' | 'predictions'>('overview')

  const loadAll = useCallback(async () => {
    const cached = _metricsCache.get(bookId)
    if (cached) {
      // Stale-while-revalidate: show cached data immediately, refresh in background
      setMetrics(cached.metrics)
      setInsights(cached.insights)
      setLocImportance(cached.locImportance)
      setOrgImportance(cached.orgImportance)
      setClustering(cached.clustering)
      setLinkPred(cached.linkPred)
      setLoading(false)
    } else {
      setLoading(true)
    }
    try {
      const [mRes, iRes, locRes, orgRes, ccRes, lpRes] = await Promise.all([
        fetch(`/api/books/${bookId}/graph/metrics`),
        fetch(`/api/books/${bookId}/graph/insights`),
        fetch(`/api/books/${bookId}/graph/location-importance`),
        fetch(`/api/books/${bookId}/graph/organization-importance`),
        fetch(`/api/books/${bookId}/graph/clustering-coefficient`),
        fetch(`/api/books/${bookId}/graph/link-prediction?top_n=10`),
      ])
      let newMetrics: MetricsData | null = null
      let newInsights: InsightsData | null = null
      let newLoc: LocationImportance[] = []
      let newOrg: OrgImportance[] = []
      let newCC: ClusteringCoef[] = []
      let newLP: LinkPrediction[] = []
      if (mRes.ok) { newMetrics = await mRes.json(); setMetrics(newMetrics) }
      if (iRes.ok) {
        const data = await iRes.json()
        newInsights = {
          forgotten_characters: data.forgotten_characters || [],
          unresolved_foreshadows: data.unresolved_foreshadows || [],
          disconnected_pairs: data.disconnected_pairs || [],
          bridge_characters: data.bridge_characters || [],
          underutilized_locations: data.underutilized_locations || [],
          suggestions: data.suggestions || [],
          confidence_scores: data.confidence_scores || [],
          constraint_violations: data.constraint_violations || [],
        }
        setInsights(newInsights)
      }
      if (locRes.ok) { newLoc = await locRes.json(); setLocImportance(newLoc) }
      if (orgRes.ok) { newOrg = await orgRes.json(); setOrgImportance(newOrg) }
      if (ccRes.ok) { newCC = await ccRes.json(); setClustering(newCC) }
      if (lpRes.ok) { newLP = await lpRes.json(); setLinkPred(newLP) }
      // Update cache
      _metricsCache.set(bookId, {
        metrics: newMetrics,
        insights: newInsights,
        locImportance: newLoc,
        orgImportance: newOrg,
        clustering: newCC,
        linkPred: newLP,
      })
    } catch (e) {
      console.error('Metrics fetch failed:', e)
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadAll() }, [loadAll])

  const densityPercent = useMemo(() => metrics ? Math.round(metrics.density * 1000) / 10 : 0, [metrics])
  const connectivityPercent = useMemo(() => {
    if (!metrics || metrics.entity_count === 0) return 0
    return Math.round((metrics.largest_component_size / metrics.entity_count) * 100)
  }, [metrics])
  const avgRelations = useMemo(() => {
    if (!metrics || metrics.entity_count === 0) return 0
    return Math.round((metrics.relation_count / metrics.entity_count) * 10) / 10
  }, [metrics])
  const fragPercent = useMemo(() => Math.round((metrics?.fragmentation_ratio || 0) * 100), [metrics])
  const isolatedPercent = useMemo(() => {
    if (!metrics || metrics.entity_count === 0) return 0
    return Math.round((metrics.isolated_count / metrics.entity_count) * 100)
  }, [metrics])

  const forgottenCount = insights?.forgotten_characters?.length ?? 0
  const foreshadowCount = insights?.unresolved_foreshadows?.length ?? 0
  const bridgeCount = insights?.bridge_characters?.length ?? 0
  const disconnectedCount = insights?.disconnected_pairs?.length ?? 0
  const unusedLocCount = insights?.underutilized_locations?.length ?? 0
  const constraintCount = insights?.constraint_violations?.length ?? 0
  const riskScore = metrics?.health_score ?? 0
  const allClear = metrics?.isolated_count === 0 && forgottenCount === 0 && foreshadowCount === 0 && disconnectedCount === 0 && constraintCount === 0

  // Clustering stats
  const avgCC = useMemo(() => {
    if (!clustering.length) return 0
    return Math.round(clustering.reduce((a, c) => a + c.clustering_coefficient, 0) / clustering.length * 100) / 100
  }, [clustering])

  if (loading) return (
    <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
      <div className="w-4 h-4 border-2 border-zinc-700 border-t-sky-400 rounded-full animate-spin mr-2" /> 加载指标中...
    </div>
  )
  if (!metrics) return <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">无法加载指标数据</div>

  return (
    <div className="flex-1 w-full flex flex-col overflow-hidden">
      {/* ── Tab bar ── */}
      <div className="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-zinc-800/60 bg-zinc-950/40">
        {([
          { key: 'overview', label: '总览', icon: 'activity' },
          { key: 'characters', label: '角色分析', icon: 'users' },
          { key: 'locations', label: '地点/组织', icon: 'map-pin' },
          { key: 'predictions', label: '预测建议', icon: 'lightbulb' },
        ] as const).map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-all flex items-center gap-1.5 ${
              activeTab === tab.key
                ? 'bg-zinc-800/80 text-zinc-100 border border-zinc-700'
                : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
            }`}
          >
            <Icon name={tab.icon} size={12} /> {tab.label}
          </button>
        ))}
        <button onClick={loadAll} className="ml-auto text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800/50 transition-colors">
          <Icon name="refresh" size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {activeTab === 'overview' && (
          <>
            {/* ── 健康度横幅 ── */}
            <div className={`border rounded-xl p-4 backdrop-blur-sm ${HEALTH_BG[metrics.health_assessment] || HEALTH_BG['稀疏']}`}>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
                  <Icon name="activity" size={16} /> 世界观健康度
                </h2>
              </div>
              <div className="flex items-center gap-4">
                <div className={`text-3xl font-bold ${HEALTH_COLORS[metrics.health_assessment] || HEALTH_COLORS['稀疏']}`}>
                  {metrics.health_assessment}
                </div>
                <div className="flex-1">
                  <div className="text-[10px] text-zinc-500 mb-1">综合风险评分</div>
                  <div className="h-2.5 bg-black/30 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${riskScore < 20 ? 'bg-gradient-to-r from-emerald-600 to-emerald-400' : riskScore < 50 ? 'bg-gradient-to-r from-yellow-600 to-yellow-400' : 'bg-gradient-to-r from-red-600 to-red-400'}`}
                      style={{ width: `${riskScore}%` }}
                    />
                  </div>
                </div>
                <div className={`text-2xl font-bold ${riskScore < 20 ? 'text-emerald-400' : riskScore < 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {riskScore}<span className="text-[10px] text-zinc-600">/100</span>
                </div>
              </div>
            </div>

            {/* ── 核心拓扑指标 ── */}
            <div className="grid grid-cols-2 gap-2">
              <GlassCard icon="users" label="实体总数" value={metrics.entity_count} sub={`平均 ${avgRelations} 关系/实体`} />
              <GlassCard icon="link" label="关系总数" value={metrics.relation_count} sub={`碎片化 ${fragPercent}%`} />
              <GlassCard icon="bar-chart" label="连接密度" value={`${densityPercent}%`} barValue={Math.min(densityPercent * 5, 100)} barColor="from-blue-600 to-blue-400" />
              <GlassCard icon="git-merge" label="主连通率" value={`${connectivityPercent}%`} barValue={connectivityPercent} barColor="from-emerald-600 to-emerald-400" />
            </div>

            {/* ── 叙事健康指标 ── */}
            <div className={`${CARD_BASE} p-3`}>
              <div className={CARD_HEADER}>
                <Icon name="book-open" size={14} className="text-violet-400" />
                <span className="text-xs font-medium text-violet-400">叙事健康</span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <StatRow icon="target" label="待回收伏笔" value={foreshadowCount} warn={foreshadowCount > 5} />
                <StatRow icon="user-x" label="被遗忘角色" value={forgottenCount} warn={forgottenCount > 3} />
                <StatRow icon="git-merge" label="枢纽角色" value={bridgeCount} good={bridgeCount > 0} />
                <StatRow icon="unlink" label="无关联角色对" value={disconnectedCount} warn={disconnectedCount > 0} />
                <StatRow icon="map-pin" label="未使用地点" value={unusedLocCount} warn={unusedLocCount > 0} />
                <StatRow icon="alert-triangle" label="孤立实体" value={metrics.isolated_count} warn={metrics.isolated_count > 0} sub={`${isolatedPercent}%`} />
              </div>
            </div>

            {/* ── 聚类系数 ── */}
            {clustering.length > 0 && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="share-2" size={14} className="text-cyan-400" />
                  <span className="text-xs font-medium text-cyan-400">社交网络聚类</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">平均系数 {avgCC}</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2">高系数=紧密社交圈，低系数=松散网络</p>
                <div className="space-y-1.5 max-h-32 overflow-y-auto">
                  {clustering.slice(0, 8).map((c, i) => (
                    <div key={i} className="flex items-center justify-between text-[10px]">
                      <span className="text-zinc-300 truncate">{c.name}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full" style={{ width: `${c.clustering_coefficient * 100}%` }} />
                        </div>
                        <span className="text-zinc-500 w-8 text-right">{c.clustering_coefficient.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 写作建议 ── */}
            <div className={`${CARD_BASE} p-3`}>
              <div className={CARD_HEADER}>
                <Icon name="lightbulb" size={14} className="text-amber-400" />
                <span className="text-xs font-medium text-amber-400">写作建议</span>
              </div>
              {allClear ? (
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400">
                  <Icon name="check-circle" size={12} /> 世界观结构良好，各项指标正常
                </div>
              ) : (
                <ul className="space-y-1.5 text-[10px] text-zinc-400">
                  {metrics.density < 0.05 && <li className="flex items-start gap-1.5"><span className="text-yellow-500 mt-0.5">•</span><span>连接密度较低 ({densityPercent}%)，建议添加更多角色之间的关系</span></li>}
                  {metrics.isolated_count > 0 && <li className="flex items-start gap-1.5"><span className="text-yellow-500 mt-0.5">•</span><span>{metrics.isolated_count} 个孤立实体 ({isolatedPercent}%)，建议融入主线剧情</span></li>}
                  {connectivityPercent < 80 && <li className="flex items-start gap-1.5"><span className="text-yellow-500 mt-0.5">•</span><span>主连通率偏低 ({connectivityPercent}%)，可能存在多个独立故事线</span></li>}
                  {foreshadowCount > 5 && <li className="flex items-start gap-1.5"><span className="text-yellow-500 mt-0.5">•</span><span>{foreshadowCount} 个待回收伏笔，建议尽快回收</span></li>}
                  {forgottenCount > 3 && <li className="flex items-start gap-1.5"><span className="text-yellow-500 mt-0.5">•</span><span>{forgottenCount} 个角色被遗忘，建议安排出场</span></li>}
                </ul>
              )}
            </div>
          </>
        )}

        {activeTab === 'characters' && (
          <>
            {/* ── 角色重要性 ── */}
            <div className={`${CARD_BASE} p-3`}>
              <div className={CARD_HEADER}>
                <Icon name="users" size={14} className="text-violet-400" />
                <span className="text-xs font-medium text-violet-400">角色重要性排名</span>
                <span className="text-[10px] text-zinc-600 ml-auto">PageRank + 度中心性 + 出场频率</span>
              </div>
              <p className="text-[10px] text-zinc-500 mb-2">综合评分融合真PageRank迭代(权重35%)、度中心性(40%)、出场频率(25%)</p>
              <CharacterImportanceList bookId={bookId} />
            </div>

            {/* ── 聚类系数详情 ── */}
            {clustering.length > 0 && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="share-2" size={14} className="text-cyan-400" />
                  <span className="text-xs font-medium text-cyan-400">聚类系数详情</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">平均 {avgCC}</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2">衡量角色社交圈紧密程度：邻居间互连比例</p>
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {clustering.map((c, i) => (
                    <div key={i} className="flex items-center justify-between text-[10px]">
                      <span className="text-zinc-300 truncate flex-1">{c.name}</span>
                      <span className="text-zinc-600 shrink-0 ml-2">{c.edges_among_neighbors}/{Math.floor(c.neighbor_count * (c.neighbor_count - 1) / 2)}对</span>
                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full" style={{ width: `${c.clustering_coefficient * 100}%` }} />
                        </div>
                        <span className="text-zinc-400 w-8 text-right">{c.clustering_coefficient.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 枢纽角色 ── */}
            {bridgeCount > 0 && insights?.bridge_characters && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="git-merge" size={14} className="text-blue-400" />
                  <span className="text-xs text-blue-400 font-medium">关键枢纽角色 ({bridgeCount})</span>
                </div>
                <div className="space-y-1.5">
                  {insights.bridge_characters.slice(0, 5).map((b, i) => (
                    <div key={i} className="flex items-center justify-between text-[10px]">
                      <span className="text-zinc-300">{b.entity_name}</span>
                      <div className="flex items-center gap-1">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded-full" style={{ width: `${Math.min(b.bridge_count * 10, 100)}%` }} />
                        </div>
                        <span className="text-zinc-500">{b.bridge_count}对</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'locations' && (
          <>
            {locImportance.length === 0 && orgImportance.length === 0 && (
              <div className={`${CARD_BASE} p-6 text-center`}>
                <Icon name="map-pin" size={24} className="text-zinc-700 mx-auto mb-2" />
                <p className="text-sm text-zinc-500">暂无地点/组织数据</p>
                <p className="text-[10px] text-zinc-600 mt-1">请在知识库中添加地点或组织类型实体</p>
              </div>
            )}
            {/* ── 地点重要性 ── */}
            {locImportance.length > 0 && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="map-pin" size={14} className="text-emerald-400" />
                  <span className="text-xs font-medium text-emerald-400">地点重要性排名</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">度+事件+角色访问</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2">权重: 度×30% + 事件数×40% + 角色访问×30%</p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {locImportance.slice(0, 15).map((loc, i) => (
                    <div key={i} className={`p-2 rounded-lg border ${ROLE_GRADIENTS[loc.role] || 'border-zinc-800 bg-zinc-800/30'}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-medium text-zinc-200">{loc.name}</span>
                        <span className="text-[9px] text-zinc-400">{loc.role}</span>
                      </div>
                      <div className="flex items-center gap-3 text-[9px] text-zinc-500">
                        <span>度:{loc.degree}</span>
                        <span>事件:{loc.event_count}</span>
                        <span>访问:{loc.character_visits}</span>
                        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden ml-2">
                          <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full" style={{ width: `${loc.composite_score}%` }} />
                        </div>
                        <span className="text-zinc-400 w-6 text-right">{loc.composite_score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 组织重要性 ── */}
            {orgImportance.length > 0 && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="building" size={14} className="text-blue-400" />
                  <span className="text-xs font-medium text-blue-400">组织/势力排名</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">度+成员+事件</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2">权重: 度×25% + 成员数×45% + 事件数×30%</p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {orgImportance.slice(0, 15).map((org, i) => (
                    <div key={i} className={`p-2 rounded-lg border ${ROLE_GRADIENTS[org.role] || 'border-zinc-800 bg-zinc-800/30'}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-medium text-zinc-200">{org.name}</span>
                        <span className="text-[9px] text-zinc-400">{org.role}</span>
                      </div>
                      <div className="flex items-center gap-3 text-[9px] text-zinc-500">
                        <span>度:{org.degree}</span>
                        <span>成员:{org.member_count}</span>
                        <span>事件:{org.event_count}</span>
                        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden ml-2">
                          <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded-full" style={{ width: `${org.composite_score}%` }} />
                        </div>
                        <span className="text-zinc-400 w-6 text-right">{org.composite_score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'predictions' && (
          <>
            {linkPred.length === 0 && (
              <div className={`${CARD_BASE} p-6 text-center`}>
                <Icon name="lightbulb" size={24} className="text-zinc-700 mx-auto mb-2" />
                <p className="text-sm text-zinc-500">暂无关系预测数据</p>
                <p className="text-[10px] text-zinc-600 mt-1">需要至少3个角色且部分角色有共同熟人</p>
              </div>
            )}
            {/* ── 链接预测 ── */}
            {linkPred.length > 0 && (
              <div className={`${CARD_BASE} p-3`}>
                <div className={CARD_HEADER}>
                  <Icon name="link" size={14} className="text-amber-400" />
                  <span className="text-xs font-medium text-amber-400">关系预测建议</span>
                  <span className="text-[10px] text-zinc-600 ml-auto">Adamic-Adar + Jaccard</span>
                </div>
                <p className="text-[10px] text-zinc-500 mb-2">基于共同邻居预测"应该存在但缺失"的角色关系</p>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {linkPred.map((pred, i) => (
                    <div key={i} className="p-2 rounded-lg bg-zinc-800/30 border border-zinc-800">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[11px] font-medium text-violet-300">{pred.char_a_name}</span>
                        <Icon name="arrow-right" size={10} className="text-zinc-600" />
                        <span className="text-[11px] font-medium text-emerald-300">{pred.char_b_name}</span>
                      </div>
                      <div className="flex items-center gap-3 text-[9px] text-zinc-500">
                        <span>共同邻居: {pred.common_neighbors}</span>
                        <span>AA: {pred.adamic_adar}</span>
                        <span>Jaccard: {pred.jaccard}</span>
                      </div>
                      <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-amber-600 to-amber-400 rounded-full" style={{ width: `${Math.min(pred.adamic_adar * 20, 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 事件因果链 ── */}
            <EventCausalChainCard bookId={bookId} />

            {/* ── 孤立实体 ── */}
            {metrics.isolated_count > 0 && (
              <div className={`${CARD_BASE} p-3 border-yellow-800/40`}>
                <div className={CARD_HEADER}>
                  <Icon name="alert-triangle" size={14} className="text-yellow-500" />
                  <span className="text-xs text-yellow-400 font-medium">孤立实体 ({metrics.isolated_count})</span>
                </div>
                <div className="space-y-1 max-h-28 overflow-y-auto">
                  {metrics.isolated_entities.slice(0, 10).map((e, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px] text-zinc-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-yellow-600" />
                      <span>{e.name}</span>
                      <span className="text-zinc-600">({e.type})</span>
                    </div>
                  ))}
                  {metrics.isolated_count > 10 && <div className="text-[10px] text-zinc-600 pt-1">...还有 {metrics.isolated_count - 10} 个</div>}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── 子组件 ──

function GlassCard({ icon, label, value, sub, barValue, barColor }: {
  icon: string; label: string; value: any; sub?: string; barValue?: number; barColor?: string
}) {
  return (
    <div className={`${CARD_BASE} p-2.5`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon name={icon} size={12} className="text-zinc-500" />
        <span className="text-[10px] text-zinc-500">{label}</span>
      </div>
      <div className="text-xl font-bold text-zinc-200">{value}</div>
      {sub && <div className="text-[9px] text-zinc-600 mt-0.5">{sub}</div>}
      {barValue !== undefined && barColor && (
        <div className="mt-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-700 bg-gradient-to-r ${barColor}`} style={{ width: `${barValue}%` }} />
        </div>
      )}
    </div>
  )
}

function StatRow({ icon, label, value, sub, good, warn }: {
  icon: string; label: string; value: number; sub?: string; good?: boolean; warn?: boolean
}) {
  const colorClass = good ? 'text-emerald-400' : warn ? 'text-amber-400' : 'text-zinc-300'
  return (
    <div className="flex items-center justify-between text-[10px]">
      <div className="flex items-center gap-1.5">
        <Icon name={icon} size={11} className="text-zinc-600" />
        <span className="text-zinc-500">{label}</span>
      </div>
      <div className="flex items-center gap-1">
        <span className={`font-medium ${colorClass}`}>{value}</span>
        {sub && <span className="text-zinc-700">{sub}</span>}
      </div>
    </div>
  )
}

// ── 角色重要性列表（内联fetch） ──
function CharacterImportanceList({ bookId }: { bookId: string }) {
  const [data, setData] = useState<any[]>([])
  useEffect(() => {
    fetch(`/api/books/${bookId}/graph/character-importance`).then(r => r.json()).then(d => setData(d || [])).catch(() => {})
  }, [bookId])

  if (!data.length) return <p className="text-[10px] text-zinc-600">暂无角色重要性数据</p>

  return (
    <div className="space-y-1.5 max-h-64 overflow-y-auto">
      {data.slice(0, 15).map((c, i) => (
        <div key={i} className={`p-2 rounded-lg border ${ROLE_GRADIENTS[c.role] || 'border-zinc-800 bg-zinc-800/30'}`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-medium text-zinc-200">{c.name}</span>
            <span className="text-[9px] text-zinc-400">{c.role}</span>
          </div>
          <div className="flex items-center gap-3 text-[9px] text-zinc-500">
            <span>度:{c.degree}</span>
            <span>出场:{c.appearances}</span>
            <span>PR:{c.pagerank_score}</span>
            <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden ml-2">
              <div className="h-full bg-gradient-to-r from-violet-600 to-purple-400 rounded-full" style={{ width: `${c.composite_score}%` }} />
            </div>
            <span className="text-zinc-400 w-6 text-right">{c.composite_score}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── 事件因果链卡片 ──
function EventCausalChainCard({ bookId }: { bookId: string }) {
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    fetch(`/api/books/${bookId}/graph/event-causal-chain`).then(r => r.json()).then(d => setData(d)).catch(() => {})
  }, [bookId])

  if (!data || !data.critical_path?.length) return null

  return (
    <div className={`${CARD_BASE} p-3`}>
      <div className={CARD_HEADER}>
        <Icon name="git-branch" size={14} className="text-cyan-400" />
        <span className="text-xs font-medium text-cyan-400">事件因果链 — 故事脊柱</span>
      </div>
      <p className="text-[10px] text-zinc-500 mb-2">{data.summary}</p>
      <div className="space-y-1">
        {data.critical_path.map((ev: any, i: number) => (
          <div key={i} className="flex items-center gap-2 text-[10px]">
            <span className="text-cyan-400 font-mono shrink-0">T{ev.time_order}</span>
            <div className="flex items-center gap-1 flex-1">
              {i > 0 && <span className="text-zinc-700">→</span>}
              <span className="text-zinc-300 truncate">{ev.label}</span>
            </div>
            {ev.chapter_ref && <span className="text-zinc-600 shrink-0">{ev.chapter_ref}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
