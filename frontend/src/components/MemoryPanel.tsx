import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import Toggle from './ui/Toggle'
import { api } from '../api'

const CATEGORY_LABELS: Record<string, string> = {
  'user_preference': '通用',
  'user_preference.xp': 'XP偏好',
  'user_preference.xp.relationship': '关系动力',
  'user_preference.xp.archetype': '角色原型',
  'user_preference.xp.excluded': '雷区',
  'user_preference.narrative': '叙事偏好',
  'user_preference.narrative.plots': '固定套路',
  'user_preference.narrative.emotion': '情感模式',
  'user_preference.writing': '写作偏好',
  'user_preference.writing.pacing': '节奏偏好',
}

const CONFIDENCE_COLORS: Record<string, string> = {
  confirmed: 'bg-emerald-900/50 text-emerald-400 border-emerald-700/50',
  pending: 'bg-amber-900/50 text-amber-400 border-amber-700/50',
  suggested: 'bg-zinc-800 text-zinc-500 border-zinc-700',
}

export default function MemoryPanel({ bookId, onToast }: { bookId?: string; onToast?: (msg: string) => void }) {
  const [subTab, setSubTab] = useState('project')
  const [loading, setLoading] = useState(true)
  const [projectData, setProjectData] = useState<Record<string, any> | null>(null)
  const [preferences, setPreferences] = useState<any[]>([])
  const [memoryEnabled, setMemoryEnabled] = useState(true)
  const [prefForm, setPrefForm] = useState({ category: 'user_preference', content: '', summary: '', keywords: '', confidence: 'pending' })
  const [showAddForm, setShowAddForm] = useState(false)
  const [noteForm, setNoteForm] = useState({ title: '', content: '' })
  const [decisionForm, setDecisionForm] = useState({ title: '', rationale: '' })
  const [progressForm, setProgressForm] = useState('')
  const [showNoteForm, setShowNoteForm] = useState(false)
  const [showDecisionForm, setShowDecisionForm] = useState(false)
  const [premise, setPremise] = useState('')
  const [editingPremise, setEditingPremise] = useState(false)

  const showToast = onToast || ((msg: string) => {})

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      if (bookId) {
        const [stats, proj, prefs] = await Promise.all([
          api.getMemoryStats(bookId).catch(() => null),
          api.getProjectMemory(bookId).catch(() => null),
          api.getPreferences().catch(() => ({ total: 0, entries: [], category_counts: {} })),
        ])
        if (stats) setMemoryEnabled(true)
        if (proj) {
          setProjectData(proj)
          setPremise(proj.premise || '')
        }
        setPreferences(prefs.entries || [])
      } else {
        // No book selected — only show preferences
        const prefs = await api.getPreferences().catch(() => ({ total: 0, entries: [], category_counts: {} }))
        setPreferences(prefs.entries || [])
      }
    } catch (e) {
      // Memory might be disabled
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { fetchData() }, [fetchData])

  async function handleToggle(enabled: boolean) {
    try {
      const result = await api.toggleMemory(enabled)
      setMemoryEnabled(result.enabled)
      showToast(result.message)
      if (!result.enabled) {
        setProjectData(null)
        setPreferences([])
      } else {
        fetchData()
      }
    } catch (e) {
      showToast('切换失败')
    }
  }

  async function handleSavePremise() {
    if (!bookId) return
    try {
      await api.updateProjectMemory(bookId, { premise })
      showToast('已保存')
      setEditingPremise(false)
    } catch (e) {
      showToast('保存失败')
    }
  }

  async function handleAddNote() {
    if (!bookId || !noteForm.title) return
    try {
      await api.addNote(bookId, noteForm.title, noteForm.content)
      showToast('笔记已添加')
      setShowNoteForm(false)
      setNoteForm({ title: '', content: '' })
      fetchData()
    } catch (e) {
      showToast('添加失败')
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!bookId || !confirm('确定删除此笔记？')) return
    try {
      await api.deleteNote(bookId, noteId)
      showToast('已删除')
      fetchData()
    } catch (e) {
      showToast('删除失败')
    }
  }

  async function handleAddDecision() {
    if (!bookId || !decisionForm.title) return
    try {
      await api.recordDecision(bookId, decisionForm.title, decisionForm.rationale)
      showToast('决策已记录')
      setShowDecisionForm(false)
      setDecisionForm({ title: '', rationale: '' })
      fetchData()
    } catch (e) {
      showToast('添加失败')
    }
  }

  async function handleDeleteDecision(decisionId: string) {
    if (!bookId || !confirm('确定删除此决策？')) return
    try {
      await api.deleteDecision(bookId, decisionId)
      showToast('已删除')
      fetchData()
    } catch (e) {
      showToast('删除失败')
    }
  }

  async function handleAddProgress() {
    if (!bookId || !progressForm) return
    try {
      await api.addProgress(bookId, progressForm)
      showToast('已记录')
      setProgressForm('')
      fetchData()
    } catch (e) {
      showToast('添加失败')
    }
  }

  async function handleDeleteProgress(noteId: string) {
    if (!bookId || !confirm('确定删除？')) return
    try {
      await api.deleteProgress(bookId, noteId)
      showToast('已删除')
      fetchData()
    } catch (e) {
      showToast('删除失败')
    }
  }

  async function handleAddPreference() {
    if (!prefForm.content) return showToast('请填写内容')
    try {
      const keywords = prefForm.keywords.split(',').map(s => s.trim()).filter(Boolean)
      const result = await api.createPreference({
        category: prefForm.category,
        content: prefForm.content,
        summary: prefForm.summary || prefForm.content.slice(0, 40),
        keywords,
        confidence: prefForm.confidence,
      })
      if (result.ok) {
        showToast('偏好已添加')
        setShowAddForm(false)
        setPrefForm({ category: 'user_preference', content: '', summary: '', keywords: '', confidence: 'pending' })
        fetchData()
      }
    } catch (e) {
      showToast('添加失败')
    }
  }

  async function handleConfirmPref(id: string) {
    try {
      await api.confirmPreference(id)
      showToast('已确认')
      fetchData()
    } catch (e) {
      showToast('确认失败')
    }
  }

  async function handleDeletePref(id: string) {
    if (!confirm('确定删除此偏好？')) return
    try {
      await api.deletePreference(id)
      showToast('已删除')
      fetchData()
    } catch (e) {
      showToast('删除失败')
    }
  }

  function categoryLabel(cat: string): string {
    return CATEGORY_LABELS[cat] || cat.split('.').pop() || cat
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Icon name="loader" size={16} className="animate-spin mr-2 text-zinc-500" />
        <span className="text-xs text-zinc-500">加载中...</span>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Global toggle */}
      <div className="border border-zinc-800 rounded-xl p-3 flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-300">记忆系统</div>
          <div className="text-[10px] text-zinc-500 mt-0.5">
            {memoryEnabled ? '已启用' : '已全局关闭，Agent 完全不知道记忆系统存在'}
          </div>
        </div>
        <Toggle checked={memoryEnabled} onChange={handleToggle} />
      </div>

      {!memoryEnabled ? (
        <div className="text-center text-[11px] text-zinc-600 py-4">
          开启记忆系统后，Agent 会自动加载书籍创作笔记和用户偏好
        </div>
      ) : !bookId ? (
        /* No book selected — show only preferences */
        <div>
          <div className="text-center text-[11px] text-zinc-600 py-2 mb-3">
            书籍创作笔记需要先选择一本书
          </div>
          <PreferencesTab
            preferences={preferences}
            prefForm={prefForm}
            showAddForm={showAddForm}
            onSetPrefForm={setPrefForm}
            onToggleForm={() => setShowAddForm(!showAddForm)}
            onAdd={handleAddPreference}
            onConfirm={handleConfirmPref}
            onDelete={handleDeletePref}
            categoryLabel={categoryLabel}
          />
        </div>
      ) : (
        <>
          {/* Sub tabs */}
          <div className="flex border-b border-zinc-800">
            {[
              { key: 'project', label: '书籍笔记', icon: 'book-open' },
              { key: 'preferences', label: '用户偏好', icon: 'heart' },
            ].map(t => (
              <button
                key={t.key}
                onClick={() => setSubTab(t.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                  subTab === t.key
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <Icon name={t.icon} size={12} /> {t.label}
              </button>
            ))}
          </div>

          {subTab === 'project' && (
            <div className="space-y-3">
              {/* Premise */}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] text-zinc-500">核心设定</div>
                  <button
                    onClick={() => setEditingPremise(!editingPremise)}
                    className="text-zinc-500 hover:text-blue-400 text-[9px]"
                  >
                    <Icon name={editingPremise ? 'x' : 'edit'} size={10} />
                  </button>
                </div>
                {editingPremise ? (
                  <div className="space-y-2">
                    <textarea
                      value={premise}
                      onChange={e => setPremise(e.target.value)}
                      rows={3}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600 resize-none"
                    />
                    <button onClick={handleSavePremise} className="text-[10px] bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded-lg">
                      保存
                    </button>
                  </div>
                ) : (
                  <div className="text-xs text-zinc-300">{projectData?.premise || '(未设置)'}</div>
                )}
              </div>

              {/* Notes */}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] text-zinc-500">创作笔记 ({(projectData?.notes || []).length})</div>
                  <button onClick={() => setShowNoteForm(!showNoteForm)} className="text-zinc-500 hover:text-blue-400 text-[9px]">
                    <Icon name="plus" size={10} />
                  </button>
                </div>
                {showNoteForm && (
                  <div className="space-y-2 mb-3 p-2 rounded-lg bg-zinc-900/50">
                    <input
                      value={noteForm.title} onChange={e => setNoteForm(f => ({ ...f, title: e.target.value }))}
                      placeholder="标题" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none focus:border-blue-600"
                    />
                    <textarea
                      value={noteForm.content} onChange={e => setNoteForm(f => ({ ...f, content: e.target.value }))}
                      placeholder="内容" rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none focus:border-blue-600 resize-none"
                    />
                    <button onClick={handleAddNote} className="text-[10px] bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded-lg">保存</button>
                  </div>
                )}
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {(projectData?.notes || []).map((n: any) => (
                    <div key={n.id} className="flex items-start justify-between gap-2 group text-[11px]">
                      <div className="min-w-0 flex-1">
                        <span className="text-zinc-300 font-medium">{n.title}</span>
                        <div className="text-zinc-500 truncate">{n.content}</div>
                      </div>
                      <button onClick={() => handleDeleteNote(n.id)} className="text-zinc-700 hover:text-red-400 opacity-0 group-hover:opacity-100 shrink-0">
                        <Icon name="x" size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Creative Decisions */}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] text-zinc-500">创作决策 ({(projectData?.creative_decisions || []).length})</div>
                  <button onClick={() => setShowDecisionForm(!showDecisionForm)} className="text-zinc-500 hover:text-blue-400 text-[9px]">
                    <Icon name="plus" size={10} />
                  </button>
                </div>
                {showDecisionForm && (
                  <div className="space-y-2 mb-3 p-2 rounded-lg bg-zinc-900/50">
                    <input
                      value={decisionForm.title} onChange={e => setDecisionForm(f => ({ ...f, title: e.target.value }))}
                      placeholder="决策标题" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none focus:border-blue-600"
                    />
                    <textarea
                      value={decisionForm.rationale} onChange={e => setDecisionForm(f => ({ ...f, rationale: e.target.value }))}
                      placeholder="理由" rows={2} className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none focus:border-blue-600 resize-none"
                    />
                    <button onClick={handleAddDecision} className="text-[10px] bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded-lg">保存</button>
                  </div>
                )}
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {(projectData?.creative_decisions || []).map((d: any) => (
                    <div key={d.id} className="flex items-start justify-between gap-2 group text-[11px]">
                      <div className="min-w-0 flex-1">
                        <span className="text-zinc-300 font-medium">{d.title}</span>
                        <div className="text-zinc-500 truncate">{d.rationale}</div>
                      </div>
                      <button onClick={() => handleDeleteDecision(d.id)} className="text-zinc-700 hover:text-red-400 opacity-0 group-hover:opacity-100 shrink-0">
                        <Icon name="x" size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Progress notes */}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="text-[10px] text-zinc-500 mb-2">写作进度</div>
                <div className="flex gap-2 mb-2">
                  <input
                    value={progressForm} onChange={e => setProgressForm(e.target.value)}
                    placeholder="记录写作进度..." className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
                    onKeyDown={e => e.key === 'Enter' && handleAddProgress()}
                  />
                  <button onClick={handleAddProgress} className="text-[10px] bg-blue-600 hover:bg-blue-500 text-white px-2 py-1 rounded-lg">记录</button>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {(projectData?.progress_notes || []).map((n: any) => (
                    <div key={n.id} className="flex items-start justify-between gap-2 group text-[10px]">
                      <div className="flex items-start gap-1.5 min-w-0">
                        <Icon name="check-circle" size={10} className="text-emerald-500 shrink-0 mt-0.5" />
                        <span className="text-zinc-400">{n.content}</span>
                      </div>
                      <button onClick={() => handleDeleteProgress(n.id)} className="text-zinc-700 hover:text-red-400 opacity-0 group-hover:opacity-100 shrink-0">
                        <Icon name="x" size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {subTab === 'preferences' && (
            <PreferencesTab
              preferences={preferences}
              prefForm={prefForm}
              showAddForm={showAddForm}
              onSetPrefForm={setPrefForm}
              onToggleForm={() => setShowAddForm(!showAddForm)}
              onAdd={handleAddPreference}
              onConfirm={handleConfirmPref}
              onDelete={handleDeletePref}
              categoryLabel={categoryLabel}
            />
          )}
        </>
      )}
    </div>
  )
}

/* ── User Preferences Sub-component ── */

function PreferencesTab({ preferences, prefForm, showAddForm, onSetPrefForm, onToggleForm, onAdd, onConfirm, onDelete, categoryLabel }: {
  preferences: any[]
  prefForm: any
  showAddForm: boolean
  onSetPrefForm: (f: any) => void
  onToggleForm: () => void
  onAdd: () => void
  onConfirm: (id: string) => void
  onDelete: (id: string) => void
  categoryLabel: (c: string) => string
}) {
  return (
    <div className="space-y-3">
      <button onClick={onToggleForm}
        className="w-full border border-dashed border-zinc-700 hover:border-zinc-600 rounded-xl py-2 text-xs text-zinc-500 hover:text-zinc-400 transition-colors"
      >
        <Icon name="plus" size={12} className="inline mr-1" />
        {showAddForm ? '取消' : '添加偏好'}
      </button>

      {showAddForm && (
        <div className="border border-zinc-800 rounded-xl p-3 space-y-2.5">
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">分类</label>
            <select value={prefForm.category} onChange={e => onSetPrefForm({ ...prefForm, category: e.target.value })}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
            >
              <option value="user_preference">通用</option>
              <option value="user_preference.xp.relationship">XP - 关系动力</option>
              <option value="user_preference.xp.archetype">XP - 角色原型</option>
              <option value="user_preference.xp.excluded">XP - 雷区</option>
              <option value="user_preference.narrative.plots">叙事 - 固定套路</option>
              <option value="user_preference.narrative.emotion">叙事 - 情感模式</option>
              <option value="user_preference.writing.pacing">写作 - 节奏偏好</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">内容</label>
            <textarea value={prefForm.content} onChange={e => onSetPrefForm({ ...prefForm, content: e.target.value })}
              placeholder="用户偏好详细描述..." rows={2}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600 resize-none"
            />
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">摘要 (Tier 1 索引显示)</label>
            <input value={prefForm.summary} onChange={e => onSetPrefForm({ ...prefForm, summary: e.target.value })}
              placeholder="一句话摘要..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
            />
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">关键词 (逗号分隔)</label>
            <input value={prefForm.keywords} onChange={e => onSetPrefForm({ ...prefForm, keywords: e.target.value })}
              placeholder="宿敌, 误会, 追妻..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
            />
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">置信度</label>
            <select value={prefForm.confidence} onChange={e => onSetPrefForm({ ...prefForm, confidence: e.target.value })}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
            >
              <option value="confirmed">已确认 (直接生效)</option>
              <option value="pending">待确认 (需用户确认)</option>
            </select>
          </div>
          <button onClick={onAdd} className="w-full bg-blue-600 hover:bg-blue-500 text-white text-xs py-2 rounded-lg font-medium transition-colors">
            保存偏好
          </button>
        </div>
      )}

      {preferences.length === 0 ? (
        <div className="text-center text-[11px] text-zinc-600 py-8">
          暂无用户偏好。添加后，写作时 Agent 会自动匹配关键词注入偏好参考。
        </div>
      ) : (
        <div className="space-y-1.5 max-h-96 overflow-y-auto">
          {preferences.map((p: any) => (
            <div key={p.id} className="border border-zinc-800 rounded-xl p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">{categoryLabel(p.category)}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border ${CONFIDENCE_COLORS[p.confidence] || 'bg-zinc-800 text-zinc-500 border-zinc-700'}`}>
                      {p.confidence}
                    </span>
                  </div>
                  <div className="text-xs text-zinc-200 font-medium truncate">{p.summary}</div>
                  <div className="text-[10px] text-zinc-400 mt-0.5 line-clamp-2">{p.content}</div>
                  {p.keywords?.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {p.keywords.map((kw: string, i: number) => (
                        <span key={i} className="text-[9px] px-1 py-0.5 rounded bg-blue-900/30 text-blue-400">{kw}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {p.confidence === 'pending' && (
                    <button onClick={() => onConfirm(p.id)}
                      className="text-zinc-500 hover:text-emerald-400 p-1 rounded hover:bg-zinc-800" title="确认">
                      <Icon name="check-circle" size={12} />
                    </button>
                  )}
                  <button onClick={() => onDelete(p.id)}
                    className="text-zinc-500 hover:text-red-400 p-1 rounded hover:bg-zinc-800" title="删除">
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
