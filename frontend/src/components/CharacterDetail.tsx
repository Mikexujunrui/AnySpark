import { useState, useMemo } from 'react'
import { api } from "../api"
import Modal from './ui/Modal'
import ConfirmModal from './ui/ConfirmModal'
import Icon from './ui/Icon'
import { triggerRefresh } from "../store"

const PROP_LABELS = {
  appearance: '外貌', personality: '性格', abilities: '能力',
  background: '背景', age: '年龄', status: '状态',
  location: '位置', note: '备注', cultivation: '修为',
  identity: '身份', goal: '目标', secret: '秘密',
  motivation: '驱动力', relationships: '关系状态', growth_note: '成长说明',
  role: '角色定位', description: '描述',
  '核心冲突': '核心冲突', '角色主题': '角色主题', 阶段: '阶段',
}

const PHASE_FIELDS = [
  { key: 'appearance', label: '外貌' },
  { key: 'personality', label: '性格' },
  { key: 'abilities', label: '能力' },
  { key: 'status', label: '状态' },
  { key: 'motivation', label: '驱动力' },
  { key: 'relationships', label: '关系状态' },
  { key: 'growth_note', label: '成长说明' },
]

const EMPTY_PHASE_FORM = {
  phase: '', phase_key: '',
  is_current: true,
  label: '', description: '', time_point: '',
  data: {},
}

function isPhaseSnap(s) {
  return !!s.phase && s.phase !== '未分阶段'
}

