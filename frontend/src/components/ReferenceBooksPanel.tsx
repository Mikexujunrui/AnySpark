import { useState, useEffect, useCallback } from 'react'
import { api, type StructureReportData, type StyleFingerprintData } from '../api'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import Modal from './ui/Modal'
import { showToast } from './ui/toast-utils'

interface RefBook {
  id: string
  title: string
  entityCount?: number
  chapterCount?: number
}

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

export default function ReferenceBooksPanel({ bookId }: { bookId: string }) {
  const [references, setReferences] = useState<RefBook[]>([])
  const [allBooks, setAllBooks] = useState<RefBook[]>([])
  const [loading, setLoading] = useState(true)
  const [showPicker, setShowPicker] = useState(false)
  const [analyzingRef, setAnalyzingRef] = useState<string | null>(null)
  const [analysisType, setAnalysisType] = useState<'structure' | 'style' | null>(null)
  const [structureData, setStructureData] = useState<StructureReportData | null>(null)
  const [styleData, setStyleData] = useState<StyleFingerprintData | null>(null)
  const [expandedRef, setExpandedRef] = useState<string | null>(null)
  const [analysisStatus, setAnalysisStatus] = useState<Record<string, { structure?: boolean; style?: boolean; deep_style?: boolean; emotional_curve?: boolean }>>({})
  const [deepStyleData, setDeepStyleData] = useState<Record<string, DeepStyleData> | null>(null)
  const [emotionalCurveData, setEmotionalCurveData] = useState<EmotionalCurveData | null>(null)
  const [analyzingDeep, setAnalyzingDeep] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [refRes, booksData] = await Promise.all([
        fetch(`/api/books/${bookId}/references`),
        api.getBooks(),
      ])
      const refData = await refRes.json()
      const refIds = refData.reference_book_ids || []
      const refBooks = refData.references || []
      setReferences(refBooks)
      setAllBooks((Array.isArray(booksData) ? booksData : []).filter(
        (b: RefBook) => b.id !== bookId && !refIds.includes(b.id)
      ))
      try {
        const analysesRes = await api.listAnalyses(bookId)
        const statusMap: Record<string, { structure?: boolean; style?: boolean; deep_style?: boolean; emotional_curve?: boolean }> = {}
        for (const a of analysesRes.analyses) {
          statusMap[a.ref_book_id] = {
            structure: !!a.structure,
            style: !!a.style_fingerprint,
            deep_style: !!a.deep_style,
            emotional_curve: !!a.emotional_curve,
          }
        }
        setAnalysisStatus(statusMap)
      } catch { /* analyses endpoint may not be ready yet */ }
    } catch {
      showToast('加载参考书失败', 'error')
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadData() }, [loadData])

  async function addReference(refBookId: string) {
    const refIds = references.map(r => r.id).concat(refBookId)
    try {
      await api.setReferences(bookId, refIds)
      setShowPicker(false)
      loadData()
      showToast('参考书已添加', 'success')
    } catch {
      showToast('添加失败', 'error')
    }
  }

  async function removeReference(refBookId: string) {
    const refIds = references.filter(r => r.id !== refBookId).map(r => r.id)
    try {
      await api.setReferences(bookId, refIds)
      if (expandedRef === refBookId) setExpandedRef(null)
      loadData()
      showToast('已移除', 'success')
    } catch {
      showToast('移除失败', 'error')
    }
  }

  async function runAnalysis(refBookId: string, type: 'structure' | 'style') {
    setAnalyzingRef(refBookId)
    setAnalysisType(type)
    setStructureData(null)
    setStyleData(null)
    try {
      if (type === 'structure') {
        const result = await api.triggerStructureAnalysis(bookId, refBookId)
        setStructureData(result)
      } else {
        const result = await api.triggerStyleAnalysis(bookId, refBookId)
        setStyleData(result)
      }
      const analysesRes = await api.listAnalyses(bookId)
      const statusMap: Record<string, { structure?: boolean; style?: boolean; deep_style?: boolean; emotional_curve?: boolean }> = {}
      for (const a of analysesRes.analyses) {
        statusMap[a.ref_book_id] = {
          structure: !!a.structure,
          style: !!a.style_fingerprint,
          deep_style: !!a.deep_style,
          emotional_curve: !!a.emotional_curve,
        }
      }
      setAnalysisStatus(statusMap)
      showToast('分析完成', 'success')
    } catch (e) {
      showToast(`分析失败: ${e instanceof Error ? e.message : '未知错误'}`, 'error')
    }
    setAnalyzingRef(null)
    setAnalysisType(null)
  }

  async function runDeepStyleAnalysis(refBookId: string) {
    setAnalyzingDeep(refBookId)
    setDeepStyleData(null)
    const types = ['sentence_rhythm', 'rhetoric_density', 'prophecy_signature', 'narrative_pov']
    const results: Record<string, DeepStyleData> = {}
    try {
      for (const t of types) {
        const data = await api.triggerDeepStyle(bookId, t, refBookId)
        results[t] = data as unknown as DeepStyleData
      }
      setDeepStyleData(results)
      const analysesRes = await api.listAnalyses(bookId)
      const statusMap: Record<string, { structure?: boolean; style?: boolean; deep_style?: boolean; emotional_curve?: boolean }> = {}
      for (const a of analysesRes.analyses) {
        statusMap[a.ref_book_id] = {
          structure: !!a.structure,
          style: !!a.style_fingerprint,
          deep_style: !!a.deep_style,
          emotional_curve: !!a.emotional_curve,
        }
      }
      setAnalysisStatus(statusMap)
      showToast('深度文风分析完成', 'success')
    } catch (e) {
      showToast(`深度分析失败: ${e instanceof Error ? e.message : '未知错误'}`, 'error')
    }
    setAnalyzingDeep(null)
  }

  async function runEmotionalCurveAnalysis(refBookId: string) {
    setAnalyzingDeep(refBookId)
    setEmotionalCurveData(null)
    try {
      const data = await api.triggerEmotionalCurve(bookId, refBookId)
      setEmotionalCurveData(data as unknown as EmotionalCurveData)
      showToast('情感弧线分析完成', 'success')
    } catch (e) {
      showToast(`情感分析失败: ${e instanceof Error ? e.message : '未知错误'}`, 'error')
    }
    setAnalyzingDeep(null)
  }

  async function loadCachedAnalysis(refBookId: string, type: 'structure' | 'style') {
    try {
      if (type === 'structure') {
        const result = await api.getStructureAnalysis(bookId, refBookId)
        setStructureData(result)
        setStyleData(null)
      } else {
        const result = await api.getStyleAnalysis(bookId, refBookId)
        setStyleData(result)
        setStructureData(null)
      }
    } catch {
      setStructureData(null)
      setStyleData(null)
    }
  }

  function toggleRef(refId: string) {
    if (expandedRef === refId) {
      setExpandedRef(null)
      setStructureData(null)
      setStyleData(null)
      setDeepStyleData(null)
      setEmotionalCurveData(null)
    } else {
      setExpandedRef(refId)
      setStructureData(null)
      setStyleData(null)
      setDeepStyleData(null)
      setEmotionalCurveData(null)
      loadCachedAnalysis(refId, 'structure')
    }
  }

  if (loading) {
    return <LoadingState text="加载参考书..." />
  }

  const colors = [
    'from-rose-600 to-orange-500', 'from-violet-600 to-indigo-500',
    'from-emerald-600 to-teal-500', 'from-amber-500 to-yellow-400',
    'from-cyan-500 to-blue-500', 'from-fuchsia-600 to-pink-500',
  ]

  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Icon name="book-open" size={20} /> 参考书
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            指定其他项目为参考书，其角色/设定/关系会以只读方式注入写作上下文
          </p>
        </div>
        {allBooks.length > 0 && (
          <button onClick={() => setShowPicker(true)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-2">
            <Icon name="plus" size={14} /> 添加参考书
          </button>
        )}
      </header>

      {references.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
          <Icon name="book-open" size={36} className="mb-3 text-zinc-700" />
          <p className="text-sm mb-1">未设置参考书</p>
          <p className="text-xs mb-4">如同人小说可指定原著为参考书，写作时自动参考原著设定</p>
          {allBooks.length > 0 ? (
            <button onClick={() => setShowPicker(true)}
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-5 py-2 rounded-lg transition-colors text-sm flex items-center gap-2">
              <Icon name="plus" size={14} /> 选择参考书
            </button>
          ) : (
            <p className="text-xs text-zinc-600">当前没有其他项目可选</p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {references.map((book, i) => {
            const status = analysisStatus[book.id] || {}
            const isExpanded = expandedRef === book.id
            const isAnalyzing = analyzingRef === book.id
            return (
              <div key={book.id}
                className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors">
                <div className={`h-1 bg-gradient-to-r ${colors[i % colors.length]}`} />
                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-zinc-200">{book.title}</h3>
                      <div className="flex gap-3 text-[10px] text-zinc-500 mt-1">
                        {book.entityCount !== undefined && book.entityCount > 0 && <span>{book.entityCount} 个实体</span>}
                        {book.chapterCount !== undefined && book.chapterCount > 0 && <span>{book.chapterCount} 章</span>}
                        {status.structure && <span className="text-emerald-500">结构已分析</span>}
                        {status.style && <span className="text-emerald-500">文风已量化</span>}
                        {status.deep_style && <span className="text-violet-400">深度文风</span>}
                        {status.emotional_curve && <span className="text-rose-400">情感弧线</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleRef(book.id)}
                        className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1"
                      >
                        <Icon name={isExpanded ? 'chevron-up' : 'chevron-down'} size={12} />
                        {isExpanded ? '收起' : '分析'}
                      </button>
                      <button onClick={() => removeReference(book.id)}
                        className="text-xs text-zinc-600 hover:text-red-400 transition-colors flex items-center gap-1">
                        <Icon name="x" size={12} /> 移除
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-zinc-800 space-y-4">
                      <div className="flex gap-2 flex-wrap">
                        <button
                          onClick={() => runAnalysis(book.id, 'structure')}
                          disabled={isAnalyzing}
                          className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {isAnalyzing && analysisType === 'structure' ? (
                            <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
                          ) : (
                            <><Icon name="bar-chart" size={12} /> {status.structure ? '重新分析结构' : '分析结构'}</>
                          )}
                        </button>
                        <button
                          onClick={() => runAnalysis(book.id, 'style')}
                          disabled={isAnalyzing}
                          className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {isAnalyzing && analysisType === 'style' ? (
                            <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
                          ) : (
                            <><Icon name="palette" size={12} /> {status.style ? '重新量化文风' : '量化文风'}</>
                          )}
                        </button>
                        <button
                          onClick={() => runDeepStyleAnalysis(book.id)}
                          disabled={analyzingDeep === book.id}
                          className="text-xs bg-violet-900/50 hover:bg-violet-800/60 text-violet-200 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 border border-violet-700/40"
                        >
                          {analyzingDeep === book.id ? (
                            <><span className="animate-spin inline-block">{'\u27f3'}</span> 深度分析中...</>
                          ) : (
                            <><Icon name="compass" size={12} /> {status.deep_style ? '重新深度分析' : '深度文风分析'}</>
                          )}
                        </button>
                        <button
                          onClick={() => runEmotionalCurveAnalysis(book.id)}
                          disabled={analyzingDeep === book.id}
                          className="text-xs bg-rose-900/40 hover:bg-rose-800/50 text-rose-200 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 border border-rose-700/40"
                        >
                          {analyzingDeep === book.id ? (
                            <><span className="animate-spin inline-block">{'\u27f3'}</span> 分析中...</>
                          ) : (
                            <><Icon name="activity" size={12} /> {status.emotional_curve ? '重新分析情感' : '情感弧线分析'}</>
                          )}
                        </button>
                      </div>

                      {structureData && (
                        <StructureReportView data={structureData} />
                      )}

                      {styleData && (
                        <StyleFingerprintView data={styleData} />
                      )}

                      {deepStyleData && (
                        <DeepStyleRadarView data={deepStyleData} />
                      )}

                      {emotionalCurveData && (
                        <EmotionalCurveView data={emotionalCurveData} />
                      )}

                      {!structureData && !styleData && !deepStyleData && !emotionalCurveData && !isAnalyzing && analyzingDeep !== book.id && (
                        <p className="text-xs text-zinc-600">
                          点击上方按钮分析原著的结构和文风。分析结果会自动缓存，写作时注入为约束。
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {references.length > 0 && (
        <div className="mt-8 p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl">
          <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-2">
            <Icon name="info" size={14} /> 提示
          </h3>
          <p className="text-xs text-zinc-500 leading-relaxed">
            参考书的知识图谱（角色名、设定、关系）会自动注入写作上下文和评审团"原著党"评审中。
            分析原著结构和文风后，写作时会额外注入量化约束（章节篇幅、对话密度、句长分布等），让续写更贴近原著风格。
          </p>
        </div>
      )}

      {showPicker && (
        <Modal open onClose={() => setShowPicker(false)} title="选择参考书" size="lg">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-4">选择参考书</h2>
            {allBooks.length === 0 ? (
              <p className="text-zinc-500 text-sm">没有可选项目</p>
            ) : (
              <div className="space-y-2">
                {allBooks.map((b, i) => (
                  <div key={b.id}
                    onClick={() => addReference(b.id)}
                    className="flex items-center gap-4 p-3 rounded-lg cursor-pointer hover:bg-zinc-800 transition-colors border border-zinc-800 hover:border-zinc-600">
                    <div className={`w-8 h-8 rounded-md bg-gradient-to-br ${colors[i % colors.length]} flex items-center justify-center text-white text-xs font-bold shrink-0`}>
                      {b.title.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200 font-medium truncate">{b.title}</p>
                      <p className="text-[10px] text-zinc-500">
                        {b.entityCount || 0} 实体 · {b.chapterCount || 0} 章
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowPicker(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">取消</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function StructureReportView({ data }: { data: StructureReportData }) {
  const maxChapterLen = Math.max(...data.chapter_length_distribution, 1)
  const maxPace = Math.max(...(data.pacing_curve?.map(x => x.pace_score) || [0.01]), 0.01)
  return (
    <div className="bg-zinc-950/50 border border-zinc-800 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="bar-chart" size={14} /> 结构分析报告
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Metric label="章节数" value={String(data.chapter_count)} />
        <Metric label="总字数" value={data.total_words.toLocaleString()} />
        <Metric label="平均章节字数" value={data.avg_chapter_length.toFixed(0)} />
        <Metric label="平均对话占比" value={`${(data.avg_dialogue_ratio * 100).toFixed(1)}%`} />
        <Metric label="平均段落/章" value={data.paragraph_stats?.avg_per_chapter?.toFixed(0) || '-'} />
        <Metric label="平均句长" value={`${data.sentence_stats?.avg_length?.toFixed(0) || '-'}字`} />
      </div>

      {data?.chapter_length_distribution?.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] text-zinc-500 mb-1.5">逐章字数分布</p>
          <div className="flex items-end gap-0.5 h-20">
            {data.chapter_length_distribution.map((len, i) => (
              <div key={i}
                className="flex-1 bg-gradient-to-t from-cyan-600 to-blue-400 rounded-sm min-w-[2px]"
                style={{ height: `${(len / maxChapterLen) * 100}%` }}
                title={`第${i + 1}章: ${len}字`}
              />
            ))}
          </div>
        </div>
      )}

      {data.pacing_curve && data.pacing_curve.length > 0 && (
        <div>
          <p className="text-[10px] text-zinc-500 mb-1.5">节奏曲线</p>
          <div className="flex items-end gap-0.5 h-12">
            {data.pacing_curve.map((p, i) => (
              <div key={i}
                className="flex-1 bg-gradient-to-t from-amber-600 to-yellow-400 rounded-sm min-w-[2px]"
                style={{ height: `${(p.pace_score / maxPace) * 100}%` }}
                title={`第${p.chapter}章: pace=${p.pace_score}`}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StyleFingerprintView({ data }: { data: StyleFingerprintData }) {
  const dist = data.sentence_length_distribution || {}
  const distBuckets = [
    { label: '<10字', key: '<10', color: 'bg-emerald-500' },
    { label: '10-20字', key: '10-20', color: 'bg-cyan-500' },
    { label: '20-40字', key: '20-40', color: 'bg-amber-500' },
    { label: '>40字', key: '>40', color: 'bg-rose-500' },
  ]
  const punctEntries = Object.entries(data.punctuation_pattern || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  return (
    <div className="bg-zinc-950/50 border border-zinc-800 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="palette" size={14} /> 文风量化指纹
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Metric label="词汇丰富度 (TTR)" value={data.vocabulary_richness_ttr.toFixed(3)} />
        <Metric label="四字成语密度" value={data.four_char_idiom_density.toFixed(4)} />
        <Metric label="对话密度" value={`${(data.dialogue_density * 100).toFixed(1)}%`} />
        <Metric label="段落均值" value={`${data.paragraph_length_stats?.mean?.toFixed(0) || '-'}字`} />
      </div>

      {Object.keys(dist).length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] text-zinc-500 mb-1.5">句长分布</p>
          <div className="space-y-1">
            {distBuckets.map(b => {
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg px-3 py-2">
      <p className="text-[10px] text-zinc-500 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-zinc-200">{value}</p>
    </div>
  )
}

// ── Deep Style Radar Chart ──

const RADAR_DIMENSIONS = [
  { key: 'sentence_rhythm', label: '句式韵律', fields: ['parallel_ratio', 'four_six_prose_density', 'classical_marker_density', 'long_short_alternation', 'inversion_frequency'] },
  { key: 'rhetoric_density', label: '修辞密度', fields: ['metaphor_density', 'personification_density', 'antithesis_density', 'allusion_density'] },
  { key: 'prophecy_signature', label: '谶语特征', fields: ['prophecy_frequency', 'foreshadowing_density', 'omen_density'] },
  { key: 'narrative_pov', label: '叙事视角', fields: ['first_person_ratio', 'third_person_ratio', 'omniscient_ratio', 'pov_shift_frequency'] },
]

function DeepStyleRadarView({ data }: { data: Record<string, DeepStyleData> }) {
  // Compute normalized scores per dimension (0-1)
  const scores = RADAR_DIMENSIONS.map(dim => {
    const d = data[dim.key]
    if (!d) return { ...dim, score: 0, raw: {} }
    const vals = dim.fields.map(f => Number(d[f as keyof DeepStyleData] ?? 0))
    const avg = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    // Normalize: typical classical novel values are small, scale up for radar
    const score = Math.min(1, avg * 20) // scale factor for visual
    return { ...dim, score, raw: d }
  })

  const cx = 120, cy = 120, r = 90
  const angleStep = (Math.PI * 2) / scores.length

  function polarToCart(angle: number, radius: number) {
    return { x: cx + radius * Math.cos(angle - Math.PI / 2), y: cy + radius * Math.sin(angle - Math.PI / 2) }
  }

  const gridLevels = [0.25, 0.5, 0.75, 1.0]
  const dataPoints = scores.map((s, i) => polarToCart(i * angleStep, r * s.score))
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'

  return (
    <div className="bg-zinc-950/50 border border-zinc-800 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="compass" size={14} className="text-violet-400" /> 深度文风指纹
      </h4>

      <div className="flex items-start gap-6">
        {/* Radar SVG */}
        <svg width="100%" viewBox="0 0 240 240" preserveAspectRatio="xMidYMid meet" className="shrink-0 max-w-[240px]">
          {/* Grid circles */}
          {gridLevels.map(level => {
            const pts = scores.map((_, i) => polarToCart(i * angleStep, r * level))
            const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
            return <path key={level} d={path} fill="none" stroke="#27272a" strokeWidth={0.5} />
          })}
          {/* Axis lines */}
          {scores.map((_, i) => {
            const end = polarToCart(i * angleStep, r)
            return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#3f3f46" strokeWidth={0.5} />
          })}
          {/* Data polygon */}
          <path d={dataPath} fill="rgba(139,92,246,0.15)" stroke="#8b5cf6" strokeWidth={1.5} />
          {/* Data points */}
          {dataPoints.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={3} fill="#a78bfa" />
          ))}
          {/* Labels */}
          {scores.map((s, i) => {
            const labelPos = polarToCart(i * angleStep, r + 18)
            return (
              <text key={i} x={labelPos.x} y={labelPos.y} textAnchor="middle" dominantBaseline="middle"
                className="text-[10px] fill-zinc-400 font-medium">{s.label}</text>
            )
          })}
        </svg>

        {/* Detail metrics */}
        <div className="flex-1 space-y-3">
          {scores.map(s => {
            const d = s.raw as DeepStyleData
            if (!d) return null
            const entries = s.fields.map(f => ({
              key: f,
              label: FIELD_LABELS[f] || f,
              value: Number(d[f as keyof DeepStyleData] ?? 0),
            }))
            return (
              <div key={s.key}>
                <div className="text-[10px] text-zinc-500 mb-1">{s.label}</div>
                <div className="space-y-1">
                  {entries.map(e => (
                    <div key={e.key} className="flex items-center gap-2">
                      <span className="text-[9px] text-zinc-600 w-20 shrink-0 truncate">{e.label}</span>
                      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-violet-500/60 rounded-full" style={{ width: `${Math.min(100, e.value * 2000)}%` }} />
                      </div>
                      <span className="text-[9px] text-zinc-500 w-12 text-right font-mono">{e.value.toFixed(4)}</span>
                    </div>
                  ))}
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

// ── Emotional Curve View ──

const TONE_COLORS: Record<string, string> = {
  joy: '#f59e0b',
  calm: '#10b981',
  sorrow: '#3b82f6',
  tension: '#ef4444',
  neutral: '#6b7280',
  anger: '#dc2626',
  surprise: '#8b5cf6',
}

const TONE_LABELS: Record<string, string> = {
  joy: '喜悦', calm: '平静', sorrow: '悲伤', tension: '紧张',
  neutral: '中性', anger: '愤怒', surprise: '惊奇',
}

function EmotionalCurveView({ data }: { data: EmotionalCurveData }) {
  const seq = data.chapter_tone_sequence || []
  if (seq.length === 0) return null

  const w = 400, h = 120, pad = { top: 10, right: 10, bottom: 20, left: 30 }
  const plotW = w - pad.left - pad.right
  const plotH = h - pad.top - pad.bottom

  const minVal = Math.min(...seq.map(s => s.valence), -0.5)
  const maxVal = Math.max(...seq.map(s => s.valence), 0.5)
  const range = maxVal - minVal || 1

  const xScale = (i: number) => pad.left + (i / Math.max(seq.length - 1, 1)) * plotW
  const yScale = (v: number) => pad.top + plotH - ((v - minVal) / range) * plotH

  const pathD = seq.map((s, i) => `${i === 0 ? 'M' : 'L'}${xScale(i)},${yScale(s.valence)}`).join(' ')

  // Zero line
  const zeroY = yScale(0)

  return (
    <div className="bg-zinc-950/50 border border-zinc-800 rounded-lg p-4">
      <h4 className="text-xs font-semibold text-zinc-300 mb-3 flex items-center gap-1.5">
        <Icon name="activity" size={14} className="text-rose-400" /> 情感弧线
      </h4>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <Metric label="主基调" value={TONE_LABELS[data.dominant_tone] || data.dominant_tone} />
        <Metric label="乐极生悲比" value={data.joy_to_sorrow_ratio.toFixed(2)} />
        <Metric label="情绪波动度" value={data.emotional_volatility.toFixed(3)} />
      </div>

      <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" className="mb-2">
        {/* Zero line */}
        <line x1={pad.left} y1={zeroY} x2={w - pad.right} y2={zeroY} stroke="#3f3f46" strokeWidth={0.5} strokeDasharray="4,2" />
        <text x={pad.left - 4} y={zeroY} textAnchor="end" dominantBaseline="middle" className="text-[8px] fill-zinc-600">0</text>
        <text x={pad.left - 4} y={pad.top + 4} textAnchor="end" className="text-[8px] fill-zinc-600">+</text>
        <text x={pad.left - 4} y={h - pad.bottom} textAnchor="end" className="text-[8px] fill-zinc-600">-</text>

        {/* Curve */}
        <path d={pathD} fill="none" stroke="#f43f5e" strokeWidth={1.5} />

        {/* Data points with tone color */}
        {seq.map((s, i) => (
          <g key={i}>
            <circle cx={xScale(i)} cy={yScale(s.valence)} r={2.5}
              fill={TONE_COLORS[s.tone] || '#6b7280'} />
            {seq.length <= 20 && (
              <text x={xScale(i)} y={h - 2} textAnchor="middle" className="text-[7px] fill-zinc-600">
                {i + 1}
              </text>
            )}
          </g>
        ))}
      </svg>

      {/* Tone legend */}
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
