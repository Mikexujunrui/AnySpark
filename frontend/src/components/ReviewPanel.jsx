import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon.jsx'
import LoadingState from './ui/Skeleton.jsx'
import { useRefreshKey } from '../store.js'

const AVATAR_MAP = {
  film: 'film', pen: 'pen-tool', magnifier: 'search', fire: 'zap',
  heart: 'heart', shield: 'shield', skull: 'skull', coffee: 'coffee',
  book: 'book-open', user: 'users',
}

const CAT_LABEL = { professional: '专业', reader: '读者' }

function ReviewerCard({ reviewer, onToggle, onSelect, selected }) {
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
          <div className="text-[10px] text-zinc-500">{catLabel}{reviewer.custom ? ' · 自定义' : ''}</div>
        </div>
        <button onClick={e => { e.stopPropagation(); onToggle(reviewer.id, !reviewer.active) }}
          className={`w-8 h-4 rounded-full transition-colors ${reviewer.active ? 'bg-cyan-600' : 'bg-zinc-700'}`}>
          <div className={`w-3 h-3 bg-white rounded-full transition-transform ${reviewer.active ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      </div>
      <p className="text-xs text-zinc-400 line-clamp-2">{reviewer.persona}</p>
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

function ReviewReport({ report, onClose }) {
  const [expandedReviewer, setExpandedReviewer] = useState(null)
  if (!report) return null

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">评审报告 — {report.chapter_ref || '章节'}</h3>
        {onClose && <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">✕</button>}
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="text-3xl font-bold text-cyan-400">{report.overall_score}/10</div>
        <div className="text-xs text-zinc-500">{report.reviewer_count} 位评审员 · {report.timestamp?.slice(0, 16)}</div>
      </div>

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
                    <span className="text-sm font-semibold text-cyan-400">{rev.overall_score}/10</span>
                  )}
                  <span className="text-zinc-600 text-xs">{isExpanded ? '▲' : '▼'}</span>
                </div>
                {isExpanded && !rev.error && (
                  <div className="px-4 py-3 bg-zinc-950/50 border-t border-zinc-800">
                    {rev.scores && Object.keys(rev.scores).length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {Object.entries(rev.scores).map(([k, v]) => (
                          <span key={k} className="text-[10px] bg-zinc-800 px-2 py-0.5 rounded">
                            {k}: <span className="text-cyan-400">{v}</span>
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
    </div>
  )
}

function AddCustomModal({ onAdd, onClose }) {
  const [name, setName] = useState('')
  const [persona, setPersona] = useState('')
  const [category, setCategory] = useState('reader')

  function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || !persona.trim()) return
    onAdd({ name: name.trim(), persona: persona.trim(), category })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <form onClick={e => e.stopPropagation()} onSubmit={handleSubmit}
        className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold mb-4">添加自定义评审员</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-zinc-400 block mb-1">名称</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="如：文青读者"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-600" />
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">分类</label>
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none">
              <option value="reader">读者</option>
              <option value="professional">专业</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400 block mb-1">人设描述</label>
            <textarea value={persona} onChange={e => setPersona(e.target.value)} rows={5}
              placeholder="描述这个评审员的阅读偏好、关注点、评审风格..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-600 resize-none" />
          </div>
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200">取消</button>
          <button type="submit" disabled={!name.trim() || !persona.trim()}
            className="px-4 py-2 text-sm bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg disabled:opacity-40">添加</button>
        </div>
      </form>
    </div>
  )
}

export default function ReviewPanel({ bookId }) {
  const refreshKey = useRefreshKey()
  const [reviewers, setReviewers] = useState([])
  const [reviews, setReviews] = useState([])
  const [selectedReviewer, setSelectedReviewer] = useState(null)
  const [selectedReview, setSelectedReview] = useState(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [rRes, hRes] = await Promise.all([
        fetch(`/api/books/${bookId}/reviewers`),
        fetch(`/api/books/${bookId}/reviews`),
      ])
      setReviewers(await rRes.json())
      setReviews(await hRes.json())
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadData() }, [loadData, refreshKey])

  async function handleToggle(reviewerId, active) {
    await fetch(`/api/books/${bookId}/reviewers/${reviewerId}`, {
      method: 'PATCH',
      headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    })
    setReviewers(prev => prev.map(r => r.id === reviewerId ? { ...r, active } : r))
  }

  async function handleAddCustom(data) {
    const res = await fetch(`/api/books/${bookId}/reviewers/custom`, {
      method: 'POST',
      headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    const newR = await res.json()
    setReviewers(prev => [...prev, newR])
  }

  async function handleDeleteCustom(rid) {
    await fetch(`/api/books/${bookId}/reviewers/custom/${rid}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    setReviewers(prev => prev.filter(r => r.id !== rid))
  }

  async function handleViewReview(reviewId) {
    try {
      const res = await fetch(`/api/books/${bookId}/reviews/${reviewId}`)
      setSelectedReview(await res.json())
    } catch (e) {
      console.error(e)
    }
  }

  async function handleDeleteReview(reviewId) {
    await fetch(`/api/books/${bookId}/reviews/${reviewId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    setReviews(prev => prev.filter(r => r.id !== reviewId))
    if (selectedReview?.id === reviewId) setSelectedReview(null)
  }

  if (loading) {
    return <LoadingState text="加载评审团..." />
  }

  const selectedR = selectedReviewer ? reviewers.find(r => r.id === selectedReviewer) : null
  const activeCount = reviewers.filter(r => r.active).length

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Reviewer Cards */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">评审团成员 ({activeCount}/{reviewers.length} 激活)</h2>
            <button onClick={() => setShowAddModal(true)}
              className="text-xs bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded-lg">+ 自定义</button>
          </div>

          {/* Professional */}
          {reviewers.filter(r => r.category === 'professional').length > 0 && (
            <div className="mb-4">
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">专业审稿人</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {reviewers.filter(r => r.category === 'professional').map(r => (
                  <ReviewerCard key={r.id} reviewer={r} onToggle={handleToggle}
                    onSelect={setSelectedReviewer} selected={selectedReviewer === r.id} />
                ))}
              </div>
            </div>
          )}

          {/* Readers */}
          {reviewers.filter(r => r.category === 'reader').length > 0 && (
            <div>
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">读者代言人</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {reviewers.filter(r => r.category === 'reader').map(r => (
                  <ReviewerCard key={r.id} reviewer={r} onToggle={handleToggle}
                    onSelect={setSelectedReviewer} selected={selectedReviewer === r.id} />
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
                {selectedR.custom && (
                  <button onClick={() => { handleDeleteCustom(selectedR.id); setSelectedReviewer(null) }}
                    className="text-xs text-zinc-600 hover:text-red-400 ml-2">删除</button>
                )}
              </div>
              <button onClick={() => setSelectedReviewer(null)} className="text-zinc-500 hover:text-zinc-300 text-sm">✕</button>
            </div>
            <p className="text-sm text-zinc-300 whitespace-pre-line leading-relaxed">{selectedR.persona}</p>
            {selectedR.scoring_dimensions?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {selectedR.scoring_dimensions.map((d, i) => (
                  <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">
                    {d.name} ({(d.weight * 100).toFixed(0)}%)
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
              {reviews.slice().reverse().map(r => (
                <div key={r.id}>
                  <div className={`flex items-center gap-3 bg-zinc-900 border rounded-lg px-4 py-2.5 hover:border-zinc-600 cursor-pointer ${
                    selectedReview?.id === r.id ? 'border-cyan-600' : 'border-zinc-800'
                  }`}
                    onClick={() => selectedReview?.id === r.id ? setSelectedReview(null) : handleViewReview(r.id)}>
                    <div className="text-lg font-bold text-cyan-400 w-12">{r.overall_score}/10</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{r.chapter_ref || '章节'} — {r.summary?.slice(0, 60) || '...'}</div>
                      <div className="text-[10px] text-zinc-500">{r.timestamp?.slice(0, 16)} · {r.reviewer_count} 位评审</div>
                    </div>
                    <button onClick={e => { e.stopPropagation(); handleDeleteReview(r.id) }}
                      className="text-zinc-600 hover:text-red-400 text-xs"><Icon name="trash" size={12} /></button>
                  </div>
                  {selectedReview?.id === r.id && (
                    <div className="mt-2">
                      <ReviewReport report={selectedReview} onClose={() => setSelectedReview(null)} />
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
            <p className="text-sm mb-2">在对话中发送"让评审团看看 #1"即可启动评审</p>
            <p className="text-xs">评审团会从多个角度评审你的章节，给出综合报告和每位评审员的详细反馈</p>
          </div>
        )}
      </div>

      {showAddModal && <AddCustomModal onAdd={handleAddCustom} onClose={() => setShowAddModal(false)} />}
    </div>
  )
}
