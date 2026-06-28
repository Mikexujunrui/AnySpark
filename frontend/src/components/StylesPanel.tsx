import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/Toast'

const PRIORITY_LABELS = { suggest: '建议', apply: '应用', strict: '严格' }
const PRIORITY_COLORS = {
  suggest: 'bg-zinc-700 text-zinc-400',
  apply: 'bg-amber-900/50 text-amber-400',
  strict: 'bg-red-900/50 text-red-400',
}
const SOURCE_COLORS = {
  system: 'from-indigo-600 to-blue-500',
  user: 'from-emerald-600 to-teal-500',
}
const POV_LABELS = {
  third_person_limited: '第三人称限知',
  third_person_cinematic: '电影化第三人称',
  third_person_omniscient: '第三人称全知',
  first_person: '第一人称',
}
const PACING_LABELS = {
  three_act: '三幕式',
  roller_coaster: '过山车式',
  slow_burn: '慢热型',
}

export default function StylesPanel({ bookId }) {
  const [styles, setStyles] = useState([])
  const [activeStyle, setActiveStyle] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [creating, setCreating] = useState(false)
  const [editForm, setEditForm] = useState(null)
  const [editingNarrative, setEditingNarrative] = useState(false)
  const [narrativeForm, setNarrativeForm] = useState<any>({})
  const [narrativeLoading, setNarrativeLoading] = useState(false)

  // Load narrative strategy for active style
  const loadNarrative = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/style/narrative`)
      const data = await res.json()
      setNarrativeForm({
        pov: data.pov || '',
        pacing_curve: data.pacing_curve || '',
        reveal_density: data.reveal_density || '',
        foreshadow_budget: data.foreshadow_budget || 3,
        chapter_arc: data.chapter_arc || '',
        tone_guidance: data.tone_guidance || '',
      })
    } catch (_) {}
  }, [bookId])

  const saveNarrative = useCallback(async () => {
    setNarrativeLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/style/narrative`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(narrativeForm),
      })
      if (res.ok) {
        showToast('叙事策略已保存', 'success')
        setEditingNarrative(false)
      } else {
        showToast('保存失败', 'error')
      }
    } catch (_) { showToast('保存失败', 'error') }
    setNarrativeLoading(false)
  }, [bookId, narrativeForm])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [stylesData, activeData] = await Promise.all([
        api.getStyles(),
        api.getActiveStyle(bookId),
      ])
      setStyles(Array.isArray((stylesData as any)?.styles) ? (stylesData as any).styles : [])
      setActiveStyle((activeData as any)?.active || '')
    } catch (e) {
      showToast('加载文风列表失败', 'error')
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadData() }, [loadData])

  async function handleSetActive(name) {
    try {
      await api.setActiveStyle(bookId, name)
      setActiveStyle(name)
      setExpanded(null)
      showToast(`活跃文风已切换为「${name}」`, 'success')
    } catch (e) {
      showToast('设置失败', 'error')
    }
  }

  async function handleDelete(name) {
    try {
      await api.deleteStyle(name)
      loadData()
      showToast(`已删除「${name}」`, 'success')
    } catch (e) {
      showToast('删除失败（系统文风不可删除）', 'error')
    }
  }

  async function handleCreate(formData) {
    try {
      await api.createStyle(formData)
      setCreating(false)
      loadData()
      showToast(`文风「${formData.name}」已创建`, 'success')
    } catch (e) {
      showToast('创建失败', 'error')
    }
  }

  if (loading) return <LoadingState text="加载文风库..." />

  const activeStyleObj = styles.find(s => s.name === activeStyle)

  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Icon name="pen-tool" size={20} /> 文风库
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            {activeStyle ? (
              <>当前活跃: <span className="text-amber-400 font-medium">{activeStyle}</span></>
            ) : (
              '点击风格卡片可设为活跃，活跃风格会自动注入写作上下文'
            )}
          </p>
        </div>
        <button onClick={() => setCreating(!creating)}
          className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-2">
          <Icon name="plus" size={14} /> 创建文风
        </button>
      </header>

      {/* Active style detail */}
      {activeStyleObj && (
        <div className="mb-6 bg-amber-900/10 border border-amber-900/30 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-amber-300 flex items-center gap-2">
              <Icon name="zap" size={14} /> 当前活跃: {activeStyleObj.name}
            </h3>
            <button onClick={() => handleSetActive('')}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              取消活跃
            </button>
          </div>
          <p className="text-xs text-zinc-400 mb-2">{activeStyleObj.description}</p>
          {activeStyleObj.slots && activeStyleObj.slots.length > 0 && (
            <div className="space-y-2 mt-3">
              {activeStyleObj.slots.map((slot, i) => (
                <div key={i} className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-3">
                  <div className="text-[10px] text-amber-500 mb-1 font-semibold">{slot.target}:</div>
                  <p className="text-xs text-zinc-300 leading-relaxed">{slot.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create form */}
      {creating && (
        <StyleForm
          onSave={handleCreate}
          onCancel={() => setCreating(false)}
          initial={{}}
        />
      )}

      {/* Style grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {styles.map((style) => {
          const isActive = style.name === activeStyle
          const isExpanded = expanded === style.name

          return (
            <div key={style.name}
              className={`relative group bg-zinc-900 border rounded-xl overflow-hidden transition-colors ${
                isActive ? 'border-amber-700/60 ring-1 ring-amber-800/40' : 'border-zinc-800 hover:border-zinc-700'
              }`}
            >
              <div className={`h-1.5 bg-gradient-to-r ${SOURCE_COLORS[style.source] || SOURCE_COLORS.user}`} />
              <div className="p-4">
                <div className="flex items-start justify-between mb-1.5">
                  <h3 className="text-sm font-semibold text-zinc-200">{style.name}</h3>
                  {isActive && (
                    <span className="shrink-0 text-[9px] bg-amber-900/50 text-amber-400 px-1.5 py-0.5 rounded">
                      活跃
                    </span>
                  )}
                </div>
                <p className="text-xs text-zinc-500 mb-2.5 leading-relaxed line-clamp-2">
                  {style.description}
                </p>

                <div className="flex flex-wrap gap-1 mb-2.5">
                  {style.applies_to && style.applies_to.map((tag) => (
                    <span key={tag} className="text-[9px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
                      {tag}
                    </span>
                  ))}
                </div>

                {/* Narrative Strategy */}
                {style.narrative_strategy && (
                  <div className="flex flex-wrap items-center gap-1.5 mb-2.5 text-[9px]">
                    <span className="text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded flex items-center gap-1" title="POV视角">
                      👁 {POV_LABELS[style.narrative_strategy.pov] || style.narrative_strategy.pov}
                    </span>
                    <span className="text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded" title="节奏曲线">
                      📈 {PACING_LABELS[style.narrative_strategy.pacing_curve] || style.narrative_strategy.pacing_curve}
                    </span>
                    {style.narrative_strategy.foreshadow_budget > 0 && (
                      <span className="text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded" title="每章伏笔预算">
                        🎯 {style.narrative_strategy.foreshadow_budget}
                      </span>
                    )}
                    {style.narrative_strategy.reveal_density && (
                      <span className="text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded" title="信息密度">
                        📊 {style.narrative_strategy.reveal_density}
                      </span>
                    )}
                    {style.narrative_strategy.chapter_arc && (
                      <span className="text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded" title="章节弧线">
                        🎬 {style.narrative_strategy.chapter_arc}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-2 mb-2.5 text-[10px]">
                  <span className={PRIORITY_COLORS[style.priority] || 'bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded'}>
                    {PRIORITY_LABELS[style.priority] || style.priority}
                  </span>
                  <span className="text-zinc-600">
                    {style.source === 'system' ? '系统' : '自定义'}
                  </span>
                  <span className="text-zinc-600">
                    {style.slots?.length || 0} 条提示
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {!isActive && (
                    <button onClick={() => handleSetActive(style.name)}
                      className="text-xs text-zinc-500 hover:text-amber-400 transition-colors flex items-center gap-1">
                      <Icon name="check" size={10} /> 设为活跃
                    </button>
                  )}
                  <button onClick={() => setExpanded(isExpanded ? null : style.name)}
                    className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors ml-auto">
                    {isExpanded ? '收起' : '详情'}
                  </button>
                  {style.source === 'user' && (
                    <button onClick={() => handleDelete(style.name)}
                      className="text-xs text-zinc-600 hover:text-red-400 transition-colors flex items-center gap-1">
                      <Icon name="trash" size={10} />
                    </button>
                  )}
                </div>

                {isExpanded && style.slots && (
                  <div className="mt-3 pt-3 border-t border-zinc-800 space-y-2">
                    {style.slots.map((slot, i) => (
                      <div key={i} className="bg-zinc-800/50 rounded-lg p-2.5">
                        <div className="text-[9px] text-zinc-500 mb-0.5 font-semibold">{slot.target}:</div>
                        <p className="text-[10px] text-zinc-300 leading-relaxed">{slot.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {styles.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
          <Icon name="pen-tool" size={36} className="mb-3 text-zinc-700" />
          <p className="text-sm mb-1">文风库为空</p>
          <p className="text-xs">点击上方"创建文风"按钮添加自定义风格</p>
        </div>
      )}

      {/* ── Narrative Strategy Editor ── */}
      <div className="border-t border-zinc-800 mt-4 pt-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Icon name="pen-tool" size={14} /> 叙事导演
          </span>
          {!editingNarrative ? (
            <button onClick={() => setEditingNarrative(true)}
              className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded transition-colors">
              编辑策略
            </button>
          ) : (
            <div className="flex gap-1">
              <button onClick={() => setEditingNarrative(false)}
                className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded transition-colors">取消</button>
              <button onClick={saveNarrative} disabled={narrativeLoading}
                className="text-xs bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white px-3 py-1 rounded transition-colors">
                {narrativeLoading ? '保存中...' : '保存'}
              </button>
            </div>
          )}
        </div>

        {editingNarrative ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">叙述视角</label>
                <select value={narrativeForm.pov} onChange={e => setNarrativeForm(f => ({...f, pov: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                  <option value="">默认</option>
                  <option value="first_person">第一人称</option>
                  <option value="third_person_limited">第三人称限知</option>
                  <option value="third_person_omniscient">第三人称全知</option>
                  <option value="third_person_cinematic">电影化第三人称</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">节奏曲线</label>
                <select value={narrativeForm.pacing_curve} onChange={e => setNarrativeForm(f => ({...f, pacing_curve: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                  <option value="">默认</option>
                  <option value="three_act">三幕式</option>
                  <option value="roller_coaster">过山车式</option>
                  <option value="slow_burn">慢热型</option>
                  <option value="fast_paced">快节奏</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">信息密度</label>
                <select value={narrativeForm.reveal_density} onChange={e => setNarrativeForm(f => ({...f, reveal_density: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                  <option value="">默认</option>
                  <option value="sparse">稀疏 — 逐步揭示</option>
                  <option value="moderate">适中 — 平衡节奏</option>
                  <option value="dense">密集 — 信息丰富</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">章节弧线</label>
                <select value={narrativeForm.chapter_arc} onChange={e => setNarrativeForm(f => ({...f, chapter_arc: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
                  <option value="">默认</option>
                  <option value="rising_action">上升行动</option>
                  <option value="climax">高潮</option>
                  <option value="resolution">解决</option>
                  <option value="standalone">独立篇章</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">伏笔预算 (每章)</label>
                <input type="number" min={0} max={10} value={narrativeForm.foreshadow_budget}
                  onChange={e => setNarrativeForm(f => ({...f, foreshadow_budget: parseInt(e.target.value) || 0}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500" />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">语调指引</label>
                <input type="text" value={narrativeForm.tone_guidance} placeholder="如：紧张、悬疑、温情..."
                  onChange={e => setNarrativeForm(f => ({...f, tone_guidance: e.target.value}))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500" />
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-zinc-600">
            {narrativeForm.pov ? (
              <div className="flex flex-wrap gap-1.5">
                {narrativeForm.pov && <span className="bg-zinc-800/60 px-2 py-1 rounded">👁 {POV_LABELS[narrativeForm.pov] || narrativeForm.pov}</span>}
                {narrativeForm.pacing_curve && <span className="bg-zinc-800/60 px-2 py-1 rounded">📈 {PACING_LABELS[narrativeForm.pacing_curve] || narrativeForm.pacing_curve}</span>}
                {narrativeForm.reveal_density && <span className="bg-zinc-800/60 px-2 py-1 rounded">📊 {narrativeForm.reveal_density}</span>}
                {narrativeForm.chapter_arc && <span className="bg-zinc-800/60 px-2 py-1 rounded">🎬 {narrativeForm.chapter_arc}</span>}
                {(narrativeForm.foreshadow_budget || 0) > 0 && <span className="bg-zinc-800/60 px-2 py-1 rounded">🎯 伏笔×{narrativeForm.foreshadow_budget}</span>}
                {narrativeForm.tone_guidance && <span className="bg-zinc-800/60 px-2 py-1 rounded">🎭 {narrativeForm.tone_guidance}</span>}
              </div>
            ) : (
              '点击"编辑策略"配置叙事导演参数'
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StyleForm({ onSave, onCancel, initial }) {
  const [name, setName] = useState(initial?.name || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [priority, setPriority] = useState(initial?.priority || 'apply')
  const [tags, setTags] = useState(initial?.applies_to?.join('、') || '')
  const [slotsText, setSlotsText] = useState(
    initial?.slots?.map(s => `${s.target}: ${s.content}`).join('\n') || 'system: \nscene: \nknowledge: '
  )

  function buildData() {
    const applies_to = tags.split(/[,，、\s]+/).filter(Boolean)
    const slots = slotsText.split('\n').filter(line => line.includes(':')).map(line => {
      const idx = line.indexOf(':')
      return { target: line.slice(0, idx).trim(), content: line.slice(idx + 1).trim() }
    })
    return { name, description, priority, applies_to, slots }
  }

  return (
    <div className="mb-6 bg-zinc-900 border border-zinc-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-zinc-200 mb-4">
        {initial ? '编辑文风' : '新建文风'}
      </h3>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="text-[10px] text-zinc-500 mb-1 block">名称（英文ID）</label>
          <input value={name} onChange={e => setName(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
            placeholder="如: suspense" />
        </div>
        <div>
          <label className="text-[10px] text-zinc-500 mb-1 block">优先级</label>
          <select value={priority} onChange={e => setPriority(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none">
            <option value="suggest">建议 (suggest)</option>
            <option value="apply">应用 (apply)</option>
            <option value="strict">严格 (strict)</option>
          </select>
        </div>
      </div>
      <div className="mb-3">
        <label className="text-[10px] text-zinc-500 mb-1 block">描述</label>
        <input value={description} onChange={e => setDescription(e.target.value)}
          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
          placeholder="简要描述此风格的特点" />
      </div>
      <div className="mb-3">
        <label className="text-[10px] text-zinc-500 mb-1 block">适用场景标签（用逗号分隔）</label>
        <input value={tags} onChange={e => setTags(e.target.value)}
          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
          placeholder="如: 战斗、悬疑、日常、高潮" />
      </div>
      <div className="mb-3">
        <label className="text-[10px] text-zinc-500 mb-1 block">提示词槽位（每行一个，格式: 目标: 内容）</label>
        <textarea value={slotsText} onChange={e => setSlotsText(e.target.value)}
          rows={4}
          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500 font-mono resize-none"
          placeholder="system: 使用短句...&#10;scene: 战斗场景时..." />
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onCancel}
          className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-1.5 rounded-lg text-xs transition-colors">
          取消
        </button>
        <button onClick={() => onSave(buildData())}
          disabled={!name}
          className="bg-zinc-200 text-zinc-900 px-4 py-1.5 rounded-lg text-xs font-medium hover:bg-white transition-colors disabled:opacity-40">
          保存
        </button>
      </div>
    </div>
  )
}
