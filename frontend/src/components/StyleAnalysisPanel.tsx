/** Style Analysis Panel — analyzes the current book's own chapters.
 *  Deep style (sentence rhythm / rhetoric density / prophecy / POV)
 *  + Emotional curve + basic Structure & Style fingerprint.
 */
import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import Icon from './ui/Icon'
import { showToast } from './ui/toast-utils'

// ── Types ──

interface DeepStyleData {
  book_id: string
  chapter_count: number
  parallel_ratio?: number
  four_six_prose_density?: number
  classical_marker_density?: number
  long_short_alternation?: number
  inversion_frequency?: number
  metaphor_density?: number
  personification_density?: number
  antithesis_density?: number
  allusion_density?: number
  prophecy_frequency?: number
  foreshadowing_density?: number
  omen_density?: number
  first_person_ratio?: number
  third_person_ratio?: number
  omniscient_ratio?: number
  pov_shift_frequency?: number
}

interface EmotionalCurveData {
  book_id: string
  chapter_count: number
  chapter_tone_sequence: { chapter: number; title: string; tone: string; valence: number }[]
  joy_to_sorrow_ratio: number
  dominant_tone: string
  emotional_volatility: number
}

interface StructureData {
  book_id: string
  chapter_count: number
  total_words: number
  avg_chapter_length: number
  avg_dialogue_ratio: number
  chapter_length_distribution: number[]
  pacing_curve?: { chapter: number; pace_score: number }[]
}

interface StyleData {
  book_id: string
  vocabulary_richness_ttr: number
  four_char_idiom_density: number
  dialogue_density: number
  sentence_length_distribution: Record<string, number>
  punctuation_pattern: Record<string, number>
}

// ── Constants ──

const DEEP_TYPES = [
  { key: 'sentence_rhythm', label: '句式韵律', color: 'violet' },
  { key: 'rhetoric_density', label: '修辞密度', color: 'amber' },
  { key: 'prophecy_signature', label: '谶语特征', color: 'rose' },
  { key: 'narrative_pov', label: '叙事视角', color: 'sky' },
] as const

const FIELD_LABELS: Record<string, string> = {
  parallel_ratio: '对仗句占比',
  four_six_prose_density: '四六骈文密度',
  classical_marker_density: '文言标记密度',
  long_short_alternation: '长短句交替',
  inversion_frequency: '倒装句频次',
  metaphor_density: '比喻密度',
  personification_density: '拟人密度',
  antithesis_density: '排比密度',
  allusion_density: '典故密度',
  prophecy_frequency: '谶语频率',
  foreshadowing_density: '伏笔密度',
  omen_density: '预兆密度',
  first_person_ratio: '第一人称占比',
  third_person_ratio: '第三人称占比',
  omniscient_ratio: '全知视角占比',
  pov_shift_frequency: '视角切换频率',
}

const TONE_COLORS: Record<string, string> = {
  joy: '#f59e0b', calm: '#10b981', sorrow: '#3b82f6', tension: '#ef4444',
  neutral: '#6b7280', anger: '#dc2626', surprise: '#8b5cf6',
}
const TONE_LABELS: Record<string, string> = {
  joy: '喜悦', calm: '平静', sorrow: '悲伤', tension: '紧张',
  neutral: '中性', anger: '愤怒', surprise: '惊奇',
}

// ── Component ──

