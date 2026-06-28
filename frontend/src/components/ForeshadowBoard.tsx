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

  const unresolved = foreshadows.filter(f => !f.resolved)
  const resolved = foreshadows.filter(f => f.resolved)
  const total = foreshadows.length
  const resolveRate = total > 0 ? Math.round((resolved.length / total) * 100) : 0

  if (loading) return <LoadingState text="加载伏笔..." />

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="target" size={16} /> 伏笔追踪板</h3>
        <div className="flex gap-3 text-xs text-zinc-500">
          <span className="text-amber-400 flex items-center gap-1"><Icon name="hourglass" size={12} /> {unresolved.length} 待回收</span>
          <span className="text-emerald-400 flex items-center gap-1"><Icon name="check-circle" size={12} /> {resolved.length} 已回收</span>
        </div>
      </div>

      {/* 统计条 */}
      {total > 0 && (
        <div className="px-6 py-4 bg-zinc-950/50 border-b border-zinc-800 shrink-0">
          <div className="flex items-center justify-between gap-4 mb-2">
            <div className="flex gap-3">
              <div className="flex items-center gap-2 bg-amber-950/30 border border-amber-900/40 rounded-lg px-3 py-1.5">
                <div className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-xs font-medium text-amber-300">{unresolved.length}</span>
                <span className="text-xs text-amber-400/80">待回收</span>
              </div>
              <div className="flex items-center gap-2 bg-emerald-950/30 border border-emerald-900/40 rounded-lg px-3 py-1.5">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs font-medium text-emerald-300">{resolved.length}</span>
                <span className="text-xs text-emerald-400/80">已回收</span>
              </div>
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
          {unresolved.length > 0 && (
            <p className="text-[10px] text-zinc-600 mt-2">
              💡 还有 <span className="text-amber-400 font-medium">{unresolved.length}</span> 个伏笔待处理 · {resolved.length > 0 ? `最近回收率 ${resolveRate}%` : '开始回收第一个伏笔吧'}
            </p>
          )}
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
            {/* Unresolved Column */}
            <div>
              <h4 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
                <Icon name="hourglass" size={14} /> 待回收 ({unresolved.length})
              </h4>
              <div className="space-y-3">
                {unresolved.map(f => (
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

            {/* Resolved Column */}
            <div>
              <h4 className="text-sm font-semibold text-emerald-400 mb-3 flex items-center gap-2">
                <Icon name="check-circle" size={14} /> 已回收 ({resolved.length})
              </h4>
              <div className="space-y-3">
                {resolved.map(f => (
                  <div key={f.id}
                    className="bg-emerald-950/20 border border-emerald-900/30 rounded-xl p-4 opacity-80"
                  >
                    <p className="text-sm text-zinc-400 font-medium line-through mb-1">"{f.text}"</p>
                    <div className="space-y-1.5 mt-2">
                      <div className="flex gap-2 text-xs">
                        <span className="text-zinc-600 shrink-0">暗示</span>
                        <span className="text-zinc-500">{f.hint}</span>
                      </div>
                      {f.resolution && (
                        <div className="flex gap-2 text-xs">
                          <span className="text-emerald-700 shrink-0">回收</span>
                          <span className="text-emerald-500">{f.resolution}</span>
                        </div>
                      )}
                      {f.expected_resolution && (
                        <div className="flex gap-2 text-xs">
                          <span className="text-zinc-600 shrink-0">预计</span>
                          <span className="text-zinc-600">{f.expected_resolution}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

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
