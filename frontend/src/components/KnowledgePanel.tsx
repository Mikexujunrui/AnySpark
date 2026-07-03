import { useState, useEffect } from 'react'
import { api } from "../api"
import Icon from './ui/Icon'
import Modal from './ui/Modal'
import ConfirmModal from './ui/ConfirmModal'
import LoadingState from './ui/Skeleton'
import { useRefreshKey, triggerRefresh } from "../store"
import FullGraphView from './FullGraphView'

const TYPE_LABELS = {
  character: { icon: 'user', label: '人物' },
  location: { icon: 'map-pin', label: '地点' },
  item: { icon: 'sword', label: '物品' },
  skill: { icon: 'zap', label: '技能/功法' },
  organization: { icon: 'building', label: '组织' },
  race: { icon: 'users', label: '种族' },
  concept: { icon: 'lightbulb', label: '概念' },
  event: { icon: 'calendar', label: '事件' },
}
const TYPE_ORDER = ['character', 'location', 'item', 'skill', 'organization', 'race', 'concept', 'event']

const FIELD_SECTIONS = {
  character: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'age', 'gender', 'species'] },
    { key: '外貌', label: '外貌特征', fields: ['appearance', 'hair', 'eyes', 'height', 'build', 'clothing', 'distinctive_marks'] },
    { key: '性格', label: '性格', fields: ['personality', 'temperament', 'inner_conflict', 'motivation', 'fears', 'quirks', 'likes', 'dislikes'] },
    { key: '能力', label: '能力/功法', fields: ['cultivation_level', 'cultivation_method', 'techniques', 'powers', 'special_items', 'combat_style'] },
    { key: '背景', label: '背景经历', fields: ['origin', 'background', 'key_experiences', 'secrets', 'traumas', 'goals', 'regrets', 'identity'] },
    { key: '状态', label: '当前状态', fields: ['current_location', 'current_condition', 'social_standing', 'reputation'] },
  ],
  location: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'location_type'] },
    { key: '地理', label: '地理环境', fields: ['region', 'parent_location', 'climate', 'terrain', 'landmarks', 'resources'] },
    { key: '社会', label: '社会人文', fields: ['population', 'ruler', 'economy', 'culture', 'factions', 'atmosphere'] },
    { key: '叙事', label: '叙事信息', fields: ['description', 'first_appearance', 'significance', 'current_status'] },
  ],
  item: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'item_type', 'rarity'] },
    { key: '属性', label: '物品属性', fields: ['appearance', 'material', 'origin', 'special_ability', 'limitation', 'current_state'] },
    { key: '归属', label: '归属信息', fields: ['owner', 'previous_owners', 'acquisition_method'] },
    { key: '叙事', label: '叙事信息', fields: ['description', 'first_appearance', 'significance'] },
  ],
  organization: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'org_type', 'alignment'] },
    { key: '结构', label: '组织结构', fields: ['leader', 'key_members', 'hierarchy', 'headquarters', 'sub_orgs'] },
    { key: '属性', label: '组织属性', fields: ['purpose', 'influence', 'history', 'strength', 'secrets'] },
    { key: '叙事', label: '叙事信息', fields: ['description', 'first_appearance', 'significance', 'current_status'] },
  ],
  concept: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'concept_type'] },
    { key: '规则', label: '规则说明', fields: ['mechanism', 'rules', 'levels_or_stages', 'limitations', 'exceptions'] },
    { key: '范围', label: '作用范围', fields: ['affected_by', 'region', 'requirements'] },
    { key: '叙事', label: '叙事信息', fields: ['description', 'source', 'significance'] },
  ],
  event: [
    { key: '基本', label: '基本信息', fields: ['name', 'aliases', 'event_type'] },
    { key: '时间', label: '时间信息', fields: ['time_point', 'duration', 'chronology_order'] },
    { key: '参与者', label: '参与方', fields: ['characters', 'organizations', 'locations'] },
    { key: '叙事', label: '叙事信息', fields: ['description', 'cause', 'consequence', 'significance', 'is_foreshadow'] },
  ],
}