export default function StyleAnalysisPanel({ bookId }: { bookId: string }) {
  const [tab, setTab] = useState<'deep' | 'emotion' | 'basic'>('deep')
  const [analyzing, setAnalyzing] = useState(false)
  const [deepData, setDeepData] = useState<Record<string, DeepStyleData> | null>(null)
  const [emotionData, setEmotionData] = useState<EmotionalCurveData | null>(null)
  const [structureData, setStructureData] = useState<StructureData | null>(null)
  const [styleData, setStyleData] = useState<StyleData | null>(null)
  const [status, setStatus] = useState<Record<string, boolean>>({})

  // Check cached status on mount
  const checkStatus = useCallback(async () => {
    try {
      const res = await api.listAnalyses(bookId)
      const s: Record<string, boolean> = {}
      for (const a of res.analyses) {
        if (a.ref_book_id === bookId) {
          s.structure = !!a.structure
          s.style = !!a.style_fingerprint
          s.deep_style = !!a.deep_style
          s.emotional_curve = !!a.emotional_curve
        }
      }
      setStatus(s)
    } catch { /* ignore */ }
  }, [bookId])

  useEffect(() => { checkStatus() }, [checkStatus])

  // ── Run analyses ──

  async function runDeepAnalysis() {
    setAnalyzing(true)
    const results: Record<string, DeepStyleData> = {}
    for (const t of DEEP_TYPES) {
      try {
        const data = await api.triggerDeepStyle(bookId, t.key, bookId)
        results[t.key] = data as unknown as DeepStyleData
      } catch (e) {
        showToast(`${t.label}分析失败: ${e instanceof Error ? e.message : ''}`, 'error')
      }
    }
    if (Object.keys(results).length > 0) {
      setDeepData(results)
      setTab('deep')
      showToast('深度文风分析完成', 'success')
    }
    setAnalyzing(false)
    checkStatus()
  }

  async function runEmotionAnalysis() {
    setAnalyzing(true)
    try {
      const data = await api.triggerEmotionalCurve(bookId, bookId)
      setEmotionData(data as unknown as EmotionalCurveData)
      setTab('emotion')
      showToast('情感弧线分析完成', 'success')
    } catch (e) {
      showToast(`情感分析失败: ${e instanceof Error ? e.message : ''}`, 'error')
    }
    setAnalyzing(false)
    checkStatus()
  }

  async function runBasicAnalysis() {
    setAnalyzing(true)
    try {
      const [struct, style] = await Promise.all([
        api.triggerStructureAnalysis(bookId, bookId),
        api.triggerStyleAnalysis(bookId, bookId),
      ])
      setStructureData(struct as unknown as StructureData)
      setStyleData(style as unknown as StyleData)
      setTab('basic')
      showToast('基础分析完成', 'success')
    } catch (e) {
      showToast(`分析失败: ${e instanceof Error ? e.message : ''}`, 'error')
    }
    setAnalyzing(false)
    checkStatus()
  }

  // Load cached on tab click
  async function loadCached(type: 'deep' | 'emotion' | 'basic') {
    setTab(type)
    if (type === 'deep' && !deepData) {
      const results: Record<string, DeepStyleData> = {}
      for (const t of DEEP_TYPES) {
        try {
          const d = await api.getDeepStyle(bookId, t.key, bookId)
          results[t.key] = d as unknown as DeepStyleData
        } catch { /* not cached */ }
      }
      if (Object.keys(results).length > 0) setDeepData(results)
    }
    if (type === 'emotion' && !emotionData) {
      try {
        const d = await api.getEmotionalCurve(bookId, bookId)
        setEmotionData(d as unknown as EmotionalCurveData)
      } catch { /* not cached */ }
    }
    if (type === 'basic') {
      try {
        const [s, st] = await Promise.all([
          api.getStructureAnalysis(bookId, bookId),
          api.getStyleAnalysis(bookId, bookId),
        ])
        setStructureData(s as unknown as StructureData)
        setStyleData(st as unknown as StyleData)
      } catch { /* not cached */ }
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* ── Header ── */}
      <div className="shrink-0 px-6 py-4 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
              <Icon name="compass" size={16} className="text-violet-400" /> 文风分析
            </h2>
            <p className="text-[10px] text-zinc-500 mt-1">
              分析当前书的章节文本，提取文风特征。分析结果自动注入写作 Prompt 作为风格约束。
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={runDeepAnalysis}
            disabled={analyzing}
            className="text-xs bg-violet-900/50 hover:bg-violet-800/60 text-violet-200 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 border border-violet-700/40"
          >
            {analyzing ? <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
              : <><Icon name="compass" size={12} /> {status.deep_style ? '重新深度分析' : '深度文风分析'}</>}
          </button>
          <button
            onClick={runEmotionAnalysis}
            disabled={analyzing}
            className="text-xs bg-rose-900/40 hover:bg-rose-800/50 text-rose-200 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 border border-rose-700/40"
          >
            {analyzing ? <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
              : <><Icon name="activity" size={12} /> {status.emotional_curve ? '重新分析情感' : '情感弧线分析'}</>}
          </button>
          <button
            onClick={runBasicAnalysis}
            disabled={analyzing}
            className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {analyzing ? <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
              : <><Icon name="bar-chart" size={12} /> {status.structure ? '重新基础分析' : '基础结构分析'}</>}
          </button>
        </div>

        {/* Status badges */}
        <div className="flex gap-2 mt-2 text-[10px]">
          {status.deep_style && <span className="text-violet-400">深度文风已分析</span>}
          {status.emotional_curve && <span className="text-rose-400">情感弧线已分析</span>}
          {status.structure && <span className="text-emerald-500">基础结构已分析</span>}
          {status.style && <span className="text-emerald-500">文风指纹已量化</span>}
        </div>
      </div>

      {/* ── Tab bar ── */}
      <div className="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-zinc-800/60 bg-zinc-950/40">
        {([
          { key: 'deep' as const, label: '深度文风', icon: 'compass' },
          { key: 'emotion' as const, label: '情感弧线', icon: 'activity' },
          { key: 'basic' as const, label: '基础结构', icon: 'bar-chart' },
        ]).map(t => (
          <button
            key={t.key}
            onClick={() => loadCached(t.key)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-all flex items-center gap-1.5 ${
              tab === t.key
                ? 'bg-zinc-800/80 text-zinc-100 border border-zinc-700'
                : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
            }`}
          >
            <Icon name={t.icon} size={12} /> {t.label}
          </button>
        ))}
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {tab === 'deep' && deepData && <DeepStyleView data={deepData} />}
        {tab === 'deep' && !deepData && !analyzing && <EmptyHint text="点击上方「深度文风分析」按钮，分析句式韵律、修辞密度、谶语特征、叙事视角四个维度。" />}

        {tab === 'emotion' && emotionData && <EmotionalCurveView data={emotionData} />}
        {tab === 'emotion' && !emotionData && !analyzing && <EmptyHint text="点击上方「情感弧线分析」按钮，生成逐章情感基调曲线。" />}

        {tab === 'basic' && (structureData || styleData) && (
          <>
            {structureData && <BasicStructureView data={structureData} />}
            {styleData && <BasicStyleView data={styleData} />}
          </>
        )}
        {tab === 'basic' && !structureData && !styleData && !analyzing && <EmptyHint text="点击上方「基础结构分析」按钮，统计章节篇幅、对话比、句长分布等。" />}

        {analyzing && (
          <div className="flex items-center justify-center py-16 text-zinc-600 text-sm">
            <div className="w-5 h-5 border-2 border-zinc-700 border-t-violet-400 rounded-full animate-spin mr-2" />
            正在分析章节文本，请稍候...
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ──

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-zinc-600">
      <Icon name="compass" size={28} className="mb-3 text-zinc-700" />
      <p className="text-xs text-center max-w-xs">{text}</p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg px-3 py-2">
      <p className="text-[10px] text-zinc-500 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-zinc-200">{value}</p>
    </div>
  )
}

// ── Deep Style Radar ──

const RADAR_DIMENSIONS = [
  { key: 'sentence_rhythm', label: '句式韵律', fields: ['parallel_ratio', 'four_six_prose_density', 'classical_marker_density', 'long_short_alternation', 'inversion_frequency'] },
  { key: 'rhetoric_density', label: '修辞密度', fields: ['metaphor_density', 'personification_density', 'antithesis_density', 'allusion_density'] },
  { key: 'prophecy_signature', label: '谶语特征', fields: ['prophecy_frequency', 'foreshadowing_density', 'omen_density'] },
  { key: 'narrative_pov', label: '叙事视角', fields: ['first_person_ratio', 'third_person_ratio', 'omniscient_ratio', 'pov_shift_frequency'] },
]

function DeepStyleView({ data }: { data: Record<string, DeepStyleData> }) {
  const scores = RADAR_DIMENSIONS.map(dim => {
    const d = data[dim.key]
    if (!d) return { ...dim, score: 0, raw: {} as DeepStyleData }
    const vals = dim.fields.map(f => Number(d[f as keyof DeepStyleData] ?? 0))
    const avg = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    const score = Math.min(1, avg * 20)
    return { ...dim, score, raw: d }
  })

  const cx = 120, cy = 120, r = 90
  const angleStep = (Math.PI * 2) / scores.length
  const polar = (angle: number, radius: number) => ({
    x: cx + radius * Math.cos(angle - Math.PI / 2),
    y: cy + radius * Math.sin(angle - Math.PI / 2),
  })

  const gridLevels = [0.25, 0.5, 0.75, 1.0]
  const dataPoints = scores.map((s, i) => polar(i * angleStep, r * s.score))
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'

  return (
    <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="compass" size={14} className="text-violet-400" /> 深度文风指纹
      </h4>

      <div className="flex items-start gap-6">
        <svg width="100%" viewBox="0 0 240 240" preserveAspectRatio="xMidYMid meet" className="shrink-0 max-w-[240px]">
          {gridLevels.map(level => {
            const pts = scores.map((_, i) => polar(i * angleStep, r * level))
            const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
            return <path key={level} d={path} fill="none" stroke="#27272a" strokeWidth={0.5} />
          })}
          {scores.map((_, i) => {
            const end = polar(i * angleStep, r)
            return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#3f3f46" strokeWidth={0.5} />
          })}
          <path d={dataPath} fill="rgba(139,92,246,0.15)" stroke="#8b5cf6" strokeWidth={1.5} />
          {dataPoints.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={3} fill="#a78bfa" />
          ))}
          {scores.map((s, i) => {
            const lp = polar(i * angleStep, r + 18)
            return (
              <text key={i} x={lp.x} y={lp.y} textAnchor="middle" dominantBaseline="middle"
                className="text-[10px] fill-zinc-400 font-medium">{s.label}</text>
            )
          })}
        </svg>

        <div className="flex-1 space-y-3 min-w-0">
          {scores.map(s => {
            const d = s.raw
            if (!d || !d.book_id) return null
            return (
              <div key={s.key}>
                <div className="text-[10px] text-zinc-500 mb-1">{s.label}</div>
                <div className="space-y-1">
                  {s.fields.map(f => {
                    const val = Number(d[f as keyof DeepStyleData] ?? 0)
                    return (
                      <div key={f} className="flex items-center gap-2">
                        <span className="text-[9px] text-zinc-600 w-20 shrink-0 truncate">{FIELD_LABELS[f] || f}</span>
                        <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-violet-500/60 rounded-full" style={{ width: `${Math.min(100, val * 2000)}%` }} />
                        </div>
                        <span className="text-[9px] text-zinc-500 w-12 text-right font-mono">{val.toFixed(4)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <p className="text-[9px] text-zinc-600 mt-3">
        雷达图面积越大表示该维度特征越显著。续写时会自动注入这些特征作为风格约束。
      </p>
    </div>
  )
}

// ── Emotional Curve ──

function EmotionalCurveView({ data }: { data: EmotionalCurveData }) {
  const seq = data.chapter_tone_sequence || []
  if (seq.length === 0) return <EmptyHint text="章节数据不足，无法生成情感弧线。" />

  const w = 400, h = 120, pad = { top: 10, right: 10, bottom: 20, left: 30 }
  const plotW = w - pad.left - pad.right
  const plotH = h - pad.top - pad.bottom
  const minVal = Math.min(...seq.map(s => s.valence), -0.5)
  const maxVal = Math.max(...seq.map(s => s.valence), 0.5)
  const range = maxVal - minVal || 1
  const xScale = (i: number) => pad.left + (i / Math.max(seq.length - 1, 1)) * plotW
  const yScale = (v: number) => pad.top + plotH - ((v - minVal) / range) * plotH
  const pathD = seq.map((s, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(s.valence)}`).join(' ')
  const zeroY = yScale(0)

  return (
    <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="activity" size={14} className="text-rose-400" /> 情感弧线
      </h4>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <Metric label="主基调" value={TONE_LABELS[data.dominant_tone] || data.dominant_tone} />
        <Metric label="乐极生悲比" value={data.joy_to_sorrow_ratio.toFixed(2)} />
        <Metric label="情绪波动度" value={data.emotional_volatility.toFixed(3)} />
      </div>

      <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" className="mb-2">
        <line x1={pad.left} y1={zeroY} x2={w - pad.right} y2={zeroY} stroke="#3f3f46" strokeWidth={0.5} strokeDasharray="4,2" />
        <text x={pad.left - 4} y={zeroY} textAnchor="end" dominantBaseline="middle" className="text-[8px] fill-zinc-600">0</text>
        <text x={pad.left - 4} y={pad.top + 4} textAnchor="end" className="text-[8px] fill-zinc-600">+</text>
        <text x={pad.left - 4} y={h - pad.bottom} textAnchor="end" className="text-[8px] fill-zinc-600">-</text>
        <path d={pathD} fill="none" stroke="#f43f5e" strokeWidth={1.5} />
        {seq.map((s, i) => (
          <g key={i}>
            <circle cx={xScale(i)} cy={yScale(s.valence)} r={2.5} fill={TONE_COLORS[s.tone] || '#6b7280'} />
            {seq.length <= 20 && (
              <text x={xScale(i)} y={h - 2} textAnchor="middle" className="text-[7px] fill-zinc-600">{i + 1}</text>
            )}
          </g>
        ))}
      </svg>

      <div className="flex flex-wrap gap-2 mt-1">
        {Object.entries(TONE_LABELS).map(([key, label]) => (
          <span key={key} className="text-[9px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: TONE_COLORS[key] }} />
            <span className="text-zinc-500">{label}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Basic Structure ──

function BasicStructureView({ data }: { data: StructureData }) {
  const maxLen = Math.max(...(data.chapter_length_distribution || [1]), 1)
  const maxPace = Math.max(...(data.pacing_curve?.map(x => x.pace_score) || [0.01]), 0.01)

  return (
    <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="bar-chart" size={14} /> 结构分析
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Metric label="章节数" value={String(data.chapter_count)} />
        <Metric label="总字数" value={data.total_words.toLocaleString()} />
        <Metric label="平均章节字数" value={data.avg_chapter_length.toFixed(0)} />
        <Metric label="平均对话占比" value={`${(data.avg_dialogue_ratio * 100).toFixed(1)}%`} />
      </div>

      {data.chapter_length_distribution?.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] text-zinc-500 mb-1.5">逐章字数分布</p>
          <div className="flex items-end gap-0.5 h-20">
            {data.chapter_length_distribution.map((len, i) => (
              <div key={i} className="flex-1 bg-gradient-to-t from-cyan-600 to-blue-400 rounded-sm min-w-[2px]"
                style={{ height: `${(len / maxLen) * 100}%` }} title={`第${i + 1}章: ${len}字`} />
            ))}
          </div>
        </div>
      )}

      {data.pacing_curve && data.pacing_curve.length > 0 && (
        <div>
          <p className="text-[10px] text-zinc-500 mb-1.5">节奏曲线</p>
          <div className="flex items-end gap-0.5 h-12">
            {data.pacing_curve.map((p, i) => (
              <div key={i} className="flex-1 bg-gradient-to-t from-amber-600 to-yellow-400 rounded-sm min-w-[2px]"
                style={{ height: `${(p.pace_score / maxPace) * 100}%` }} title={`第${p.chapter}章: pace=${p.pace_score}`} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Basic Style ──

function BasicStyleView({ data }: { data: StyleData }) {
  const dist = data.sentence_length_distribution || {}
  const buckets = [
    { label: '<10字', key: '<10', color: 'bg-emerald-500' },
    { label: '10-20字', key: '10-20', color: 'bg-cyan-500' },
    { label: '20-40字', key: '20-40', color: 'bg-amber-500' },
    { label: '>40字', key: '>40', color: 'bg-rose-500' },
  ]
  const punctEntries = Object.entries(data.punctuation_pattern || {}).sort((a, b) => b[1] - a[1]).slice(0, 5)

  return (
    <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="pen-tool" size={14} /> 文风量化指纹
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Metric label="词汇丰富度 (TTR)" value={data.vocabulary_richness_ttr.toFixed(3)} />
        <Metric label="四字成语密度" value={data.four_char_idiom_density.toFixed(4)} />
        <Metric label="对话密度" value={`${(data.dialogue_density * 100).toFixed(1)}%`} />
      </div>

      {Object.keys(dist).length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] text-zinc-500 mb-1.5">句长分布</p>
          <div className="space-y-1">
            {buckets.map(b => {
              const val = dist[b.key] || 0
              return (
                <div key={b.key} className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-500 w-14 shrink-0">{b.label}</span>
                  <div className="flex-1 h-3 bg-zinc-800 rounded-sm overflow-hidden">
                    <div className={`h-full ${b.color} rounded-sm`} style={{ width: `${val * 100}%` }} />
                  </div>
                  <span className="text-[10px] text-zinc-400 w-10 text-right">{(val * 100).toFixed(0)}%</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {punctEntries.length > 0 && (
        <div>
          <p className="text-[10px] text-zinc-500 mb-1.5">标点模式 (Top 5)</p>
          <div className="flex flex-wrap gap-2">
            {punctEntries.map(([punct, freq]) => (
              <span key={punct} className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
                {punct}: {(freq * 100).toFixed(2)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