export default function CharacterDetail({ character, timelineEvents, bookId, onClose, onUpdated }: { character: Record<string, any>; timelineEvents: any[]; bookId: string; onClose: () => void; onUpdated?: () => void }) {
  const [selectedSnapIdx, setSelectedSnapIdx] = useState(-1)
  const [deleteSnapId, setDeleteSnapId] = useState(null)
  const [showAddPhase, setShowAddPhase] = useState(false)
  const [editingPhaseId, setEditingPhaseId] = useState(null)
  const [phaseForm, setPhaseForm] = useState(EMPTY_PHASE_FORM)
  // ── 编辑/删除角色整体 ──
  const [showEditBase, setShowEditBase] = useState(false)
  const [editForm, setEditForm] = useState({ name: '', aliases: '', data: {} })
  const [editSaving, setEditSaving] = useState(false)
  const [deleteCharId, setDeleteCharId] = useState(null)

  const { phases, legacySnaps } = useMemo(() => {
    const sorted = [...character.snapshots].sort((a, b) => a.timeOrder - b.timeOrder)
    return {
      phases: sorted.filter(isPhaseSnap),
      legacySnaps: sorted.filter(s => !isPhaseSnap(s)),
    }
  }, [character.snapshots])

  const allSnaps = [...phases, ...legacySnaps]
  const selectedSnap = selectedSnapIdx >= 0 ? allSnaps[selectedSnapIdx] : null
  const isInPhaseGroup = selectedSnap && selectedSnapIdx < phases.length

  // When a phase is selected, show that phase's full data; otherwise show
  // the base entity.data (with legacy snapshot patches merged in).
  const displayData = isInPhaseGroup
    ? (selectedSnap.data || {})
    : selectedSnap ? { ...character.data, ...(selectedSnap.data || {}) } : character.data

  const currentPhase = character.snapshots.find(s => s.isCurrent && isPhaseSnap(s))

  function updatePhaseField(field, value) {
    setPhaseForm(prev => ({
      ...prev,
      data: PHASE_FIELDS.some(f => f.key === field)
        ? { ...prev.data, [field]: value }
        : prev.data,
      [field]: value,
    }))
  }

  function openEditPhase(phaseSnap) {
    setEditingPhaseId(phaseSnap.id)
    setPhaseForm({
      phase: phaseSnap.phase || '',
      phase_key: phaseSnap.phaseKey || '',
      is_current: !!phaseSnap.isCurrent,
      label: phaseSnap.label || '',
      description: phaseSnap.description || '',
      time_point: phaseSnap.timePoint || '',
      data: { ...(phaseSnap.data || {}) },
    })
    setShowAddPhase(true)
  }

  async function handleSavePhase() {
    if (!phaseForm.phase) return
    const timeOrder = timelineEvents?.find(e => e.timePoint === phaseForm.time_point)?.timeOrder ?? 0
    const payload = {
      phase: phaseForm.phase,
      phase_key: phaseForm.phase_key || phaseForm.phase.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, ''),
      is_current: phaseForm.is_current,
      label: phaseForm.label || phaseForm.phase,
      description: phaseForm.description,
      time_point: phaseForm.time_point || phaseForm.phase,
      time_order: timeOrder,
      data: phaseForm.data,
    }

    if (editingPhaseId) {
      await fetch(`/api/books/${bookId}/snapshots/${editingPhaseId}`, {
        method: 'PUT',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } else {
      await fetch(`/api/books/${bookId}/characters/${character.id}/snapshots`, {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_entity_id: character.id,
          ...payload,
        }),
      })
    }
    setShowAddPhase(false)
    setEditingPhaseId(null)
    setPhaseForm(EMPTY_PHASE_FORM)
    onUpdated()
  }

  async function handleDeleteSnapshot(snapId) {
    setDeleteSnapId(snapId)
  }

  async function confirmDeleteSnapshot() {
    await fetch(`/api/books/${bookId}/snapshots/${deleteSnapId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    setSelectedSnapIdx(-1)
    setDeleteSnapId(null)
    onUpdated()
  }

  async function setAsCurrent(snapId) {
    await fetch(`/api/books/${bookId}/snapshots/${snapId}`, {
      method: 'PUT',
      headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify({ is_current: true }),
    })
    onUpdated()
  }

  function openEditBase() {
    setEditForm({
      name: character.name || '',
      aliases: (character.aliases || []).join(', '),
      data: { ...(character.data || {}) },
    })
    setShowEditBase(true)
  }

  function updateEditData(key, value) {
    setEditForm(prev => ({ ...prev, data: { ...prev.data, [key]: value } }))
  }

  function removeEditData(key) {
    setEditForm(prev => {
      const next = { ...prev.data }
      delete next[key]
      return { ...prev, data: next }
    })
  }

  async function saveEditBase() {
    if (!editForm.name.trim()) return
    setEditSaving(true)
    try {
      await api.updateEntity(bookId, character.id, {
        name: editForm.name.trim(),
        aliases: editForm.aliases.split(',').map(a => a.trim()).filter(Boolean),
        data: editForm.data,
      })
      setShowEditBase(false)
      triggerRefresh()
      onUpdated()
    } catch (e) {
      console.error(e)
    } finally {
      setEditSaving(false)
    }
  }

  async function confirmDeleteCharacter() {
    try {
      await api.deleteEntity(bookId, character.id)
      setDeleteCharId(null)
      triggerRefresh()
      onClose()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh]">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-3xl max-h-[82vh] overflow-y-auto shadow-2xl">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-zinc-300 text-lg z-10" aria-label="关闭">✕</button>

        <div className="p-6">
          {/* Header */}
          <div className="flex items-center gap-4 mb-6">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-500 to-rose-600 flex items-center justify-center text-2xl shadow-lg shrink-0">
              {character.name[0]}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-xl font-bold">{character.name}</h2>
              {character.aliases?.length > 0 && (
                <p className="text-sm text-zinc-500">{character.aliases.join(' · ')}</p>
              )}
              <div className="flex gap-3 mt-1 text-xs text-zinc-600">
                <span>{character.relationCount} 条关系</span>
                <span>{phases.length} 个阶段</span>
                {legacySnaps.length > 0 && <span>{legacySnaps.length} 个快照</span>}
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={openEditBase}
                className="flex items-center gap-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded-lg transition-colors"
                title="编辑角色基础信息"
              >
                <Icon name="edit" size={12} /> 编辑
              </button>
              <button
                onClick={() => setDeleteCharId(character.id)}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-red-400 bg-zinc-800/50 hover:bg-red-950/40 px-3 py-1.5 rounded-lg transition-colors"
                title="删除角色"
              >
                <Icon name="trash" size={12} /> 删除
              </button>
            </div>
          </div>

          {/* Current Phase badge */}
          {currentPhase && (
            <div className="mb-4 px-4 py-2 rounded-lg bg-sky-950/30 border border-sky-800/40 flex items-center gap-2 text-xs">
              <Icon name="zap" size={12} className="text-sky-400" />
              <span className="text-sky-300">当前写作阶段:</span>
              <span className="text-zinc-200 font-semibold">{currentPhase.phase}</span>
            </div>
          )}

          {/* ── Phase Timeline ── */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
                <Icon name="trending-up" size={14} className="text-sky-400" /> 角色阶段
              </h3>
              <button
                onClick={() => { setEditingPhaseId(null); setPhaseForm(EMPTY_PHASE_FORM); setShowAddPhase(true) }}
                className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1 rounded-lg transition-colors flex items-center gap-1.5"
              >
                <Icon name="plus" size={12} /> 新阶段
              </button>
            </div>

            {phases.length === 0 && !showAddPhase && (
              <div className="border border-dashed border-zinc-800 rounded-xl p-6 text-center">
                <p className="text-sm text-zinc-500 mb-1">尚未划分阶段</p>
                <p className="text-xs text-zinc-600">
                  为有重大弧光的角色划分阶段（如 第一部·觉醒 / 第二部·暗流 / 第三部·救赎），<br />
                  阶段不绑定具体章节，写作时自动注入「当前阶段」的角色卡。
                </p>
              </div>
            )}

            {phases.length > 0 && (
              <div className="relative pl-5">
                {/* Vertical connector line */}
                <div className="absolute left-[9px] top-2 bottom-2 w-0.5 bg-gradient-to-b from-sky-500/50 via-zinc-700 to-zinc-800" />
                {phases.map((phase, i) => {
                  const idx = i
                  const isSelected = selectedSnapIdx === idx
                  const isCurrent = phase.isCurrent
                  return (
                    <div key={phase.id} className="relative mb-3 last:mb-0">
                      {/* Node dot */}
                      <div
                        className={`absolute left-[-15px] top-4 w-[17px] h-[17px] rounded-full border-2 transition-all ${
                          isCurrent
                            ? 'bg-sky-400 border-sky-300 shadow-[0_0_8px_rgba(56,189,248,0.6)]'
                            : isSelected
                            ? 'bg-emerald-500 border-emerald-300'
                            : 'bg-zinc-800 border-zinc-600 hover:border-zinc-400'
                        }`}
                      />
                      <button
                        onClick={() => setSelectedSnapIdx(isSelected ? -1 : idx)}
                        className={`w-full text-left rounded-xl px-4 py-3 border transition-all ${
                          isSelected
                            ? 'border-sky-700 bg-sky-950/30 shadow-md'
                            : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-800/40'
                        }`}
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className={`text-sm font-semibold ${isCurrent ? 'text-sky-300' : 'text-zinc-200'}`}>
                            {phase.phase || phase.label}
                          </h4>
                          {isCurrent && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-900/60 text-sky-300 border border-sky-800/50">
                              当前
                            </span>
                          )}
                          {!isCurrent && (
                            <span
                              onClick={(e) => { e.stopPropagation(); setAsCurrent(phase.id) }}
                              className="text-[10px] text-zinc-600 hover:text-sky-400 px-1.5 py-0.5 rounded cursor-pointer transition-colors"
                              title="设为当前写作阶段"
                            >
                              设为当前
                            </span>
                          )}
                        </div>
                        {phase.description && (
                          <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{phase.description}</p>
                        )}
                        {/* Growth note between phases */}
                        {i > 0 && phases[i - 1].data?.growth_note && (
                          <div className="mt-2 pt-2 border-t border-zinc-800/60 flex items-start gap-1.5">
                            <Icon name="trending-up" size={10} className="text-amber-400 mt-0.5 shrink-0" />
                            <span className="text-[10px] text-amber-400/80 italic">
                              {phases[i - 1].data.growth_note}
                            </span>
                          </div>
                        )}
                        {isSelected && (
                          <div className="mt-3 flex gap-2 justify-end pt-2 border-t border-zinc-800/60">
                            <button
                              onClick={(e) => { e.stopPropagation(); openEditPhase(phase) }}
                              className="text-xs text-zinc-400 hover:text-zinc-200 px-2 py-1"
                            >编辑</button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDeleteSnapshot(phase.id) }}
                              className="text-xs text-zinc-600 hover:text-red-400 px-2 py-1"
                            >删除</button>
                          </div>
                        )}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── Phase full settings: shown when a phase is selected ── */}
          {isInPhaseGroup && (
            <div className="mb-6 border border-zinc-800 rounded-xl p-4 bg-zinc-950/30">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Icon name="user" size={12} /> 阶段角色卡
                </h4>
                <span className="text-[10px] text-zinc-600">{selectedSnap.phase}</span>
              </div>
              {/* Render grouped card sections if available, fall back to flat grid */}
              {(selectedSnap.card?.length > 0
                ? selectedSnap.card.map(group => (
                    <div key={group.group} className="mb-4 last:mb-0">
                      <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 border-b border-zinc-800 pb-1">{group.group}</p>
                      <div className="grid grid-cols-2 gap-3">
                        {group.items.map(item => {
                          const isLong = typeof item.value === 'string' && item.value.length > 100
                          return (
                            <div key={item.key} className={`rounded-lg p-3 border border-zinc-800 bg-zinc-900/50 ${isLong ? 'col-span-2' : ''}`}>
                              <p className="text-[10px] text-zinc-500 mb-0.5">{item.label}</p>
                              <p className="text-sm text-zinc-200 whitespace-pre-wrap">{item.value}</p>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))
                : Object.entries(displayData).map(([k, v]) => {
                    if (!v) return null
                    const label = PROP_LABELS[k] || k
                    const isLong = typeof v === 'string' && v.length > 100
                    return (
                      <div key={k} className={`rounded-lg p-3 border border-zinc-800 bg-zinc-900/50 ${isLong ? 'col-span-2' : ''}`}>
                        <p className="text-[10px] text-zinc-500 mb-0.5">{label}</p>
                        <p className="text-sm text-zinc-200 whitespace-pre-wrap">{String(v)}</p>
                      </div>
                    )
                  })
              )}
              {Object.keys(displayData).length === 0 && (!selectedSnap.card || selectedSnap.card.length === 0) && (
                <p className="text-xs text-zinc-600 text-center py-4">该阶段尚未填写属性</p>
              )}
            </div>
          )}

          {/* ── Base Properties (when nothing / legacy selected) ── */}
          {!isInPhaseGroup && (
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5">
                  <Icon name="user" size={14} /> 基础设定
                </h3>
                {selectedSnap && (
                  <span className="text-[10px] text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">
                    + 快照 {selectedSnap.label || selectedSnap.timePoint}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(displayData).map(([k, v]) => {
                  if (!v || k === 'age') return null
                  const label = PROP_LABELS[k] || k
                  const changed = selectedSnap && selectedSnap.data?.[k] && character.data?.[k] !== selectedSnap.data[k]
                  return (
                    <div key={k} className={`rounded-lg p-3 border ${changed ? 'border-blue-800 bg-blue-950/30' : 'border-zinc-800 bg-zinc-800/30'}`}>
                      <p className="text-[10px] text-zinc-500 mb-0.5 flex items-center gap-1">
                        {label}
                        {changed && <span className="text-blue-400">*</span>}
                      </p>
                      <p className="text-sm text-zinc-200">{String(v)}</p>
                    </div>
                  )
                })}
                {character.data.age && (
                  <div className="rounded-lg p-3 border border-zinc-800 bg-zinc-800/30">
                    <p className="text-[10px] text-zinc-500 mb-0.5">年龄</p>
                    <p className="text-sm text-zinc-200">{character.data.age}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Relationships */}
          {character.relations?.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-1.5"><Icon name="link" size={14} /> 关系</h3>
              <div className="space-y-2">
                {character.relations.map(r => (
                  <div key={r.id} className="flex items-center gap-2 text-xs bg-zinc-800/30 border border-zinc-800 rounded-lg px-3 py-2">
                    <span className="text-zinc-500">{r.direction === 'out' ? '→' : '←'}</span>
                    <span className="text-zinc-400 bg-zinc-700/50 px-2 py-0.5 rounded">[{r.type}]</span>
                    <span className="text-zinc-200">{r.targetName}</span>
                    {r.timePoint && (
                      <span className="text-zinc-600 ml-auto">{r.timePoint}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Legacy snapshots (backward compat) ── */}
          {legacySnaps.length > 0 && (
            <div className="mb-6 bg-zinc-800/30 rounded-xl p-4 border border-zinc-800">
              <h3 className="text-sm font-semibold text-zinc-400 mb-2 flex items-center gap-1.5">
                <Icon name="hourglass" size={14} /> 旧版快照 ({legacySnaps.length})
              </h3>
              <div className="flex gap-2 flex-wrap">
                {legacySnaps.map((snap) => {
                  const idx = phases.length + legacySnaps.indexOf(snap)
                  const isSelected = selectedSnapIdx === idx
                  return (
                    <button
                      key={snap.id}
                      onClick={() => setSelectedSnapIdx(isSelected ? -1 : idx)}
                      className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                        isSelected
                          ? 'bg-blue-600 text-white'
                          : 'bg-zinc-700/50 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                      }`}
                    >
                      {snap.label || snap.timePoint}
                      <span onClick={(e) => { e.stopPropagation(); handleDeleteSnapshot(snap.id) }}
                        className="ml-2 text-zinc-500 hover:text-red-400">✕</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* ── Add/Edit Phase Form ── */}
          {showAddPhase && (
            <div className="border border-zinc-700 rounded-xl p-5 space-y-4 bg-zinc-900/50">
              <h4 className="text-sm font-semibold text-zinc-200 flex items-center gap-1.5">
                <Icon name="trending-up" size={14} />
                {editingPhaseId ? '编辑阶段' : '新增阶段'}
              </h4>

              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">阶段名 <span className="text-red-400">*</span></label>
                <input
                  value={phaseForm.phase}
                  onChange={e => updatePhaseField('phase', e.target.value)}
                  placeholder="如：第一部·觉醒 / 复仇期 / 救赎期"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-zinc-400 mb-1 block">阶段 key (可选)</label>
                  <input
                    value={phaseForm.phase_key}
                    onChange={e => updatePhaseField('phase_key', e.target.value)}
                    placeholder="arc1"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-400 mb-1 block">关联时间节点</label>
                  <select
                    value={phaseForm.time_point}
                    onChange={e => updatePhaseField('time_point', e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200"
                  >
                    <option value="">不关联</option>
                    {(timelineEvents || []).map(ev => (
                      <option key={ev.timePoint} value={ev.timePoint}>{ev.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2 mt-5">
                  <input
                    type="checkbox"
                    id="is_current"
                    checked={phaseForm.is_current}
                    onChange={e => updatePhaseField('is_current', e.target.checked)}
                    className="rounded bg-zinc-800 border-zinc-700"
                  />
                  <label htmlFor="is_current" className="text-xs text-zinc-300">标记为当前写作阶段</label>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">阶段卡片属性</label>
                <div className="grid grid-cols-2 gap-2">
                  {PHASE_FIELDS.map(({ key, label }) => (
                    PHASE_FIELDS.slice(-3).some(f => f.key === key) ? (
                      <div key={key} className="col-span-2">
                        <label className="text-[10px] text-zinc-500">{label}</label>
                        <textarea
                          value={phaseForm.data[key] || ''}
                          onChange={e => updatePhaseField(key, e.target.value)}
                          rows={2}
                          placeholder={`${label}...`}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 mt-0.5 resize-none"
                        />
                      </div>
                    ) : (
                      <div key={key}>
                        <label className="text-[10px] text-zinc-500">{label}</label>
                        <input
                          value={phaseForm.data[key] || ''}
                          onChange={e => updatePhaseField(key, e.target.value)}
                          placeholder={`${label}...`}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 mt-0.5"
                        />
                      </div>
                    )
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] text-zinc-400 mb-1 block">阶段叙事说明</label>
                <textarea
                  value={phaseForm.description}
                  onChange={e => updatePhaseField('description', e.target.value)}
                  placeholder="一句话概括角色在本阶段的状态..."
                  rows={2}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 resize-none"
                />
              </div>

              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setShowAddPhase(false); setEditingPhaseId(null); setPhaseForm(EMPTY_PHASE_FORM) }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5">取消</button>
                <button
                  onClick={handleSavePhase}
                  className="text-xs bg-accent text-white rounded-lg px-4 py-1.5 font-medium hover:bg-accent-hover disabled:opacity-50"
                  disabled={!phaseForm.phase}>
                  {editingPhaseId ? '保存修改' : '创建阶段'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!deleteSnapId}
        title="删除阶段"
        message="确定删除此阶段？此操作不可撤销。"
        danger
        onConfirm={confirmDeleteSnapshot}
        onCancel={() => setDeleteSnapId(null)}
      />

      <ConfirmModal
        open={!!deleteCharId}
        title="删除角色"
        message={`确定删除「${character.name}」？该角色的所有阶段、快照、关系都会一并删除，此操作不可撤销。`}
        danger
        confirmText="删除角色"
        onConfirm={confirmDeleteCharacter}
        onCancel={() => setDeleteCharId(null)}
      />

      {showEditBase && (
        <EditCharacterModal
          form={editForm}
          setForm={setEditForm}
          onCancel={() => setShowEditBase(false)}
          onSave={saveEditBase}
          saving={editSaving}
          onUpdateData={updateEditData}
          onRemoveData={removeEditData}
        />
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Edit character base info modal (name / aliases / data dict)
// ──────────────────────────────────────────────────────────────────────────

function EditCharacterModal({ form, setForm, onCancel, onSave, saving, onUpdateData, onRemoveData }) {
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  function handleAddField() {
    if (!newKey.trim()) return
    onUpdateData(newKey.trim(), newValue)
    setNewKey('')
    setNewValue('')
  }

  const entries = Object.entries(form.data || {}).filter(([k]) => k && k !== 'name' && k !== 'aliases')
  const COMMON_CHARS_FIELDS = [
    { key: 'appearance', label: '外貌' },
    { key: 'personality', label: '性格' },
    { key: 'abilities', label: '能力' },
    { key: 'background', label: '背景' },
    { key: 'age', label: '年龄' },
    { key: 'status', label: '状态' },
    { key: 'motivation', label: '驱动力' },
    { key: 'identity', label: '身份' },
    { key: 'goal', label: '目标' },
    { key: 'secret', label: '秘密' },
    { key: 'location', label: '位置' },
  ]
  const commonNotInData = COMMON_CHARS_FIELDS.filter(f => !form.data?.[f.key])

  return (
    <Modal open onClose={onCancel} title="编辑角色基础信息" size="lg">
      <div className="p-6 space-y-4 max-h-[72vh] overflow-y-auto">
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">名称 <span className="text-red-400">*</span></label>
          <input
            value={form.name}
            onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
          />
        </div>
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">别名（逗号分隔）</label>
          <input
            value={form.aliases}
            onChange={e => setForm(prev => ({ ...prev, aliases: e.target.value }))}
            placeholder="别名1, 别名2, ..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider">属性字段</label>
            {commonNotInData.length > 0 && (
              <select
                value=""
                onChange={e => {
                  if (e.target.value) {
                    onUpdateData(e.target.value, '')
                    e.target.value = ''
                  }
                }}
                className="text-[10px] bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300"
              >
                <option value="">+ 添加常用字段</option>
                {commonNotInData.map(f => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </select>
            )}
          </div>
          {entries.map(([k, v]) => {
            const isLong = typeof v === 'string' && v.length > 60
            const commonInfo = COMMON_CHARS_FIELDS.find(f => f.key === k)
            const label = commonInfo?.label || k
            return (
              <div key={k} className="flex gap-2 items-start">
                <input
                  value={k}
                  onChange={(e) => {
                    const newK = e.target.value
                    if (newK !== k) {
                      onRemoveData(k)
                      onUpdateData(newK, v)
                    }
                  }}
                  title="修改字段名"
                  className="w-24 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300 shrink-0"
                />
                {isLong ? (
                  <textarea
                    value={v || ''}
                    onChange={(e) => onUpdateData(k, e.target.value)}
                    placeholder={label}
                    rows={3}
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300 resize-none"
                  />
                ) : (
                  <input
                    value={String(v || '')}
                    onChange={(e) => onUpdateData(k, e.target.value)}
                    placeholder={label}
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300"
                  />
                )}
                <button
                  onClick={() => onRemoveData(k)}
                  aria-label="移除字段"
                  className="text-zinc-600 hover:text-red-400 px-2 py-1.5 text-xs shrink-0"
                >✕</button>
              </div>
            )
          })}
          <div className="flex gap-2 items-start pt-2 border-t border-zinc-800">
            <input
              value={newKey}
              onChange={e => setNewKey(e.target.value)}
              placeholder="自定义字段名..."
              className="w-28 bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 shrink-0"
            />
            <input
              value={newValue}
              onChange={e => setNewValue(e.target.value)}
              placeholder="字段值..."
              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddField())}
              className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200"
            />
            <button
              onClick={handleAddField}
              disabled={!newKey.trim()}
              className="text-accent hover:text-accent-hover px-2 py-1.5 text-xs shrink-0 disabled:opacity-40"
            >+ 添加</button>
          </div>
        </div>

        <div className="flex gap-2 justify-end pt-3 border-t border-zinc-800">
          <button
            onClick={onCancel}
            className="text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5"
          >取消</button>
          <button
            onClick={onSave}
            disabled={saving || !form.name.trim()}
            className="text-xs bg-accent text-white rounded-lg px-4 py-1.5 font-medium hover:bg-accent-hover disabled:opacity-50"
          >
            {saving ? '保存中...' : '保存修改'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
