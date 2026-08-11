import { useState, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { useRefreshKey } from '../store'
import { showToast } from './ui/toast-utils'

const AVATAR_MAP = {
  film: 'film', pen: 'pen-tool', magnifier: 'search', fire: 'zap',
  heart: 'heart', shield: 'shield', skull: 'skull', coffee: 'coffee',
  book: 'book-open', user: 'users', '✒️': 'pen-tool', '📖': 'book-open',
}

const CAT_LABEL = { professional: '专业', reader: '读者', continuation: '续写' }

// ── 评审员卡片（只读展示：激活态来自后端 YAML 内容资产，不提供前端切换）──
function ReviewerCard({ reviewer, onSelect, selected }) {
  const avatarIcon = AVATAR_MAP[reviewer.avatar] || 'users'
  const catLabel = CAT_LABEL[reviewer.category] || reviewer.category
  return (
    <div onClick={() => onSelect(reviewer.id)}
      className={`relative rounded-xl border p-4 cursor-pointer transition-all ${
        selected ? 'border-cyan-500 bg-cyan-950/30' :
        reviewer.active ? 'border-zinc-700 bg-zinc-900 hover:border-zinc-500' : 'border-zinc-800 bg-zinc-900/50 opacity-60'
      }`}>
      <div className="flex items-center gap-3 mb-2">
        <Icon name={avatarIcon} size={24} className="text-zinc-400" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{reviewer.name}</div>
          <div className="text-[10px] text-zinc-500">{catLabel}</div>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${reviewer.active ? 'bg-emerald-900/40 text-emerald-400' : 'bg-zinc-800 text-zinc-600'}`}>
          {reviewer.active ? '激活' : '停用'}
        </span>
      </div>
      <p className="text-xs text-zinc-400 line-clamp-2">
        {reviewer.description || reviewer.persona || (reviewer.scoring_dimensions?.[0]?.desc) || '专业评审维度：' + (reviewer.scoring_dimensions || []).map((d: any) => d.name).join(' / ')}
      </p>
      {reviewer.scoring_dimensions?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {reviewer.scoring_dimensions.slice(0, 3).map((d, i) => (
            <span key={i} className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">{d.name}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── 评审报告（兼容 V4 ReviewReport 数据）──
function ReviewReport({ report, onClose }) {
  const [expandedReviewer, setExpandedReviewer] = useState(null)
  const [showMarkdown, setShowMarkdown] = useState(false)
  if (!report) return null

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">评审报告 — {report.chapter_ref || '章节'}</h3>
        {onClose && <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><Icon name="x" size={16} /></button>}
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="text-3xl font-bold text-cyan-400">
          {report.overall_score > 0 ? `${report.overall_score}/10` : '—'}
        </div>
        <div className="text-xs text-zinc-500">
          {report.reviewer_count || report.valid_count} 位评审员
          {report.timestamp?.slice(0, 16) ? ` · ${report.timestamp.slice(0, 16).replace('T', ' ')}` : ''}
        </div>
        <button onClick={() => setShowMarkdown(v => !v)}
          className="ml-auto text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded">
          {showMarkdown ? '收起原文' : 'Markdown'}
        </button>
      </div>

      {showMarkdown ? (
        <div className="prose prose-invert max-w-none text-sm text-zinc-300">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown || report.compact || ''}</ReactMarkdown>
        </div>
      ) : (
        <>
          {report.summary && <p className="text-sm text-zinc-300 mb-4 leading-relaxed">{report.summary}</p>}

          {report.consensus?.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-green-400 mb-1">共识</h4>
              {report.consensus.map((c, i) => <p key={i} className="text-xs text-zinc-400 ml-2">• {c}</p>)}
            </div>
          )}
          {report.divergences?.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-amber-400 mb-1">分歧</h4>
              {report.divergences.map((d, i) => <p key={i} className="text-xs text-zinc-400 ml-2">• {d}</p>)}
            </div>
          )}
          {report.top_suggestions?.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-semibold text-blue-400 mb-1">改进建议</h4>
              {report.top_suggestions.map((s, i) => <p key={i} className="text-xs text-zinc-400 ml-2">{i + 1}. {s}</p>)}
            </div>
          )}

          <div className="border-t border-zinc-800 pt-4">
            <h4 className="text-sm font-semibold mb-3">各评审员反馈</h4>
            <div className="space-y-2">
              {report.individual_reviews?.map((rev, i) => {
                const avatarIcon = AVATAR_MAP[rev.avatar] || 'users'
                const isExpanded = expandedReviewer === i
                return (
                  <div key={i} className="border border-zinc-800 rounded-lg overflow-hidden">
                    <div onClick={() => setExpandedReviewer(isExpanded ? null : i)}
                      className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-zinc-800/50">
                      <Icon name={avatarIcon} size={16} className="text-zinc-500" />
                      <span className="text-sm font-medium flex-1">{rev.reviewer_name}</span>
                      <span className="text-xs text-zinc-500">{CAT_LABEL[rev.category] || ''}</span>
                      {rev.error ? (
                        <span className="text-xs text-red-400">失败</span>
                      ) : (
                        <span className="text-sm font-semibold text-cyan-400">{rev.overall_score > 0 ? `${rev.overall_score}/10` : '未打分'}</span>
                      )}
                      <span className="text-zinc-600 text-xs">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                    {isExpanded && !rev.error && (
                      <div className="px-4 py-3 bg-zinc-950/50 border-t border-zinc-800">
                        {rev.scores && Object.keys(rev.scores).length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {Object.entries(rev.scores).map(([k, v]) => (
                              <span key={k} className="text-[10px] bg-zinc-800 px-2 py-0.5 rounded">
                                {k}: <span className="text-cyan-400">{typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}</span>
                              </span>
                            ))}
                          </div>
                        )}
                        {rev.highlights?.length > 0 && (
                          <div className="mb-2">
                            <span className="text-[10px] text-green-400 font-semibold">亮点</span>
                            {rev.highlights.map((h, j) => <p key={j} className="text-xs text-zinc-400 ml-2">+ {h}</p>)}
                          </div>
                        )}
                        {rev.issues?.length > 0 && (
                          <div className="mb-2">
                            <span className="text-[10px] text-red-400 font-semibold">问题</span>
                            {rev.issues.map((h, j) => <p key={j} className="text-xs text-zinc-400 ml-2">- {h}</p>)}
                          </div>
                        )}
                        {rev.suggestions?.length > 0 && (
                          <div className="mb-2">
                            <span className="text-[10px] text-blue-400 font-semibold">建议</span>
                            {rev.suggestions.map((h, j) => <p key={j} className="text-xs text-zinc-400 ml-2">→ {h}</p>)}
                          </div>
                        )}
                        {rev.comment && <p className="text-xs text-zinc-300 mt-2 italic">"{rev.comment}"</p>}
                      </div>
                    )}
                    {isExpanded && rev.error && (
                      <div className="px-4 py-2 bg-zinc-950/50 border-t border-zinc-800">
                        <p className="text-xs text-red-400">{rev.error}</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

const HISTORY_KEY = 'v4_review_history'

export default function ReviewPanel({ bookId }) {
  const refreshKey = useRefreshKey()
  const [reviewers, setReviewers] = useState([])
  const [chapters, setChapters] = useState([])
  const [selectedReviewer, setSelectedReviewer] = useState(null)
  const [selectedChapterId, setSelectedChapterId] = useState('')
  const [running, setRunning] = useState(false)
  const [reviews, setReviews] = useState([])
  const [selectedReview, setSelectedReview] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [rRes, cRes] = await Promise.all([
        fetch('/api/review/reviewers'),
        fetch(`/api/chapters?book_id=${bookId || 'main'}`),
      ])
      setReviewers(await rRes.json())
      const chs = await cRes.json()
      setChapters(Array.isArray(chs) ? chs : [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadData() }, [loadData, refreshKey])

  // 本地评审历史（V4 无评审存储端点 → sessionStorage 缓存本次会话）
  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || '[]')
      setReviews(Array.isArray(saved) ? saved : [])
    } catch { /* 忽略损坏缓存 */ }
  }, [])

  const persistReviews = useCallback((next: unknown[]) => {
    setReviews(next)
    try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(next)) } catch { /* 忽略 */ }
  }, [])

  async function handleRunReview() {
    if (!selectedChapterId && !selectedReviewer) {
      showToast('请先选择章节（或评审员后直接发起）', 'error')
      return
    }
    const chapter = chapters.find(c => c.id === selectedChapterId || c.title === selectedChapterId)
    setRunning(true)
    try {
      const body: Record<string, unknown> = {
        book_id: bookId || 'main',
        with_check: true,
        with_foreshadow: true,
      }
      if (chapter) {
        body.chapter_ref = chapter.title
      } else if (selectedChapterId) {
        body.chapter_ref = selectedChapterId
      }
      if (selectedReviewer) {
        body.reviewer_ids = [selectedReviewer]
      }
      const res = await fetch('/api/review/panel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.text().catch(() => '')
        throw new Error(err || `HTTP ${res.status}`)
      }
      const report = await res.json()
      const withRef = { ...report, chapter_ref: report.chapter_ref || chapter?.title || '当前章节', timestamp: report.timestamp || new Date().toISOString() }
      persistReviews([withRef, ...reviews])
      setSelectedReview(withRef)
      showToast('评审完成', 'success')
    } catch (e) {
      console.error(e)
      showToast(`评审失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
    setRunning(false)
  }

  const selectedR = selectedReviewer ? reviewers.find(r => r.id === selectedReviewer) : null
  const activeCount = reviewers.filter(r => r.active).length

  if (loading) {
    return <LoadingState text="加载评审团..." />
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 发起评审 */}
        <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4">
          <h2 className="text-sm font-semibold mb-3">发起评审</h2>
          <div className="flex items-center gap-2 mb-2">
            <select
              value={selectedChapterId}
              onChange={e => setSelectedChapterId(e.target.value)}
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
            >
              <option value="">选择章节…</option>
              {chapters.map(c => (
                <option key={c.id} value={c.id}>{c.title}</option>
              ))}
            </select>
            <button
              onClick={handleRunReview}
              disabled={!selectedChapterId || running}
              className="px-4 py-2 text-sm bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg shrink-0"
            >
              {running ? '评审中…' : '开始评审'}
            </button>
          </div>
          <p className="text-[11px] text-zinc-600">
            拟人化评审团：文学编辑/结构审校/伏笔审计等多视角并发评审 + 主席汇总裁决（含硬伤检查与关键点图谱上下文）。
          </p>
        </div>

        {/* Reviewer Cards */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">评审团成员 ({activeCount}/{reviewers.length} 激活)</h2>
            {selectedR && (
              <button onClick={() => setSelectedReviewer(null)} className="text-xs text-zinc-500 hover:text-zinc-300">清除选择</button>
            )}
          </div>

          {reviewers.filter(r => r.category === 'professional').length > 0 && (
            <div className="mb-4">
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">专业审稿人</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {reviewers.filter(r => r.category === 'professional').map(r => (
                  <ReviewerCard key={r.id} reviewer={r} onSelect={setSelectedReviewer} selected={selectedReviewer === r.id} />
                ))}
              </div>
            </div>
          )}

          {reviewers.filter(r => r.category === 'reader').length > 0 && (
            <div className="mb-4">
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">读者代言人</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {reviewers.filter(r => r.category === 'reader').map(r => (
                  <ReviewerCard key={r.id} reviewer={r} onSelect={setSelectedReviewer} selected={selectedReviewer === r.id} />
                ))}
              </div>
            </div>
          )}

          {reviewers.filter(r => r.category === 'continuation').length > 0 && (
            <div>
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">续写专项</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {reviewers.filter(r => r.category === 'continuation').map(r => (
                  <ReviewerCard key={r.id} reviewer={r} onSelect={setSelectedReviewer} selected={selectedReviewer === r.id} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Selected Reviewer Detail */}
        {selectedR && (
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Icon name={AVATAR_MAP[selectedR.avatar] || 'users'} size={20} className="text-zinc-400" />
                <h3 className="font-semibold">{selectedR.name}</h3>
              </div>
              <button onClick={() => setSelectedReviewer(null)} className="text-zinc-500 hover:text-zinc-300 text-sm"><Icon name="x" size={14} /></button>
            </div>
            <p className="text-sm text-zinc-300 whitespace-pre-line leading-relaxed">{selectedR.description || selectedR.persona || (selectedR.scoring_dimensions || []).map((d: any) => `${d.name}：${d.desc || ''}`).join('\n')}</p>
            {selectedR.scoring_dimensions?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {selectedR.scoring_dimensions.map((d, i) => (
                  <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">
                    {d.name} {d.weight ? `(${Math.round(d.weight * 100)}%)` : ''}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Review History */}
        {reviews.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold mb-3">评审历史 ({reviews.length})</h2>
            <div className="space-y-2">
              {reviews.slice().reverse().map((r, idx) => (
                <div key={idx}>
                  <div className={`flex items-center gap-3 bg-zinc-900 border rounded-lg px-4 py-2.5 hover:border-zinc-600 cursor-pointer ${
                    selectedReview === r ? 'border-cyan-600' : 'border-zinc-800'
                  }`}
                    onClick={() => selectedReview === r ? setSelectedReview(null) : setSelectedReview(r)}>
                    <div className="text-lg font-bold text-cyan-400 w-12">{r.overall_score > 0 ? `${r.overall_score}/10` : '—'}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{r.chapter_ref || '章节'} — {r.summary?.slice(0, 60) || '...'}</div>
                      <div className="text-[10px] text-zinc-500">{r.timestamp?.slice(0, 16).replace('T', ' ') || ''} · {r.valid_count || r.reviewer_count || 0} 位评审</div>
                    </div>
                  </div>
                  {selectedReview === r && (
                    <div className="mt-2">
                      <ReviewReport report={r} onClose={() => setSelectedReview(null)} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Usage Hint */}
        {reviews.length === 0 && (
          <div className="text-center text-zinc-600 py-8">
            <p className="text-sm mb-2">选一个章节，点击「开始评审」</p>
            <p className="text-xs">评审团会从文学编辑/结构审校/伏笔审计等视角并发评审，输出综合报告和每位评审员的详细反馈</p>
          </div>
        )}
      </div>
    </div>
  )
}
