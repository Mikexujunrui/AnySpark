import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import EmptyState from './ui/EmptyState'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'
import { useRefreshKey } from "../store"
import OutlinePipelinePanel from './OutlinePipelinePanel'
import ChapterDependencyGraph from './ChapterDependencyGraph'

export default function OutlinePanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [outline, setOutline] = useState<Record<string, any> | null>(null)
  const [detailed, setDetailed] = useState<Record<string, any> | null>(null)
  const [volumes, setVolumes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState('outline')
  const [continuityCards, setContinuityCards] = useState<Record<string, any> | null>(null)
  const [generatingCards, setGeneratingCards] = useState(false)
  const [flavorReports, setFlavorReports] = useState<Record<string, any> | null>(null)
  const [editingSummary, setEditingSummary] = useState(false)
  const [summaryDraft, setSummaryDraft] = useState('')
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editingExtra, setEditingExtra] = useState(false)
  const [editDraft, setEditDraft] = useState<Record<string, any>>({})
  const [editingDetailedIdx, setEditingDetailedIdx] = useState<number | null>(null)
  const [editingDetailedExtra, setEditingDetailedExtra] = useState(false)
  const [detailedEditDraft, setDetailedEditDraft] = useState<Record<string, any>>({})
  const [showPipeline, setShowPipeline] = useState(false)
  const [scanningFlavor, setScanningFlavor] = useState(false)

  useEffect(() => { loadAll() }, [bookId, refreshKey])

  async function loadAll() {
    setLoading(true)
    try {
      const [o, d, v, cc, fr] = await Promise.all([
        fetch(`/api/books/${bookId}/outline`).then(r => r.json()),
        fetch(`/api/books/${bookId}/detailed-outline`).then(r => r.json()),
        fetch(`/api/books/${bookId}/volumes`).then(r => r.json().catch(() => [])),
        fetch(`/api/books/${bookId}/continuity-cards`).then(r => r.json().catch(() => null)),
        fetch(`/api/books/${bookId}/flavor-reports`).then(r => r.json().catch(() => null)),
      ])
      setOutline(o)
      setDetailed(d)
      setVolumes(Array.isArray(v) ? v : [])
      setContinuityCards(cc)
      setFlavorReports(fr)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  function loadOutline() { loadAll() }

  async function saveSummary() {
    await fetch(`/api/books/${bookId}/outline/summary`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ summary: summaryDraft }),
    })
    setEditingSummary(false)
    loadOutline()
  }

  async function saveChapter(idx: number) {
    const endpoint = editingExtra
      ? `/api/books/${bookId}/outline/extras/${idx + 1}`
      : `/api/books/${bookId}/outline/chapters/${idx + 1}`
    await fetch(endpoint, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editDraft),
    })
    setEditingIdx(null)
    setEditingExtra(false)
    setEditDraft({})
    loadOutline()
  }

  async function saveDetailedChapter(idx: number) {
    const payload = { ...detailedEditDraft }
    if (typeof payload.plot_chain === 'string') {
      payload.plot_chain = payload.plot_chain.split('\n').map(s => s.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }
    const endpoint = editingDetailedExtra
      ? `/api/books/${bookId}/detailed-outline/extras/${idx + 1}`
      : `/api/books/${bookId}/detailed-outline/chapters/${idx + 1}`
    await fetch(endpoint, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    setEditingDetailedIdx(null)
    setEditingDetailedExtra(false)
    setDetailedEditDraft({})
    loadAll()
  }

  if (loading) return <LoadingState text="加载大纲..." />

  const chapters = outline?.chapters || []
  const extras = outline?.extras || []
  const detailedChapters = detailed?.chapters || []
  const detailedExtras = detailed?.extras || []
  const hasOutline = outline?.summary || chapters.some(c => c.synopsis) || extras.some(e => e?.synopsis)
  const hasDetailed = detailedChapters.some(c => c && c.plot_chain?.length > 0) || detailedExtras.some(e => e && e.plot_chain?.length > 0)

  if (!hasOutline && !hasDetailed) {
    return <EmptyState
      icon="list"
      title="尚未生成大纲"
      description="在对话中输入 /outline 或直接告诉 AI「帮我生成全书大纲」来自动创建"
      action={() => {}}
      actionLabel=""
    />
  }

  const regularCount = chapters.filter(c => c.synopsis).length
  const extraCount = extras.filter(e => e?.synopsis).length
  const detailedRegularCount = detailedChapters.filter(c => c && c.plot_chain?.length).length
  const detailedExtraCount = detailedExtras.filter(e => e && e.plot_chain?.length).length

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="px-4 py-2.5 border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-sm shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon name="clipboard-list" size={16} className="text-zinc-400" />
          <span className="text-sm font-medium text-zinc-300">大纲</span>
          <div className="flex gap-0.5 bg-zinc-800/80 rounded-lg p-0.5 ml-2">
            <button onClick={() => setViewMode('outline')}
              className={`px-2.5 py-1 text-[11px] rounded-md font-medium transition-all ${
                viewMode === 'outline' ? 'bg-zinc-700 text-zinc-100 shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}>
              总纲
            </button>
            <button onClick={() => setViewMode('detailed')}
              className={`px-2.5 py-1 text-[11px] rounded-md font-medium transition-all ${
                viewMode === 'detailed' ? 'bg-zinc-700 text-zinc-100 shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}>
              细纲
            </button>
            <button onClick={() => setViewMode('continuity')}
              className={`px-2.5 py-1 text-[11px] rounded-md font-medium transition-all ${
                viewMode === 'continuity' ? 'bg-zinc-700 text-zinc-100 shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}>
              连续性
            </button>
            <button onClick={() => setViewMode('flavor')}
              className={`px-2.5 py-1 text-[11px] rounded-md font-medium transition-all ${
                viewMode === 'flavor' ? 'bg-zinc-700 text-zinc-100 shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`}>
              AI味
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPipeline(!showPipeline)}
            className="flex items-center gap-1 text-[11px] bg-violet-800/60 hover:bg-violet-700/60 text-violet-200 rounded-lg px-2 py-1 transition-colors"
          >
            <Icon name="sparkles" size={11} /> 逐级展开
          </button>
          <span className="text-[11px] text-zinc-600">
            {viewMode === 'outline'
              ? `${regularCount} 章${extraCount ? ` + ${extraCount} 番外` : ''}`
              : `${detailedRegularCount} 章${detailedExtraCount ? ` + ${detailedExtraCount} 番外` : ''}`}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {showPipeline && (
          <div className="p-4 space-y-4">
            <OutlinePipelinePanel bookId={bookId} onDone={() => { setShowPipeline(false); loadAll() }} />
            <ChapterDependencyGraph bookId={bookId} />
          </div>
        )}
        {viewMode === 'detailed' && (
          <div className="divide-y divide-zinc-800/50">
            {!hasDetailed && (
              <div className="p-8 text-center text-zinc-600 text-sm">
                尚未生成细纲。在对话中说"生成细纲"来自动创建。
              </div>
            )}
            {detailedChapters.map((ch, idx) => {
              if (!ch || !ch.plot_chain?.length) return null
              const isEditingDetailed = editingDetailedIdx === idx && !editingDetailedExtra
              return (
                <div key={idx} className="px-6 py-3 hover:bg-zinc-900/30 transition-colors">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-semibold text-zinc-300">#{idx + 1}</span>
                        {isEditingDetailed ? (
                          <input value={detailedEditDraft.title ?? ch.title ?? ''}
                            onChange={e => setDetailedEditDraft(d => ({ ...d, title: e.target.value }))}
                            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-xs text-zinc-200 focus:outline-none"
                            placeholder="章节标题" />
                        ) : (
                          <span className="text-xs font-medium text-zinc-400">{ch.title || ''}</span>
                        )}
                        {ch.chapter_function && !isEditingDetailed && (
                          <span className="text-[10px] bg-blue-900/30 text-blue-400 px-1.5 rounded">{ch.chapter_function}</span>
                        )}
                      </div>
                      {isEditingDetailed ? (
                        <div className="space-y-2">
                          <input value={detailedEditDraft.chapter_function ?? ch.chapter_function ?? ''}
                            onChange={e => setDetailedEditDraft(d => ({ ...d, chapter_function: e.target.value }))}
                            className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-xs text-zinc-200 focus:outline-none"
                            placeholder="章节功能（如：承上启下、高潮、转折）" />
                          <label className="text-[10px] text-zinc-500">剧情链（每行一条）</label>
                          <textarea value={detailedEditDraft.plot_chain ?? ch.plot_chain?.join('\n') ?? ''}
                            onChange={e => setDetailedEditDraft(d => ({ ...d, plot_chain: e.target.value }))}
                            className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-xs text-zinc-200 focus:outline-none resize-none" rows={5}
                            placeholder="1. 第一条剧情..." />
                          <div className="flex gap-2 justify-end">
                            <button onClick={() => { setEditingDetailedIdx(null); setEditingDetailedExtra(false); setDetailedEditDraft({}) }}
                              className="text-[10px] text-zinc-500 px-2 py-1">取消</button>
                            <button onClick={() => saveDetailedChapter(idx)}
                              className="text-[10px] bg-zinc-200 text-zinc-900 rounded px-2 py-1 font-medium">保存</button>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-1 pl-4 border-l-2 border-zinc-800">
                          {ch.plot_chain.map((ev, ei) => (
                            <p key={ei} className="text-xs text-zinc-400 leading-relaxed">
                              <span className="text-zinc-600 mr-1">{ei + 1}.</span>{ev}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                    {!isEditingDetailed && (
                      <button onClick={() => { setEditingDetailedIdx(idx); setEditingDetailedExtra(false); setDetailedEditDraft({}) }}
                        className="text-[10px] text-zinc-600 hover:text-zinc-300 shrink-0 mt-1">编辑</button>
                    )}
                  </div>
                </div>
              )
            })}

            {/* 番外细纲专区 */}
            {detailedExtras.filter(e => e && e.plot_chain?.length).length > 0 && (
              <>
                <div className="px-6 py-2 mt-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 border-t border-zinc-800" />
                    <span className="text-[10px] text-purple-500 font-medium">番外 ({detailedExtraCount} 篇)</span>
                    <div className="flex-1 border-t border-zinc-800" />
                  </div>
                </div>
                {detailedExtras.map((e, idx) => {
                  if (!e || !e.plot_chain?.length) return null
                  const isEditingDetailedExtra = editingDetailedIdx === idx && editingDetailedExtra
                  return (
                    <div key={`extra-${idx}`} className="px-6 py-3 hover:bg-zinc-900/30 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs font-semibold text-purple-400">#E{idx + 1}</span>
                            {isEditingDetailedExtra ? (
                              <input value={detailedEditDraft.title ?? e.title ?? ''}
                                onChange={ev => setDetailedEditDraft(d => ({ ...d, title: ev.target.value }))}
                                className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-xs text-zinc-200 focus:outline-none"
                                placeholder="番外标题" />
                            ) : (
                              <span className="text-xs font-medium text-zinc-400">{e.title || ''}</span>
                            )}
                            {e.chapter_function && !isEditingDetailedExtra && (
                              <span className="text-[10px] bg-purple-900/30 text-purple-400 px-1.5 rounded">{e.chapter_function}</span>
                            )}
                          </div>
                          {isEditingDetailedExtra ? (
                            <div className="space-y-2">
                              <input value={detailedEditDraft.chapter_function ?? e.chapter_function ?? ''}
                                onChange={ev => setDetailedEditDraft(d => ({ ...d, chapter_function: ev.target.value }))}
                                className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-xs text-zinc-200 focus:outline-none"
                                placeholder="章节功能" />
                              <label className="text-[10px] text-zinc-500">剧情链（每行一条）</label>
                              <textarea value={detailedEditDraft.plot_chain ?? e.plot_chain?.join('\n') ?? ''}
                                onChange={ev => setDetailedEditDraft(d => ({ ...d, plot_chain: ev.target.value }))}
                                className="w-full bg-zinc-800 border border-zinc-700 rounded p-2 text-xs text-zinc-200 focus:outline-none resize-none" rows={5}
                                placeholder="1. 第一条剧情..." />
                              <div className="flex gap-2 justify-end">
                                <button onClick={() => { setEditingDetailedIdx(null); setEditingDetailedExtra(false); setDetailedEditDraft({}) }}
                                  className="text-[10px] text-zinc-500 px-2 py-1">取消</button>
                                <button onClick={() => saveDetailedChapter(idx)}
                                  className="text-[10px] bg-zinc-200 text-zinc-900 rounded px-2 py-1 font-medium">保存</button>
                              </div>
                            </div>
                          ) : (
                            <div className="space-y-1 pl-4 border-l-2 border-purple-900/40">
                              {e.plot_chain.map((ev, ei) => (
                                <p key={ei} className="text-xs text-zinc-400 leading-relaxed">
                                  <span className="text-zinc-600 mr-1">{ei + 1}.</span>{ev}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                        {!isEditingDetailedExtra && (
                          <button onClick={() => { setEditingDetailedIdx(idx); setEditingDetailedExtra(true); setDetailedEditDraft({}) }}
                            className="text-[10px] text-zinc-600 hover:text-zinc-300 shrink-0 mt-1">编辑</button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        )}

        {viewMode === 'outline' && <>
        {/* 总纲 */}
        <div className="px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-1 h-4 rounded-full bg-sky-500" />
              <h3 className="text-sm font-semibold text-zinc-200">全书总纲</h3>
              <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">summary</span>
            </div>
            {!editingSummary && (
              <button onClick={() => { setEditingSummary(true); setSummaryDraft(outline?.summary || '') }}
                className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 bg-zinc-800/60 hover:bg-zinc-700/60 rounded-lg px-2.5 py-1 transition-colors">
                <Icon name="pen" size={11} /> 编辑
              </button>
            )}
          </div>
          {editingSummary ? (
            <div className="bg-zinc-900/60 border border-zinc-700/60 rounded-xl p-4 space-y-3">
              <textarea value={summaryDraft} onChange={e => setSummaryDraft(e.target.value)}
                className="w-full bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 focus:outline-none focus:border-sky-600/50 focus:ring-1 focus:ring-sky-600/20 resize-none transition-colors"
                rows={6} placeholder="撰写全书总纲..." />
              <div className="flex gap-2 justify-end">
                <button onClick={() => setEditingSummary(false)}
                  className="text-[11px] text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg transition-colors">取消</button>
                <button onClick={saveSummary}
                  className="text-[11px] bg-sky-600 hover:bg-sky-500 text-white rounded-lg px-4 py-1.5 font-medium transition-colors shadow-sm">保存总纲</button>
              </div>
            </div>
          ) : (
            <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4">
              {outline?.summary ? (
                <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{outline.summary}</p>
              ) : (
                <div className="flex flex-col items-center gap-2 py-6 text-zinc-600">
                  <Icon name="file-text" size={24} />
                  <p className="text-xs">尚未生成总纲</p>
                  <p className="text-[10px]">在对话中用 /outline 或告诉 AI 自动生成</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 卷纲 */}
        {volumes.length > 0 && (
          <div className="px-4 pb-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1 h-4 rounded-full bg-violet-500" />
              <h3 className="text-sm font-semibold text-zinc-200">卷纲</h3>
              <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">{volumes.length} 卷</span>
            </div>
            <div className="space-y-2">
              {volumes.sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((v, vi) => (
                <div key={v.id} className="group bg-zinc-900/40 border border-zinc-800/60 hover:border-zinc-700/60 rounded-xl p-3.5 transition-all">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-mono text-violet-500 bg-violet-500/10 px-1.5 py-0.5 rounded">V{vi + 1}</span>
                    <span className="text-sm font-semibold text-zinc-200">{v.title}</span>
                    <span className="text-[11px] text-zinc-600 ml-auto">{v.chapters?.length || 0} 章</span>
                  </div>
                  {v.storyLine ? (
                    <p className="text-xs text-zinc-400 leading-relaxed pl-1">{v.storyLine}</p>
                  ) : (
                    <p className="text-xs text-zinc-600 italic pl-1">故事主线待设置 — 使用 update_volume 或 generate_volume_outlines 自动生成</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 章节分隔线 */}
        <div className="px-4 pb-2">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-zinc-800" />
            {volumes.length > 0 ? (
              <>
                <span className="text-[10px] text-zinc-600 font-medium">章节概要</span>
                <div className="flex-1 h-px bg-zinc-800" />
              </>
            ) : (
              <span className="text-[10px] text-zinc-600 font-medium shrink-0">章节概要</span>
            )}
          </div>
        </div>

        {/* Chapters */}
        <div className="px-3 space-y-1 pb-4">
          {chapters.map((ch, idx) => {
            if (!ch.synopsis && !ch.notes) return null
            const isEditing = editingIdx === idx && !editingExtra

            return (
              <div key={idx} className={`rounded-xl transition-all ${
                isEditing
                  ? 'bg-zinc-900/60 border border-sky-700/40 ring-1 ring-sky-600/20'
                  : 'bg-zinc-900/30 border border-zinc-800/50 hover:border-zinc-700/50'
              }`}>
                <div className="px-3.5 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[10px] font-mono text-zinc-600 bg-zinc-800/70 px-1.5 py-0.5 rounded">#{idx + 1}</span>
                      <span className="text-xs font-semibold text-zinc-200 truncate">{ch.title || '无标题'}</span>
                      {ch.turning_point && (
                        <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 rounded shrink-0">转折</span>
                      )}
                    </div>

                    {isEditing ? (
                      <div className="space-y-2 mt-2">
                        <textarea value={editDraft.synopsis ?? ch.synopsis}
                          onChange={e => setEditDraft(d => ({ ...d, synopsis: e.target.value }))}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-600/50 resize-none transition-colors" rows={2}
                          placeholder="章节概要..." />
                        <textarea value={editDraft.notes ?? ch.notes ?? ''}
                          onChange={e => setEditDraft(d => ({ ...d, notes: e.target.value }))}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-600/50 resize-none transition-colors" rows={2}
                          placeholder="备注/规划..." />
                        <div className="flex gap-2 justify-end">
                          <button onClick={() => { setEditingIdx(null); setEditingExtra(false); setEditDraft({}) }}
                            className="text-[11px] text-zinc-500 hover:text-zinc-300 px-2.5 py-1">取消</button>
                          <button onClick={() => saveChapter(idx)}
                            className="text-[11px] bg-sky-600 hover:bg-sky-500 text-white rounded-lg px-3 py-1 font-medium transition-colors">保存</button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {ch.synopsis && <p className="text-xs text-zinc-400 leading-relaxed">{ch.synopsis}</p>}
                        {ch.key_events?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {ch.key_events.map((ev, ei) => (
                              <span key={ei} className="text-[10px] bg-zinc-800/80 text-zinc-400 border border-zinc-700/50 px-2 py-0.5 rounded-full">{ev}</span>
                            ))}
                          </div>
                        )}
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
                          {ch.characters?.length > 0 && (
                            <span className="flex items-center gap-1"><Icon name="user" size={10} /> {ch.characters.join(', ')}</span>
                          )}
                          {ch.turning_point && (
                            <span className="flex items-center gap-1 text-amber-500/60"><Icon name="zap" size={10} /> {ch.turning_point}</span>
                          )}
                        </div>
                        {ch.notes && (
                          <p className="text-[10px] text-zinc-500 mt-1.5 italic">{ch.notes}</p>
                        )}
                      </>
                    )}
                  </div>

                  {!isEditing && (
                    <button onClick={() => { setEditingIdx(idx); setEditingExtra(false); setEditDraft({}) }}
                      className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-300 bg-zinc-800/60 hover:bg-zinc-700/60 rounded-lg px-2 py-1 transition-colors shrink-0">
                      <Icon name="pen" size={10} /> 编辑
                    </button>
                  )}
                </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* 番外大纲专区 */}
        {extras.filter(e => e?.synopsis || e?.notes).length > 0 && (
          <>
            <div className="px-4 py-1">
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-zinc-800" />
                <span className="text-[10px] text-purple-400 font-medium">番外 · {extraCount} 篇</span>
                <div className="flex-1 h-px bg-zinc-800" />
              </div>
            </div>
            <div className="px-3 space-y-1 pb-4">
              {extras.map((e, idx) => {
                if (!e || (!e.synopsis && !e.notes)) return null
                const isEditing = editingIdx === idx && editingExtra

                return (
                  <div key={`extra-${idx}`} className={`rounded-xl transition-all ${
                    isEditing
                      ? 'bg-zinc-900/60 border border-purple-700/40 ring-1 ring-purple-600/20'
                      : 'bg-zinc-900/30 border border-zinc-800/50 hover:border-zinc-700/50'
                  }`}>
                    <div className="px-3.5 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-[10px] font-mono text-purple-500 bg-purple-500/10 px-1.5 py-0.5 rounded">#E{idx + 1}</span>
                          <span className="text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-1.5 rounded">番外</span>
                          <span className="text-xs font-semibold text-zinc-200 truncate">{e.title || ''}</span>
                        </div>

                        {isEditing ? (
                          <div className="space-y-2 mt-2">
                            <textarea value={editDraft.synopsis ?? e.synopsis ?? ''}
                              onChange={ev => setEditDraft(d => ({ ...d, synopsis: ev.target.value }))}
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-purple-600/50 resize-none transition-colors" rows={2}
                              placeholder="番外概要..." />
                            <textarea value={editDraft.notes ?? e.notes ?? ''}
                              onChange={ev => setEditDraft(d => ({ ...d, notes: ev.target.value }))}
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-2.5 text-xs text-zinc-200 focus:outline-none focus:border-purple-600/50 resize-none transition-colors" rows={2}
                              placeholder="备注/规划..." />
                            <div className="flex gap-2 justify-end">
                              <button onClick={() => { setEditingIdx(null); setEditingExtra(false); setEditDraft({}) }}
                                className="text-[11px] text-zinc-500 hover:text-zinc-300 px-2.5 py-1">取消</button>
                              <button onClick={() => saveChapter(idx)}
                                className="text-[11px] bg-purple-600 hover:bg-purple-500 text-white rounded-lg px-3 py-1 font-medium transition-colors">保存</button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {e.synopsis && <p className="text-xs text-zinc-400 leading-relaxed">{e.synopsis}</p>}
                            {e.key_events?.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {e.key_events.map((ev, ei) => (
                                  <span key={ei} className="text-[10px] bg-zinc-800/80 text-zinc-400 border border-zinc-700/50 px-2 py-0.5 rounded-full">{ev}</span>
                                ))}
                              </div>
                            )}
                            <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
                              {e.characters?.length > 0 && (
                                <span className="flex items-center gap-1"><Icon name="user" size={10} /> {e.characters.join(', ')}</span>
                              )}
                            </div>
                            {e.notes && (
                              <p className="text-[10px] text-zinc-500 mt-1.5 italic">{e.notes}</p>
                            )}
                          </>
                        )}
                      </div>

                      {!isEditing && (
                        <button onClick={() => { setEditingIdx(idx); setEditingExtra(true); setEditDraft({}) }}
                          className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-300 bg-zinc-800/60 hover:bg-zinc-700/60 rounded-lg px-2 py-1 transition-colors shrink-0">
                          <Icon name="pen" size={10} /> 编辑
                        </button>
                      )}
                    </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
        </>}
        
        {viewMode === 'continuity' && (() => {
          const cards = continuityCards?.chapters || {}
          const cardEntries = Object.entries(cards).sort(([a], [b]) => parseInt(a) - parseInt(b))
          if (cardEntries.length === 0) {
            return (
              <div className="p-8 text-center text-zinc-600 text-sm">
                <p className="mb-3">尚未生成连续性卡片。</p>
                <button
                  onClick={async () => {
                    setGeneratingCards(true)
                    try {
                      const r = await fetch(`/api/books/${bookId}/continuity-cards/generate`, { method: 'POST' })
                      const data = await r.json()
                      if (data.ok) {
                        loadAll()
                      }
                    } catch (e) { console.error(e) }
                    setGeneratingCards(false)
                  }}
                  disabled={generatingCards}
                  className="bg-emerald-700/60 hover:bg-emerald-600/60 text-emerald-200 rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                >
                  {generatingCards ? '生成中...' : '为所有章节生成连续性卡片'}
                </button>
              </div>
            )
          }
          return (
            <div className="divide-y divide-zinc-800/50">
              <div className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-1 h-4 rounded-full bg-emerald-500" />
                  <h3 className="text-sm font-semibold text-zinc-200">前情连续性</h3>
                  <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">{cardEntries.length} 章</span>
                </div>
                <p className="text-[11px] text-zinc-500 ml-3">每章定稿后自动生成，记录角色位置、情绪、伏笔状态，供下一章写作时保持连续性</p>
              </div>
              {cardEntries.map(([chIdx, card]: [string, any]) => (
                <div key={chIdx} className="px-6 py-3 hover:bg-zinc-900/30 transition-colors">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-semibold text-emerald-400">#{chIdx}</span>
                    <span className="text-xs font-medium text-zinc-300">{card.chapter_title || ''}</span>
                    {card.generated_at && (
                      <span className="text-[10px] text-zinc-600 ml-auto">{new Date(card.generated_at).toLocaleDateString()}</span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap">{card.text || ''}</p>
                </div>
              ))}
            </div>
          )
        })()}

        {viewMode === 'flavor' && (() => {
          const chapters = flavorReports?.chapters || {}
          const entries = Object.entries(chapters).sort(([a], [b]) => parseInt(a) - parseInt(b))
          if (entries.length === 0) {
            return (
              <div className="p-8 text-center text-zinc-600 text-sm">
                <p className="mb-3">尚未生成AI味扫描报告。</p>
                <button
                  onClick={async () => {
                    setScanningFlavor(true)
                    try {
                      const r = await fetch(`/api/books/${bookId}/flavor-reports/scan-all`, { method: 'POST' })
                      const data = await r.json()
                      if (data.ok) {
                        loadAll()
                        showToast(`已扫描 ${data.scanned} 章，跳过 ${data.skipped} 章`, 'success')
                      }
                    } catch (e) { console.error(e) }
                    setScanningFlavor(false)
                  }}
                  disabled={scanningFlavor}
                  className="bg-amber-700/60 hover:bg-amber-600/60 text-amber-200 rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                >
                  {scanningFlavor ? '扫描中...' : '扫描全部章节'}
                </button>
              </div>
            )
          }
          return (
            <div className="divide-y divide-zinc-800/50">
              <div className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-1 h-4 rounded-full bg-amber-500" />
                  <h3 className="text-sm font-semibold text-zinc-200">AI味扫描</h3>
                  <span className="text-[10px] text-zinc-600 bg-zinc-800/60 px-1.5 py-0.5 rounded">{entries.length} 章</span>
                  <button
                    onClick={async () => {
                      setScanningFlavor(true)
                      try {
                        const r = await fetch(`/api/books/${bookId}/flavor-reports/scan-all`, { method: 'POST' })
                        const data = await r.json()
                        if (data.ok) {
                          loadAll()
                          showToast(`已扫描 ${data.scanned} 章，跳过 ${data.skipped} 章`, 'success')
                        }
                      } catch (e) { console.error(e) }
                      setScanningFlavor(false)
                    }}
                    disabled={scanningFlavor}
                    className="ml-auto text-[10px] bg-amber-800/40 hover:bg-amber-700/40 text-amber-300 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
                  >
                    {scanningFlavor ? '扫描中...' : '扫描未打分章节'}
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 ml-3">纯规则检测，零token消耗。评分越高越像人写的。</p>
              </div>
              {entries.map(([chIdx, report]: [string, any]) => {
                const score = report.overall_score ?? 100
                const scoreColor = score >= 80 ? 'text-emerald-400' : score >= 60 ? 'text-amber-400' : 'text-red-400'
                return (
                  <div key={chIdx} className="px-6 py-3 hover:bg-zinc-900/30 transition-colors">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-semibold text-zinc-400">#{chIdx}</span>
                      <span className={`text-sm font-bold ${scoreColor}`}>{score.toFixed(0)}/100</span>
                      {report.is_clean && <span className="text-[10px] bg-emerald-900/30 text-emerald-400 px-1.5 rounded">通过</span>}
                    </div>
                    {report.checks?.length > 0 && (
                      <div className="space-y-1.5">
                        {report.checks.map((c: any, ci: number) => (
                          <div key={ci} className="flex items-start gap-2">
                            <span className={`text-[10px] mt-0.5 ${c.passed ? 'text-emerald-500' : 'text-amber-500'}`}>
                              {c.passed ? '✓' : '⚠'}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] text-zinc-400">{c.name}</span>
                                <span className="text-[10px] text-zinc-600">{c.score?.toFixed(0)}分</span>
                              </div>
                              {c.details?.length > 0 && (
                                <div className="mt-0.5">
                                  {c.details.slice(0, 2).map((d: string, di: number) => (
                                    <p key={di} className="text-[10px] text-zinc-500">{d}</p>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {report.flagged_lines?.length > 0 && (
                      <div className="mt-2 pl-4 border-l-2 border-amber-800/50">
                        {report.flagged_lines.slice(0, 3).map((line: string, li: number) => (
                          <p key={li} className="text-[10px] text-amber-500/80 leading-relaxed">{line}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )
        })()}

      </div>
    </div>
  )
}
