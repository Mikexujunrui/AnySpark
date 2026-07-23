import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import LoadingState from './ui/Skeleton'
import EmptyState from './ui/EmptyState'
import { useRefreshKey, triggerRefresh } from '../store'

export default function ForeshadowBoard({ bookId }) {
  const refreshKey = useRefreshKey()
  const [foreshadows, setForeshadows] = useState([])
  const [loading, setLoading] = useState(true)
  const [resolveId, setResolveId] = useState(null)
  const [resolutionText, setResolutionText] = useState('')
  const [deleteFsId, setDeleteFsId] = useState(null)
  const [matching, setMatching] = useState(false)
  const [autoMatches, setAutoMatches] = useState(null)

  useEffect(() => { loadData() }, [bookId, refreshKey])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/knowledge/summary`)
      const data = await res.json()
      setForeshadows(data.foreshadows || [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function handleResolve() {
    if (!resolveId || !resolutionText.trim()) return
    await fetch(`/api/books/${bookId}/foreshadows/${resolveId}/resolve`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_text: resolutionText }),
    })
    setResolveId(null)
    setResolutionText('')
    loadData()
    triggerRefresh()
  }

  async function handleDelete(fsId) {
    setDeleteFsId(fsId)
  }

  async function confirmDelete() {
    await fetch(`/api/books/${bookId}/foreshadows/${deleteFsId}`, { method: 'DELETE' })
    setDeleteFsId(null)
    loadData()
  }

  async function handleMatchResolutions() {
    setMatching(true)
    try {
      await fetch(`/api/books/${bookId}/foreshadows/match-resolutions`, { method: 'POST' })
      loadData()
      triggerRefresh()
    } catch (e) { console.error(e) }
    setMatching(false)
  }

  async function loadAutoMatches() {
    setMatching(true)
    try {
      const res = await fetch(`/api/books/${bookId}/foreshadow-matches`)
      if (res.ok) setAutoMatches(await res.json())
    } catch (e) { console.error(e) }
    setMatching(false)
  }

  const getStatus = (f) => f.status || (f.resolved ? 'resolved' : 'open')
  const openFs = foreshadows.filter(f => getStatus(f) === 'open')
  const resolvedFs = foreshadows.filter(f => getStatus(f) === 'resolved')
  const crossVolFs = foreshadows.filter(f => getStatus(f) === 'cross_volume')
  const danglingFs = foreshadows.filter(f => getStatus(f) === 'dangling')
  const total = foreshadows.length
  const resolveRate = total > 0 ? Math.round((resolvedFs.length / total) * 100) : 0

  if (loading) return <LoadingState text="加载伏笔..." />

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="target" size={16} /> 伏笔追踪板</h3>
        <div className="flex gap-3 text-xs text-zinc-500 items-center">
          <span className="text-amber-400 flex items-center gap-1"><Icon name="hourglass" size={12} /> {openFs.length} 待回收</span>
          <span className="text-emerald-400 flex items-center gap-1"><Icon name="check-circle" size={12} /> {resolvedFs.length} 已回收</span>
          {crossVolFs.length > 0 && <span className="text-blue-400">📖 {crossVolFs.length} 跨卷</span>}
          {danglingFs.length > 0 && <span className="text-zinc-500">❓ {danglingFs.length} 悬置</span>}
          <button
            onClick={handleMatchResolutions}
            disabled={matching}
            className="ml-2 text-xs bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-zinc-200 rounded px-2 py-1 transition-colors"
          >
            {matching ? '匹配中...' : '自动匹配回收'}
          </button>
          <button
            onClick={loadAutoMatches}
            disabled={matching}
            className="ml-1 text-xs bg-sky-800/60 hover:bg-sky-700/60 disabled:opacity-50 text-sky-200 rounded px-2 py-1 transition-colors"
          >
            AI 悬空检测
          </button>
        </div>
      </div>

      {/* 统计条 */}
      {total > 0 && (
        <div className="px-6 py-4 bg-zinc-950/50 border-b border-zinc-800 shrink-0">
          <div className="flex items-center justify-between gap-4 mb-2">
            <div className="flex gap-3 flex-wrap">
              <div className="flex items-center gap-2 bg-amber-950/30 border border-amber-900/40 rounded-lg px-3 py-1.5">
                <div className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-xs font-medium text-amber-300">{openFs.length}</span>
                <span className="text-xs text-amber-400/80">待回收</span>
              </div>
              <div className="flex items-center gap-2 bg-emerald-950/30 border border-emerald-900/40 rounded-lg px-3 py-1.5">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs font-medium text-emerald-300">{resolvedFs.length}</span>
                <span className="text-xs text-emerald-400/80">已回收</span>
              </div>
              {crossVolFs.length > 0 && (
                <div className="flex items-center gap-2 bg-blue-950/30 border border-blue-900/40 rounded-lg px-3 py-1.5">
                  <div className="w-2 h-2 rounded-full bg-blue-400" />
                  <span className="text-xs font-medium text-blue-300">{crossVolFs.length}</span>
                  <span className="text-xs text-blue-400/80">跨卷</span>
                </div>
              )}
              {danglingFs.length > 0 && (
                <div className="flex items-center gap-2 bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-1.5">
                  <div className="w-2 h-2 rounded-full bg-zinc-500" />
                  <span className="text-xs font-medium text-zinc-400">{danglingFs.length}</span>
                  <span className="text-xs text-zinc-500">悬置</span>
                </div>
              )}
              <div className="flex items-center gap-2 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5">
                <span className="text-xs font-medium text-zinc-300">{total}</span>
                <span className="text-xs text-zinc-500">总计</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-zinc-200">{resolveRate}%</span>
              <span className="text-xs text-zinc-500">回收率</span>
            </div>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
              style={{ width: `${resolveRate}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {foreshadows.length === 0 ? (
          <EmptyState
            icon="target"
            title="暂无录入伏笔"
            description="在对话中让 AI 分析章节文本，暗示性语言会被自动识别为伏笔并追踪回收状态"
          />
        ) : (
          <div className="grid grid-cols-2 gap-6">
            {/* Open Column */}
            <div>
              <h4 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
                <Icon name="hourglass" size={14} /> 待回收 ({openFs.length})
              </h4>
              <div className="space-y-3">
                {openFs.map(f => (
                  <div key={f.id}
                    className="bg-amber-950/20 border border-amber-900/40 rounded-xl p-4 hover:border-amber-700/60 transition-colors"
                  >
                    <p className="text-sm text-amber-300 font-medium mb-1">"{f.text}"</p>
                    <div className="space-y-1.5 mt-2">
                      <div className="flex gap-2 text-xs">
                        <span className="text-zinc-600 shrink-0">暗示</span>
                        <span className="text-zinc-400">{f.hint}</span>
                      </div>
                      {f.expected_resolution && (
                        <div className="flex gap-2 text-xs">
                          <span className="text-zinc-600 shrink-0">预计</span>
                          <span className="text-zinc-500">{f.expected_resolution}</span>
                        </div>
                      )}
                      {f.plant_chapter && (
                        <div className="flex gap-2 text-xs">
                          <span className="text-zinc-600 shrink-0">埋设</span>
                          <span className="text-zinc-500">{f.plant_chapter}</span>
                        </div>
                      )}
                      {f.confidence && f.confidence !== 'high' && (
                        <div className="flex gap-2 text-xs">
                          <span className="text-zinc-600 shrink-0">置信度</span>
                          <span className={f.confidence === 'medium' ? 'text-yellow-500' : 'text-zinc-500'}>{f.confidence}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 mt-3 pt-2 border-t border-amber-900/20">
                      <button
                        onClick={() => setResolveId(f.id)}
                        className="text-xs text-emerald-600 hover:text-emerald-400 transition-colors"
                      >
                        <Icon name="check-circle" size={12} className="inline" /> 标记回收
                      </button>
                      <button
                        onClick={() => handleDelete(f.id)}
                        className="text-xs text-zinc-600 hover:text-red-400 transition-colors ml-auto"
                      >
                        删除
                      </button>
                    </div>

                    {resolveId === f.id && (
                      <div className="mt-2 space-y-2">
                        <textarea
                          value={resolutionText}
                          onChange={e => setResolutionText(e.target.value)}
                          placeholder="描述如何回收了这个伏笔..."
                          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 resize-none h-16"
                          autoFocus
                        />
                        <div className="flex gap-2 justify-end">
                          <button onClick={() => { setResolveId(null); setResolutionText('') }}
                            className="text-xs text-zinc-500 hover:text-zinc-300">取消</button>
                          <button onClick={handleResolve}
                            className="text-xs bg-emerald-600 text-white rounded px-3 py-1 hover:bg-emerald-500"
                            disabled={!resolutionText.trim()}>确认回收</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Right column: resolved + cross_volume + dangling */}
            <div>
              {/* Resolved */}
              {resolvedFs.length > 0 && (
                <>
                  <h4 className="text-sm font-semibold text-emerald-400 mb-3 flex items-center gap-2">
                    <Icon name="check-circle" size={14} /> 已回收 ({resolvedFs.length})
                  </h4>
                  <div className="space-y-3 mb-6">
                    {resolvedFs.map(f => (
                      <div key={f.id}
                        className="bg-emerald-950/20 border border-emerald-900/30 rounded-xl p-4 opacity-80"
                      >
                        <p className="text-sm text-zinc-400 font-medium line-through mb-1">"{f.text}"</p>
                        <div className="space-y-1.5 mt-2">
                          <div className="flex gap-2 text-xs">
                            <span className="text-zinc-600 shrink-0">暗示</span>
                            <span className="text-zinc-500">{f.hint}</span>
                          </div>
                          {f.resolution_text && (
                            <div className="flex gap-2 text-xs">
                              <span className="text-emerald-700 shrink-0">回收</span>
                              <span className="text-emerald-500">{f.resolution_text}</span>
                            </div>
                          )}
                          {f.resolve_chapter && (
                            <div className="flex gap-2 text-xs">
                              <span className="text-emerald-700 shrink-0">回收于</span>
                              <span className="text-emerald-500">{f.resolve_chapter}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Cross Volume */}
              {crossVolFs.length > 0 && (
                <>
                  <h4 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-2">
                    📖 跨卷待回收 ({crossVolFs.length})
                  </h4>
                  <div className="space-y-3 mb-6">
                    {crossVolFs.map(f => (
                      <div key={f.id}
                        className="bg-blue-950/20 border border-blue-900/30 rounded-xl p-4"
                      >
                        <p className="text-sm text-blue-300 font-medium mb-1">"{f.text}"</p>
                        <div className="space-y-1.5 mt-2">
                          <div className="flex gap-2 text-xs">
                            <span className="text-zinc-600 shrink-0">暗示</span>
                            <span className="text-zinc-400">{f.hint}</span>
                          </div>
                          {f.plant_chapter && (
                            <div className="flex gap-2 text-xs">
                              <span className="text-zinc-600 shrink-0">埋设</span>
                              <span className="text-blue-400">{f.plant_chapter}</span>
                            </div>
                          )}
                          {f.volume_ref && (
                            <div className="flex gap-2 text-xs">
                              <span className="text-zinc-600 shrink-0">所属</span>
                              <span className="text-blue-400">{f.volume_ref}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Dangling */}
              {danglingFs.length > 0 && (
                <>
                  <h4 className="text-sm font-semibold text-zinc-500 mb-3 flex items-center gap-2">
                    ❓ 悬置线索 ({danglingFs.length})
                  </h4>
                  <div className="space-y-3">
                    {danglingFs.map(f => (
                      <div key={f.id}
                        className="bg-zinc-900/30 border border-zinc-800 rounded-xl p-4"
                      >
                        <p className="text-sm text-zinc-500 font-medium mb-1">"{f.text}"</p>
                        <div className="space-y-1.5 mt-2">
                          <div className="flex gap-2 text-xs">
                            <span className="text-zinc-600 shrink-0">暗示</span>
                            <span className="text-zinc-500">{f.hint}</span>
                          </div>
                          {f.confidence && (
                            <div className="flex gap-2 text-xs">
                              <span className="text-zinc-600 shrink-0">置信度</span>
                              <span className={f.confidence === 'low' ? 'text-zinc-600' : 'text-yellow-600'}>{f.confidence}</span>
                            </div>
                          )}
                        </div>
                        <div className="flex gap-2 mt-3 pt-2 border-t border-zinc-800">
                          <button
                            onClick={() => setResolveId(f.id)}
                            className="text-xs text-emerald-600 hover:text-emerald-400 transition-colors"
                          >
                            标记回收
                          </button>
                          <button
                            onClick={() => handleDelete(f.id)}
                            className="text-xs text-zinc-600 hover:text-red-400 transition-colors ml-auto"
                          >
                            删除
                          </button>
                        </div>
                        {resolveId === f.id && (
                          <div className="mt-2 space-y-2">
                            <textarea
                              value={resolutionText}
                              onChange={e => setResolutionText(e.target.value)}
                              placeholder="描述如何回收了这个伏笔..."
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 resize-none h-16"
                              autoFocus
                            />
                            <div className="flex gap-2 justify-end">
                              <button onClick={() => { setResolveId(null); setResolutionText('') }}
                                className="text-xs text-zinc-500 hover:text-zinc-300">取消</button>
                              <button onClick={handleResolve}
                                className="text-xs bg-emerald-600 text-white rounded px-3 py-1 hover:bg-emerald-500"
                                disabled={!resolutionText.trim()}>确认回收</button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* AI 自动匹配结果面板 */}
      {autoMatches && (
        <div className="border-t border-zinc-800 bg-sky-950/20 p-4 shrink-0 max-h-60 overflow-y-auto">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-sky-400 flex items-center gap-1.5">
              <Icon name="search" size={12} /> AI 伏笔匹配分析
            </h4>
            <button onClick={() => setAutoMatches(null)} className="text-zinc-600 hover:text-zinc-400">
              <Icon name="x" size={12} />
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2 mb-2 text-[10px]">
            <span className="text-emerald-400">已匹配 {autoMatches.matched || 0}</span>
            <span className="text-amber-400">弱匹配 {autoMatches.weak || 0}</span>
            <span className="text-red-400">悬空 {autoMatches.dangling || 0}</span>
          </div>
          {autoMatches.matches?.filter((m: any) => m.status === 'dangling' || m.status === 'matched').slice(0, 5).map((m: any, i: number) => (
            <div key={i} className={`text-[10px] rounded p-2 mb-1 border ${
              m.status === 'dangling' ? 'bg-red-950/30 border-red-900/30' : 'bg-emerald-950/20 border-emerald-900/20'
            }`}>
              <span className="text-zinc-300">{m.foreshadow_description?.slice(0, 40)}</span>
              {m.status === 'matched' && m.matched_chapter_title && (
                <span className="text-emerald-500 ml-2">→ 第{m.matched_chapter_title}章 (相似度{(m.similarity * 100).toFixed(0)}%)</span>
              )}
              {m.status === 'dangling' && <span className="text-red-500 ml-2">⚠ 未回收</span>}
            </div>
          ))}
        </div>
      )}

      <ConfirmModal
        open={!!deleteFsId}
        title="删除伏笔"
        message="确定删除此伏笔？此操作不可撤销。"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setDeleteFsId(null)}
      />
    </div>
  )
}
