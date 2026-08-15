import { useState, useEffect, useMemo } from 'react'
import { api } from "../api"
import Icon from './ui/Icon'
import Modal from './ui/Modal'
import ConfirmModal from './ui/ConfirmModal'
import LoadingState from './ui/Skeleton'
import { useRefreshKey, triggerRefresh } from "../store"
import FullGraphView from './FullGraphView'

// ──────────────────────────────────────────────────────────────────────────
// V4 图谱数据结构适配
//   entities:  [{ id, name, entity_type(中文), aliases[], description, state,
//                 first_chapter, last_chapter }]
//   relations: [{ id, from_name, to_name, rel_type, description }]
//   events:    [{ id, chapter_ref, time_point, label, description, involved[] }]
//   foreshadows: /api/plot → [{ id, content, category, priority, status, chapter_ref }]
// ──────────────────────────────────────────────────────────────────────────

// 中文 entity_type → 展示元数据（V4 无固定类型集，按值兜底）
const TYPE_META: Record<string, { icon: string; label: string }> = {
  角色: { icon: 'user', label: '角色' },
  地点: { icon: 'map-pin', label: '地点' },
  物件: { icon: 'sword', label: '物品' },
  设定: { icon: 'lightbulb', label: '设定' },
  组织: { icon: 'building', label: '组织' },
  种族: { icon: 'users', label: '种族' },
  事件: { icon: 'calendar', label: '事件' },
}

const FALLBACK_TYPE: { icon: string; label: string } = { icon: 'tag', label: '其他' }

function typeMeta(t: string): { icon: string; label: string } {
  return TYPE_META[t] || FALLBACK_TYPE
}

function formatDisplayValue(val: unknown): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'string') return val
  if (Array.isArray(val)) return val.map(v => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))).join('、')
  if (typeof val === 'object') return JSON.stringify(val, null, 2)
  return String(val)
}

interface V4Entity {
  id: string
  name: string
  entity_type?: string
  aliases?: string[]
  description?: string
  state?: string
  first_chapter?: string
  last_chapter?: string
  [k: string]: unknown
}

interface V4Relation {
  id: string
  from_name: string
  to_name: string
  rel_type?: string
  description?: string
}

interface V4Plot {
  id: string
  content?: string
  category?: string
  priority?: string
  status?: string
  chapter_ref?: string
  resolved?: boolean
  [k: string]: unknown
}

