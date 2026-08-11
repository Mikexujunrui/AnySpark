import { useState, useEffect } from 'react'
import { api } from '../api'
import ConfirmModal from './ui/ConfirmModal'
import Modal from './ui/Modal'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'

// V4 材料摘要卡字段：id/title/topic/key_points/key_settings/characters/terms/purpose/source_text/graph_entities/created_at
interface MaterialCard {
  id: string
  title: string
  topic?: string
  key_points?: string[]
  key_settings?: string[]
  characters?: string[]
  terms?: string[]
  purpose?: string
  source_text?: string
  graph_entities?: string[]
  created_at?: string
}

export default function MaterialsPanel() {
  const [materials, setMaterials] = useState<MaterialCard[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [deleteMatId, setDeleteMatId] = useState<string | null>(null)
  const [selectedMat, setSelectedMat] = useState<MaterialCard | null>(null)
  const [form, setForm] = useState({ title: '', content: '', purpose: 'fact' })

  useEffect(() => { loadMaterials() }, [])

  async function loadMaterials() {
    setLoading(true)
    try {
      const data: any = await api.getMaterials('')
      setMaterials(Array.isArray(data) ? data as MaterialCard[] : [])
    } catch (e) { showToast('加载资料失败', 'error') }
    setLoading(false)
  }

  async function handleSearch() {
    const q = query.trim()
    if (!q) { loadMaterials(); return }
    setLoading(true)
    try {
      const data: any = await api.getMaterials('')
      const list: MaterialCard[] = Array.isArray(data) ? data : []
      const needle = q.toLowerCase()
      const hits = list.filter(m => {
        const hay = [
          m.title, m.topic, m.purpose,
          ...(m.key_points || []), ...(m.key_settings || []),
          ...(m.characters || []), ...(m.terms || []),
          m.source_text || '',
        ].join(' ').toLowerCase()
        return hay.includes(needle)
      })
      setMaterials(hits)
    } catch (e) { showToast('搜索失败', 'error') }
    setLoading(false)
  }

  async function handleAdd() {
    if (!form.title.trim() || !form.content.trim()) {
      showToast('标题和内容不能为空', 'error')
      return
    }
    try {
      // V4：text=原文 → 后端 LLM 消化成摘要卡（topic/key_points/characters/terms）
      await api.createMaterial({
        text: form.content,
        title: form.title,
        purpose: form.purpose,
      })
      setShowAdd(false)
      setForm({ title: '', content: '', purpose: 'fact' })
      loadMaterials()
      showToast('资料已添加（AI 已消化成摘要卡）', 'success')
    } catch (e) { showToast('添加失败', 'error') }
  }

  async function handleDelete() {
    if (!deleteMatId) return
    try {
      await api.deleteMaterial(deleteMatId)
      setDeleteMatId(null)
      loadMaterials()
      showToast('已删除', 'success')
    } catch (e) { showToast('删除失败', 'error') }
  }

  // 渲染辅助：卡片预览文本（V4 摘要卡结构）
  function previewText(m: MaterialCard): string {
    const points = (m.key_points || []).slice(0, 3).join('；')
    const topic = m.topic || ''
    const src = m.source_text || ''
    const core = [topic, points].filter(Boolean).join('。')
    if (core) return core
    return src.slice(0, 300)
  }

  // 渲染辅助：标签集（V4 结构化字段 → 标签展示）
  function tagList(m: MaterialCard): string[] {
    const tags: string[] = []
    if (m.purpose) tags.push(`用途:${m.purpose}`)
    ;(m.characters || []).slice(0, 3).forEach(c => tags.push(c))
    ;(m.key_settings || []).slice(0, 3).forEach(s => tags.push(s))
    ;(m.terms || []).slice(0, 3).forEach(t => tags.push(t))
    return tags
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Icon name="folder" size={28} /> 资料库
          </h1>
          <p className="text-zinc-500 mt-1 text-sm">项目研究资料池：上传原文 → AI 消化成摘要卡（要点/设定/角色/术语）</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAdd(true)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-5 py-2.5 rounded-lg transition-colors text-sm font-medium flex items-center gap-2">
            <Icon name="plus" size={16} /> 添加资料
          </button>
        </div>
      </header>

      <div className="flex gap-2 mb-6">
        <input
          type="text" value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' ? handleSearch() : null}
          placeholder="搜索资料（标题/要点/设定/角色/术语）..."
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
        />
        <button onClick={handleSearch}
          className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-6 py-2.5 rounded-lg transition-colors text-sm flex items-center gap-2">
          <Icon name="search" size={14} /> 搜索
        </button>
        {query && (
          <button onClick={() => { setQuery(''); loadMaterials() }}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2.5 rounded-lg transition-colors text-sm flex items-center gap-2">
            <Icon name="x" size={14} /> 清除
          </button>
        )}
      </div>

      {loading ? (
        <LoadingState text="加载资料..." />
      ) : materials.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-zinc-600">
          <Icon name="folder-plus" size={48} className="mb-4 text-zinc-700" />
          <p className="text-lg mb-2">资料库为空</p>
          <p className="text-sm mb-6">添加研究资料，AI 会自动消化成摘要卡</p>
          <button onClick={() => setShowAdd(true)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-6 py-3 rounded-lg transition-colors flex items-center gap-2">
            <Icon name="plus" size={16} /> 添加第一条资料
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {materials.map(m => (
            <div key={m.id}
              onClick={() => setSelectedMat(m)}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 cursor-pointer transition-all group hover:shadow-md">
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-zinc-200 font-semibold text-sm leading-snug flex-1 mr-2">{m.title}</h3>
                <button onClick={(e) => { e.stopPropagation(); setDeleteMatId(m.id) }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 text-xs transition-all ml-1 shrink-0">
                  <Icon name="trash" size={14} />
                </button>
              </div>
              {tagList(m).length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {tagList(m).map((t, i) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">{t}</span>
                  ))}
                </div>
              )}
              <p className="text-zinc-500 text-xs leading-relaxed line-clamp-4 whitespace-pre-wrap">
                {previewText(m)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Add Material Modal */}
      {showAdd && (
        <Modal open onClose={() => setShowAdd(false)} title="添加资料" size="lg">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-1">添加资料</h2>
            <p className="text-xs text-zinc-500 mb-4">提交原文后 AI 自动消化成摘要卡（要点/设定/角色/术语），写入资料库。</p>
            <div className="space-y-3">
              <input placeholder="资料标题" value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500" />
              <textarea placeholder="资料原文（AI 将消化成摘要卡）..." value={form.content} rows={6}
                onChange={e => setForm({ ...form, content: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 resize-none" />
              <div className="flex items-center gap-3">
                <span className="text-xs text-zinc-500">用途</span>
                <select value={form.purpose}
                  onChange={e => setForm({ ...form, purpose: e.target.value })}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500">
                  <option value="fact">事实/设定（fact）</option>
                  <option value="style">文风参考（style）</option>
                  <option value="both">两者兼顾（both）</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAdd(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">取消</button>
              <button onClick={handleAdd}
                disabled={!form.title || !form.content}
                className="bg-zinc-200 hover:bg-white text-zinc-900 px-5 py-2 rounded-lg transition-colors text-sm font-medium disabled:opacity-40">提交并消化</button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteMatId}
        title="删除资料"
        message="确定永久删除这条资料？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteMatId(null)}
      />

      {/* Material Detail Modal */}
      {selectedMat && (
        <Modal open onClose={() => setSelectedMat(null)} title={selectedMat.title} size="xl">
          <div className="p-6 max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-zinc-100">{selectedMat.title}</h2>
              <button onClick={() => setSelectedMat(null)}
                className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800" aria-label="关闭">
                <Icon name="x" size={16} />
              </button>
            </div>

            {tagList(selectedMat).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                {tagList(selectedMat).map((t, i) => (
                  <span key={i} className="text-xs px-2 py-0.5 rounded-lg bg-zinc-800 text-zinc-400 border border-zinc-700">{t}</span>
                ))}
              </div>
            )}

            {/* 摘要卡结构化展示 */}
            {selectedMat.topic && (
              <div className="mb-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">主题</div>
                <p className="text-sm text-zinc-200">{selectedMat.topic}</p>
              </div>
            )}
            {selectedMat.key_points && selectedMat.key_points.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">要点</div>
                <ul className="space-y-1">
                  {selectedMat.key_points.map((p, i) => (
                    <li key={i} className="text-sm text-zinc-300 flex gap-2">
                      <span className="text-zinc-600">{i + 1}.</span>{p}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {selectedMat.characters && selectedMat.characters.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">涉及角色</div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedMat.characters.map((c, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded bg-violet-900/30 text-violet-300 border border-violet-800/40">{c}</span>
                  ))}
                </div>
              </div>
            )}
            {selectedMat.key_settings && selectedMat.key_settings.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">关键设定</div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedMat.key_settings.map((s, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded bg-emerald-900/30 text-emerald-300 border border-emerald-800/40">{s}</span>
                  ))}
                </div>
              </div>
            )}
            {selectedMat.terms && selectedMat.terms.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">术语</div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedMat.terms.map((t, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded bg-amber-900/30 text-amber-300 border border-amber-800/40">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {/* 原文（可查全文） */}
            {selectedMat.source_text && (
              <div className="mt-4">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">原文</div>
                <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-4">
                  <pre className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap break-words font-sans m-0">{selectedMat.source_text}</pre>
                </div>
              </div>
            )}

            <p className="text-[10px] text-zinc-600 mt-4 font-mono truncate">ID: {selectedMat.id}{selectedMat.created_at ? ` · ${selectedMat.created_at.slice(0, 10)}` : ''}</p>
          </div>
        </Modal>
      )}
    </div>
  )
}