export default function KnowledgePanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedEntity, setExpandedEntity] = useState(null)
  const [deleteEntityId, setDeleteEntityId] = useState(null)
  const [editingEntity, setEditingEntity] = useState(null)  // the entity being edited
  const [editForm, setEditForm] = useState({ name: '', aliases: '', data: {} })
  const [editSaving, setEditSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showAddEntity, setShowAddEntity] = useState(false)
  const [addType, setAddType] = useState('character')
  const [addForm, setAddForm] = useState({ name: '', aliases: '', data: {} })
  const [addSaving, setAddSaving] = useState(false)
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('list')

  useEffect(() => { loadSummary() }, [bookId, refreshKey])

  async function loadSummary() {
    setLoading(true)
    try {
      const data = await api.getSummary(bookId)
      setSummary(data)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function handleDelete(entityId) {
    setDeleteEntityId(entityId)
  }

  async function confirmDelete() {
    await api.deleteEntity(bookId, deleteEntityId)
    setDeleteEntityId(null)
    if (expandedEntity === deleteEntityId) setExpandedEntity(null)
    triggerRefresh()
    loadSummary()
  }

  function openEditEntity(entity) {
    setEditingEntity(entity)
    setEditForm({
      name: entity.name || '',
      aliases: (entity.aliases || []).join(', '),
      data: { ...(entity.data || {}) },
    })
  }

  function updateEditDataField(key, value) {
    setEditForm(prev => ({ ...prev, data: { ...prev.data, [key]: value } }))
  }

  function removeEditDataField(key) {
    setEditForm(prev => {
      const next = { ...prev.data }
      delete next[key]
      return { ...prev, data: next }
    })
  }

  function addEditDataField(key, value) {
    if (!key.trim()) return
    updateEditDataField(key.trim(), value || '')
  }

  async function saveEdit() {
    if (!editForm.name.trim()) return
    setEditSaving(true)
    try {
      const aliases = editForm.aliases
        .split(',')
        .map(a => a.trim())
        .filter(Boolean)
      await api.updateEntity(bookId, editingEntity.id, {
        name: editForm.name.trim(),
        aliases,
        data: editForm.data,
      })
      setEditingEntity(null)
      triggerRefresh()
      loadSummary()
    } catch (e) {
      console.error(e)
    } finally {
      setEditSaving(false)
    }
  }

  function openAddEntity(type) {
    setAddType(type)
    setShowAddEntity(true)
    setAddForm({ name: '', aliases: '', data: {} })
  }

  async function saveAdd() {
    if (!addForm.name.trim()) return
    setAddSaving(true)
    try {
      // 通过 extract_knowledge 风格写入：复用 update_entity 创建一条实体。
      // 后端 update_entity 要求 entity_id，这里用 POST 风格模拟创建：生成临时 id 后写一条空实体再更新。
      // 简单做法：前端直接调 update_entity 创建新 entity 会 404。所以这里用另一种方式：
      // 通过 chat 触发 extract，或者直接调一个新建实体的端点。
      // 目前后端没有 create_entity，所以这里用 POST /books/add_entity 不存在，改为用
      // update_entity 前先调 /validate 创建。实际最简做法: 临时用 fetch 调一个新建端点.
      // 为了简化: 直接走 POST /books/{bookId}/knowledge/entity 创建 (新端点).
      const aliases = addForm.aliases.split(',').map(a => a.trim()).filter(Boolean)
      await fetch(`/api/books/${bookId}/knowledge/entity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: addType,
          name: addForm.name.trim(),
          aliases,
          data: addForm.data,
        }),
      })
      setShowAddEntity(false)
      setAddForm({ name: '', aliases: '', data: {} })
      triggerRefresh()
      loadSummary()
    } catch (e) {
      console.error(e)
    } finally {
      setAddSaving(false)
    }
  }

  function renderEntitySections(entity) {
    const sections = FIELD_SECTIONS[entity.type]
    if (!sections) {
      return Object.entries(entity.data || {}).map(([k, v]) => (
        <div key={k} className="flex gap-2 text-sm">
          <span className="text-zinc-500 shrink-0 min-w-[60px]">{k}：</span>
          <span className="text-zinc-300">{String(v)}</span>
        </div>
      ))
    }

    return sections.map(section => {
      const hasContent = section.fields.some(f => entity.data?.[f])
      if (!hasContent) return null

      return (
        <div key={section.key} className="mb-3 last:mb-0">
          <h4 className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5 border-b border-zinc-800 pb-1">
            {section.label}
          </h4>
          <div className="space-y-1">
            {section.fields.filter(f => entity.data?.[f]).map(f => {
              const val = entity.data[f]
              if (val === undefined || val === null || val === '') return null
              const displayVal = Array.isArray(val) ? val.join('、') : String(val)
              return (
                <div key={f} className="flex gap-2 text-sm">
                  <span className="text-zinc-500 shrink-0 min-w-[70px]">{f}：</span>
                  <span className="text-zinc-300">{displayVal}</span>
                </div>
              )
            })}
          </div>
        </div>
      )
    })
  }

  if (loading) return <LoadingState text="加载知识库..." />
  if (!summary || summary.totalEntities === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-zinc-600">
        <Icon name="book-open" size={36} className="text-zinc-700 mb-3" />
        <p className="text-base mb-1">知识库为空</p>
        <p className="text-sm">在对话中发送 /s + 设定文本来添加知识</p>
      </div>
    )
  }

  // Filter entities by search query
  const filteredEntities = {}
  let totalFiltered = 0
  for (const type of TYPE_ORDER) {
    const entities = summary.entities[type]
    if (!entities) continue
    const filtered = searchQuery
      ? entities.filter(e =>
          e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (e.aliases && e.aliases.some(a => a.toLowerCase().includes(searchQuery.toLowerCase())))
        )
      : entities
    if (filtered.length > 0) {
      filteredEntities[type] = filtered
      totalFiltered += filtered.length
    }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 space-y-2 shrink-0">
        <div className="flex items-center justify-between gap-4 text-sm text-zinc-400">
          <div className="flex items-center gap-3">
            <div className="flex gap-4">
              <span>实体 {summary.totalEntities}</span>
              <span>关系 {summary.totalRelations}</span>
              <span>伏笔 {summary.totalForeshadows}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* View mode toggle */}
            <div className="flex bg-zinc-800 rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('graph')}
                className={`px-2.5 py-1 rounded text-[10px] transition-colors ${viewMode === 'graph' ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
              ><Icon name="layout-grid" size={12} className="inline mr-1" />图谱</button>
              <button
                onClick={() => setViewMode('list')}
                className={`px-2.5 py-1 rounded text-[10px] transition-colors ${viewMode === 'list' ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
              ><Icon name="list" size={12} className="inline mr-1" />列表</button>
            </div>
            <button
              onClick={() => openAddEntity('character')}
              className="flex items-center gap-1.5 text-xs text-zinc-300 hover:text-white bg-accent/80 hover:bg-accent px-3 py-1.5 rounded-md transition-colors"
              title="新建实体"
            >
              <Icon name="plus" size={12} /> 新建实体
            </button>
          </div>
        </div>
        {viewMode === 'list' && (
          <div className="relative">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索实体名称或别名..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
            />
          </div>
        )}
      </div>

      {/* 4D Map: Master graph identity banner */}
      <div className="px-6 py-2.5 bg-gradient-to-r from-blue-950/30 to-purple-950/20 border-b border-blue-900/30">
        <div className="flex items-center gap-3 text-[10px]">
          <span className="text-blue-400 font-medium flex items-center gap-1"><Icon name="layout-grid" size={12} /> 4D 全书图谱</span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-500">本页为全书复杂图主视图，以下为图谱的三个侧面：</span>
          <span className="text-zinc-600">|</span>
          <span className="text-violet-400 flex items-center gap-1"><Icon name="user" size={10} /> 角色</span>
          <span className="text-emerald-400 flex items-center gap-1"><Icon name="map-pin" size={10} /> 地图</span>
          <span className="text-cyan-400 flex items-center gap-1"><Icon name="clock" size={10} /> 时间线</span>
          <span className="text-zinc-600">|</span>
          <span className="text-amber-400/70 flex items-center gap-1"><Icon name="globe" size={10} /> 世界观为全局标量，独立于图谱</span>
        </div>
      </div>

      {/* Graph view (default) */}
      {viewMode === 'graph' && (
        <div className="flex-1 overflow-hidden flex">
          <FullGraphView bookId={bookId} />
        </div>
      )}

      {/* List view */}
      {viewMode === 'list' && (
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {totalFiltered === 0 && searchQuery ? (
          <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
            <Icon name="search" size={24} className="text-zinc-700 mb-2" />
            <p className="text-sm">未找到匹配的实体</p>
            <button onClick={() => setSearchQuery('')} className="text-xs text-blue-400 hover:text-blue-300 mt-2">
              清除搜索
            </button>
          </div>
        ) : (
          TYPE_ORDER.map(type => {
            const entities = filteredEntities[type]
            if (!entities || entities.length === 0) return null
            return (
              <div key={type}>
                <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5">
                  {TYPE_LABELS[type] ? <><Icon name={TYPE_LABELS[type].icon} size={14} /> {TYPE_LABELS[type].label}</> : type} ({entities.length})
                </h3>
                <div className="space-y-2">
                  {entities.map(entity => (
                    <div key={entity.id} className="bg-zinc-800/40 border border-zinc-800 rounded-lg">
                      <button
                        onClick={() => setExpandedEntity(expandedEntity === entity.id ? null : entity.id)}
                        className="w-full px-4 py-2.5 text-left text-sm flex items-center justify-between hover:bg-zinc-800/60 transition-colors rounded-lg"
                      >
                        <span className="font-medium text-zinc-200 min-w-0 truncate">{entity.name}</span>
                        <div className="flex items-center gap-2 shrink-0 ml-2">
                          {entity.aliases?.length > 0 && (
                            <span className="text-xs text-zinc-500 truncate max-w-[200px]">{entity.aliases.join(', ')}</span>
                          )}
                          <span className={`text-xs transition-transform ${expandedEntity === entity.id ? 'rotate-180' : ''}`}>
                            ▼
                          </span>
                        </div>
                      </button>
                      {expandedEntity === entity.id && (
                        <div className="px-4 pb-3 border-t border-zinc-800">
                          {/* 顶部：编辑 + 删除按钮 */}
                          <div className="flex items-center justify-end gap-2 pt-3 pb-1 border-b border-zinc-800 mb-3">
                            <button
                              onClick={() => openEditEntity(entity)}
                              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-accent bg-zinc-800/50 hover:bg-zinc-700/50 px-2.5 py-1 rounded-md transition-colors"
                            >
                              <Icon name="edit" size={12} /> 编辑
                            </button>
                            <button
                              onClick={() => handleDelete(entity.id)}
                              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-red-400 bg-zinc-800/50 hover:bg-red-950/40 px-2.5 py-1 rounded-md transition-colors"
                            >
                              <Icon name="trash" size={12} /> 删除
                            </button>
                          </div>
                          <div className="mt-3">
                            {renderEntitySections(entity)}
                          </div>
                          {(!entity.data || Object.keys(entity.data).length === 0) && (
                            <p className="text-xs text-zinc-600 mt-2">无详细数据</p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })
        )}

        {summary.relations?.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5"><Icon name="link" size={14} /> 关系 ({summary.relations.length})</h3>
            <div className="space-y-1">
              {summary.relations.map(r => (
                <div key={r.id} className="text-xs text-zinc-500 bg-zinc-800/30 border border-zinc-800 rounded px-3 py-1.5">
                  {r.from} <span className="text-zinc-400">[{r.type}]</span> {r.to}
                </div>
              ))}
            </div>
          </div>
        )}

        {summary.foreshadows?.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5"><Icon name="target" size={14} /> 伏笔</h3>
            <div className="space-y-2">
              {summary.foreshadows.map(f => (
                <div key={f.id} className={`text-xs p-2.5 rounded-lg border ${
                  f.resolved
                    ? 'border-emerald-800 bg-emerald-900/20 text-emerald-400'
                    : 'border-amber-800 bg-amber-900/20 text-amber-400'
                }`}>
                  <p className="font-medium">{f.text}</p>
                  <p className="text-zinc-500 mt-1">→ {f.hint}</p>
                  {f.resolved && f.resolution && (
                    <p className="text-emerald-600 mt-1 flex items-center gap-1"><Icon name="check-circle" size={12} /> {f.resolution}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      )}

      <ConfirmModal
        open={!!deleteEntityId}
        title="删除实体"
        message="确定删除此实体？相关关系和引用可能影响。"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setDeleteEntityId(null)}
      />

      {editingEntity && (
        <EditEntityModal
          entity={editingEntity}
          form={editForm}
          setForm={setEditForm}
          onCancel={() => setEditingEntity(null)}
          onSave={saveEdit}
          saving={editSaving}
          onUpdateData={updateEditDataField}
          onRemoveData={removeEditDataField}
        />
      )}

      {showAddEntity && (
        <AddEntityModal
          defaultType={addType}
          onTypeChange={setAddType}
          form={addForm}
          setForm={setAddForm}
          onCancel={() => setShowAddEntity(false)}
          onSave={saveAdd}
          saving={addSaving}
        />
      )}
    </div>
  )
}


// ──────────────────────────────────────────────────────────────────────────
// Shared form block for editing data dict fields
// ──────────────────────────────────────────────────────────────────────────

function EntityDataForm({ data, onUpdate, onRemove }) {
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  function handleAdd() {
    if (!newKey.trim()) return
    onUpdate(newKey.trim(), newValue)
    setNewKey('')
    setNewValue('')
  }

  const entries = Object.entries(data || {}).filter(([k]) => k && k !== 'name' && k !== 'aliases')

  return (
    <div className="space-y-2">
      <label className="text-[10px] text-zinc-400 uppercase tracking-wider">属性字段</label>
      {entries.map(([k, v]) => {
        const isLong = typeof v === 'string' && v.length > 60
        return (
          <div key={k} className="flex gap-2 items-start">
            <input
              value={k}
              onChange={(e) => {
                const newK = e.target.value
                if (newK !== k) {
                  onRemove(k)
                  onUpdate(newK, v)
                }
              }}
              className="w-28 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300 shrink-0"
            />
            {isLong ? (
              <textarea
                value={v || ''}
                onChange={(e) => onUpdate(k, e.target.value)}
                rows={3}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300 resize-none"
              />
            ) : (
              <input
                value={String(v || '')}
                onChange={(e) => onUpdate(k, e.target.value)}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-300"
              />
            )}
            <button
              onClick={() => onRemove(k)}
              className="text-zinc-600 hover:text-red-400 px-2 py-1.5 text-xs shrink-0"
              aria-label="移除字段"
            >
              <Icon name="x" size={12} />
            </button>
          </div>
        )
      })}
      <div className="flex gap-2 items-start pt-2 border-t border-zinc-800">
        <input
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          placeholder="字段名..."
          className="w-28 bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 shrink-0"
        />
        <input
          value={newValue}
          onChange={e => setNewValue(e.target.value)}
          placeholder="字段值..."
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAdd())}
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200"
        />
        <button
          onClick={handleAdd}
          disabled={!newKey.trim()}
          className="text-accent hover:text-accent-hover px-2 py-1.5 text-xs shrink-0 disabled:opacity-40"
        >
          + 添加
        </button>
      </div>
    </div>
  )
}


// ──────────────────────────────────────────────────────────────────────────
// Edit entity modal
// ──────────────────────────────────────────────────────────────────────────

function EditEntityModal({ entity, form, setForm, onSave, onCancel, saving, onUpdateData, onRemoveData }) {
  return (
    <Modal open onClose={onCancel} title={`编辑: ${entity.name}`} size="lg">
      <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
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
        <EntityDataForm
          data={form.data}
          onUpdate={onUpdateData}
          onRemove={onRemoveData}
        />
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


// ──────────────────────────────────────────────────────────────────────────
// Add entity modal
// ──────────────────────────────────────────────────────────────────────────

const ENTITY_TYPES = [
  { value: 'character', label: '人物' },
  { value: 'location', label: '地点' },
  { value: 'item', label: '物品' },
  { value: 'organization', label: '组织' },
  { value: 'concept', label: '概念' },
  { value: 'event', label: '事件' },
]

function AddEntityModal({ defaultType, onTypeChange, form, setForm, onSave, onCancel, saving }) {
  const [newFieldKey, setNewFieldKey] = useState('')
  const [newFieldValue, setNewFieldValue] = useState('')

  function handleAddField() {
    if (!newFieldKey.trim()) return
    setForm(prev => ({
      ...prev,
      data: { ...prev.data, [newFieldKey.trim()]: newFieldValue },
    }))
    setNewFieldKey('')
    setNewFieldValue('')
  }

  function handleRemoveField(key) {
    setForm(prev => {
      const next = { ...prev.data }
      delete next[key]
      return { ...prev, data: next }
    })
  }

  return (
    <Modal open onClose={onCancel} title="新建实体" size="lg">
      <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">类型</label>
            <select
              value={defaultType}
              onChange={e => onTypeChange(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            >
              {ENTITY_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">名称 <span className="text-red-400">*</span></label>
            <input
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="实体名称"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
            />
          </div>
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
        <EntityDataForm
          data={form.data}
          onUpdate={(k, v) => setForm(prev => ({ ...prev, data: { ...prev.data, [k]: v } }))}
          onRemove={handleRemoveField}
        />
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
            {saving ? '创建中...' : '创建实体'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