export default function KnowledgePanel({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const [summary, setSummary] = useState<Record<string, any> | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedEntity, setExpandedEntity] = useState<string | null>(null)
  const [deleteEntityId, setDeleteEntityId] = useState<string | null>(null)
  const [editingEntity, setEditingEntity] = useState<V4Entity | null>(null)
  const [editForm, setEditForm] = useState({ name: '', entity_type: '', aliases: '', description: '', state: '' })
  const [editSaving, setEditSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showAddEntity, setShowAddEntity] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', entity_type: '角色', aliases: '', description: '', state: '' })
  const [addSaving, setAddSaving] = useState(false)
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('list')
  const [typeFilter, setTypeFilter] = useState<string>('全部')

  useEffect(() => { loadSummary() }, [bookId, refreshKey])

  async function loadSummary() {
    setLoading(true)
    try {
      const data = await api.getSummary(bookId)
      setSummary(data as Record<string, any>)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function handleDelete(entityId: string) {
    setDeleteEntityId(entityId)
  }

  async function confirmDelete() {
    if (!deleteEntityId) return
    try {
      await api.deleteEntity(bookId, deleteEntityId)
      setDeleteEntityId(null)
      if (expandedEntity === deleteEntityId) setExpandedEntity(null)
      triggerRefresh()
      loadSummary()
    } catch (e) { console.error(e) }
  }

  function openEditEntity(entity: V4Entity) {
    setEditingEntity(entity)
    setEditForm({
      name: entity.name || '',
      entity_type: entity.entity_type || '角色',
      aliases: (entity.aliases || []).join(', '),
      description: entity.description || '',
      state: entity.state || '',
    })
  }

  async function saveEdit() {
    if (!editForm.name.trim()) return
    setEditSaving(true)
    try {
      const aliases = editForm.aliases.split(',').map(a => a.trim()).filter(Boolean)
      // V4 PATCH：实体主键为 name，改名请删建；只传可编辑字段
      await api.updateEntity(bookId, editingEntity!.id, {
        entity_type: editForm.entity_type,
        aliases,
        description: editForm.description,
        state: editForm.state,
      })
      setEditingEntity(null)
      triggerRefresh()
      loadSummary()
    } catch (e) { console.error(e) }
    finally { setEditSaving(false) }
  }

  async function saveAdd() {
    if (!addForm.name.trim()) return
    setAddSaving(true)
    try {
      const aliases = addForm.aliases.split(',').map(a => a.trim()).filter(Boolean)
      await api.createEntity({
        name: addForm.name.trim(),
        entity_type: addForm.entity_type,
        aliases,
        description: addForm.description,
        state: addForm.state,
        book_id: bookId || 'main',
      })
      setShowAddEntity(false)
      setAddForm({ name: '', entity_type: '角色', aliases: '', description: '', state: '' })
      triggerRefresh()
      loadSummary()
    } catch (e) { console.error(e) }
    finally { setAddSaving(false) }
  }

  // ── 数据派生（V4 扁平数组 → 展示结构）──
  const entities: V4Entity[] = (summary?.entities || []) as V4Entity[]
  const relations: V4Relation[] = (summary?.relations || []) as V4Relation[]
  const foreshadows: V4Plot[] = (summary?.foreshadows || []) as V4Plot[]

  const groupedEntities = useMemo(() => {
    const groups: Record<string, V4Entity[]> = {}
    for (const e of entities) {
      const t = e.entity_type || '其他'
      if (!groups[t]) groups[t] = []
      groups[t].push(e)
    }
    return groups
  }, [entities])

  const filteredGroups = useMemo(() => {
    // 类型过滤（角色/地点/物件/设定 子视图）
    let base = groupedEntities
    if (typeFilter !== '全部') {
      base = Object.fromEntries(
        Object.entries(groupedEntities).filter(([t]) => t === typeFilter)
      )
    }
    if (!searchQuery.trim()) return base
    const q = searchQuery.toLowerCase()
    const out: Record<string, V4Entity[]> = {}
    for (const [t, list] of Object.entries(base)) {
      const filtered = list.filter(e =>
        e.name.toLowerCase().includes(q) ||
        (e.aliases || []).some(a => a.toLowerCase().includes(q)) ||
        (e.entity_type || '').toLowerCase().includes(q) ||
        (e.description || '').toLowerCase().includes(q)
      )
      if (filtered.length > 0) out[t] = filtered
    }
    return out
  }, [groupedEntities, searchQuery, typeFilter])

  const totalFiltered = Object.values(filteredGroups).reduce((s, l) => s + l.length, 0)

  function renderEntityDetail(e: V4Entity) {
    const rows: { label: string; value: string }[] = []
    if (e.entity_type) rows.push({ label: '类型', value: e.entity_type })
    if (e.aliases && e.aliases.length > 0) rows.push({ label: '别名', value: e.aliases.join('、') })
    if (e.description) rows.push({ label: '描述', value: e.description })
    if (e.state) rows.push({ label: '状态', value: e.state })
    if (e.first_chapter) rows.push({ label: '首次出场', value: e.first_chapter })
    if (e.last_chapter) rows.push({ label: '最近出场', value: e.last_chapter })
    // 额外字段（未知 key 兜底展示）
    const known = new Set(['id', 'name', 'entity_type', 'aliases', 'description', 'state', 'first_chapter', 'last_chapter', 'book_id', 'first_order', 'last_order', 'weight', 'lines'])
    for (const [k, v] of Object.entries(e)) {
      if (known.has(k)) continue
      const val = formatDisplayValue(v)
      if (val) rows.push({ label: k, value: val })
    }
    if (rows.length === 0) {
      return <p className="text-xs text-zinc-600 mt-2">无详细数据</p>
    }
    return (
      <div className="space-y-2 mt-3">
        {rows.map(r => (
          <div key={r.label} className="flex gap-2 text-sm">
            <span className="text-zinc-500 shrink-0 min-w-[70px]">{r.label}：</span>
            <span className="text-zinc-300 whitespace-pre-wrap">{r.value}</span>
          </div>
        ))}
      </div>
    )
  }

  if (loading) return <LoadingState text="加载知识库..." />
  if (!summary || entities.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-zinc-600">
        <Icon name="book-open" size={36} className="text-zinc-700 mb-3" />
        <p className="text-base mb-1">知识库为空</p>
        <p className="text-sm">在对话中让 AI 提取设定，或点「新建实体」手动登记</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 space-y-2 shrink-0">
        <div className="flex items-center justify-between gap-4 text-sm text-zinc-400">
          <div className="flex items-center gap-3">
            <div className="flex gap-4">
              <span>实体 {entities.length}</span>
              <span>关系 {relations.length}</span>
              <span>伏笔 {foreshadows.length}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* 类型子视图：全部/角色/地点/物件/设定 */}
            <div className="flex bg-zinc-800 rounded-lg p-0.5">
              {['全部', '角色', '地点', '物件', '设定', '事件', '组织'].map(t => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`px-2 py-1 rounded text-[10px] transition-colors ${typeFilter === t ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                >
                  {t}
                </button>
              ))}
            </div>
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
              onClick={() => setShowAddEntity(true)}
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
              placeholder="搜索实体名称/别名/类型/描述..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
            />
          </div>
        )}
      </div>

      {/* 图谱视图（S153：d3-force 全图 + 聚焦子视图双模式；列表为默认） */}
      {viewMode === 'graph' && (
        <div className="flex-1 overflow-hidden flex">
          <FullGraphView bookId={bookId} />
        </div>
      )}

      {/* 列表视图 */}
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
          Object.entries(filteredGroups).map(([type, list]) => {
            const meta = typeMeta(type)
            return (
              <div key={type}>
                <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5">
                  <Icon name={meta.icon} size={14} /> {meta.label} ({list.length})
                </h3>
                <div className="space-y-2">
                  {list.map(entity => (
                    <div key={entity.id} className="bg-zinc-800/40 border border-zinc-800 rounded-lg">
                      <button
                        onClick={() => setExpandedEntity(expandedEntity === entity.id ? null : entity.id)}
                        className="w-full px-4 py-2.5 text-left text-sm flex items-center justify-between hover:bg-zinc-800/60 transition-colors rounded-lg"
                      >
                        <span className="font-medium text-zinc-200 min-w-0 truncate">{entity.name}</span>
                        <div className="flex items-center gap-2 shrink-0 ml-2">
                          {entity.aliases && entity.aliases.length > 0 && (
                            <span className="text-xs text-zinc-500 truncate max-w-[200px]">{entity.aliases.join(', ')}</span>
                          )}
                          <span className={`text-xs transition-transform ${expandedEntity === entity.id ? 'rotate-180' : ''}`}>▼</span>
                        </div>
                      </button>
                      {expandedEntity === entity.id && (
                        <div className="px-4 pb-3 border-t border-zinc-800">
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
                          {renderEntityDetail(entity)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })
        )}

        {relations.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5"><Icon name="link" size={14} /> 关系 ({relations.length})</h3>
            <div className="space-y-1">
              {relations.map(r => (
                <div key={r.id} className="text-xs text-zinc-500 bg-zinc-800/30 border border-zinc-800 rounded px-3 py-1.5">
                  {r.from_name} <span className="text-zinc-400">[{r.rel_type || '关系'}]</span> {r.to_name}
                  {r.description && <span className="text-zinc-600 ml-2">— {r.description}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {foreshadows.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-1.5"><Icon name="target" size={14} /> 伏笔 ({foreshadows.length})</h3>
            <div className="space-y-2">
              {foreshadows.map(f => {
                const resolved = f.status === 'resolved' || f.resolved
                return (
                  <div key={f.id} className={`text-xs p-2.5 rounded-lg border ${
                    resolved ? 'border-emerald-800 bg-emerald-900/20 text-emerald-400' : 'border-amber-800 bg-amber-900/20 text-amber-400'
                  }`}>
                    <div className="flex items-center gap-2">
                      {f.priority === 'must' && <span className="text-[9px] px-1 py-0.5 bg-red-900/50 text-red-300 rounded">钩子</span>}
                      {f.category && <span className="text-[9px] px-1 py-0.5 bg-zinc-700/50 text-zinc-300 rounded">{f.category}</span>}
                    </div>
                    <p className="font-medium mt-1">{String(f.content || f.text || '')}</p>
                    {f.chapter_ref && <p className="text-zinc-500 mt-1">章节：{f.chapter_ref}</p>}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
      )}

      <ConfirmModal
        open={!!deleteEntityId}
        title="删除实体"
        message="确定删除此实体？相关关系和引用可能受影响。"
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
        />
      )}

      {showAddEntity && (
        <AddEntityModal
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
// 编辑实体 Modal（V4 字段：entity_type/aliases/description/state）
// ──────────────────────────────────────────────────────────────────────────

const TYPE_OPTIONS = ['角色', '地点', '物件', '设定', '组织', '种族', '事件', '其他']

function EditEntityModal({ entity, form, setForm, onSave, onCancel, saving }: {
  entity: V4Entity
  form: { name: string; entity_type: string; aliases: string; description: string; state: string }
  setForm: (fn: (prev: any) => any) => void
  onSave: () => void
  onCancel: () => void
  saving: boolean
}) {
  return (
    <Modal open onClose={onCancel} title={`编辑: ${entity.name}`} size="lg">
      <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
        <p className="text-[11px] text-zinc-500 bg-zinc-800/40 border border-zinc-800 rounded px-3 py-2">
          实体主键为名称（改名请先删除再新建）；此处可编辑类型/别名/描述/状态。
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">类型</label>
            <select
              value={form.entity_type}
              onChange={e => setForm(prev => ({ ...prev, entity_type: e.target.value }))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            >
              {TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">名称（只读）</label>
            <input value={form.name} disabled className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-500" />
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
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">描述</label>
          <textarea
            value={form.description}
            onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
            rows={3}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent resize-none"
          />
        </div>
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">当前状态</label>
          <textarea
            value={form.state}
            onChange={e => setForm(prev => ({ ...prev, state: e.target.value }))}
            rows={2}
            placeholder="如：受伤昏迷 / 已抵达雾城码头..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent resize-none"
          />
        </div>
        <div className="flex gap-2 justify-end pt-3 border-t border-zinc-800">
          <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5">取消</button>
          <button
            onClick={onSave}
            disabled={saving}
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
// 新建实体 Modal（V4 POST /api/graph/entities）
// ──────────────────────────────────────────────────────────────────────────

function AddEntityModal({ form, setForm, onSave, onCancel, saving }: {
  form: { name: string; entity_type: string; aliases: string; description: string; state: string }
  setForm: (fn: (prev: any) => any) => void
  onSave: () => void
  onCancel: () => void
  saving: boolean
}) {
  return (
    <Modal open onClose={onCancel} title="新建实体" size="lg">
      <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">类型</label>
            <select
              value={form.entity_type}
              onChange={e => setForm(prev => ({ ...prev, entity_type: e.target.value }))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            >
              {TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
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
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">描述</label>
          <textarea
            value={form.description}
            onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
            rows={3}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent resize-none"
          />
        </div>
        <div>
          <label className="text-[10px] text-zinc-400 uppercase tracking-wider mb-1 block">当前状态</label>
          <textarea
            value={form.state}
            onChange={e => setForm(prev => ({ ...prev, state: e.target.value }))}
            rows={2}
            placeholder="如：受伤昏迷 / 已抵达雾城码头..."
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent resize-none"
          />
        </div>
        <div className="flex gap-2 justify-end pt-3 border-t border-zinc-800">
          <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5">取消</button>
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
