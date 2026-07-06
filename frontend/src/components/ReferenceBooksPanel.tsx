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
  const [analysisStatus, setAnalysisStatus] = useState<Record<string, { structure?: boolean; style?: boolean }>>({})

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
        const statusMap: Record<string, { structure?: boolean; style?: boolean }> = {}
        for (const a of analysesRes.analyses) {
          statusMap[a.ref_book_id] = {
            structure: !!a.structure,
            style: !!a.style_fingerprint,
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
      const statusMap: Record<string, { structure?: boolean; style?: boolean }> = {}
      for (const a of analysesRes.analyses) {
        statusMap[a.ref_book_id] = {
          structure: !!a.structure,
          style: !!a.style_fingerprint,
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
    } else {
      setExpandedRef(refId)
      setStructureData(null)
      setStyleData(null)
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
                        {status.style && <span className="text-emerald-500">文风已分析</span>}
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
                      <div className="flex gap-2">
                        <button
                          onClick={() => runAnalysis(book.id, 'structure')}
                          disabled={isAnalyzing}
                          className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {isAnalyzing && analysisType === 'structure' ? (
                            <><span className="animate-spin inline-block">{'\\u27f3'}</span> 分析中...</>
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
                            <><span className="animate-spin inline-block">{'\\u27f3'}</span> 分析中...</>
                          ) : (
                            <><Icon name="palette" size={12} /> {status.style ? '重新量化文风' : '量化文风'}</>
                          )}
                        </button>
                      </div>

                      {structureData && (
                        <StructureReportView data={structureData} />
                      )}

                      {styleData && (
                        <StyleFingerprintView data={styleData} />
                      )}

                      {!structureData && !styleData && !isAnalyzing && (
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

      {data.chapter_length_distribution.length > 0 && (
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
