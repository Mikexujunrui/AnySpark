import { useState, useEffect } from 'react'
import { api } from '../api.js'
import ConfirmModal from './ui/ConfirmModal.jsx'
import Modal from './ui/Modal.jsx'
import Icon from './ui/Icon.jsx'
import LoadingState from './ui/Skeleton.jsx'
import { showToast } from './ui/Toast.jsx'

export default function MaterialsPanel() {
  const [materials, setMaterials] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showSubscribe, setShowSubscribe] = useState(false)
  const [globalMats, setGlobalMats] = useState([])
  const [deleteMatId, setDeleteMatId] = useState(null)
  const [selectedMat, setSelectedMat] = useState(null)
  const [form, setForm] = useState({ title: '', content: '', tags: '', source: 'manual', source_url: '' })

  useEffect(() => { loadMaterials() }, [])

  async function loadMaterials() {
    setLoading(true)
    try {
      const data = await api.getMaterials('')
      setMaterials(Array.isArray(data.materials) ? data.materials : data)
    } catch (e) { showToast('加载资料失败', 'error') }
    setLoading(false)
  }

  async function handleSearch() {
    setLoading(true)
    try {
      const data = await api.searchMaterials(query, '')
      setMaterials(Array.isArray(data.results) ? data.results : data)
    } catch (e) { showToast('搜索失败', 'error') }
    setLoading(false)
  }

  async function handleAdd() {
    const tags = form.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
    try {
      await api.createMaterial({ ...form, tags })
      setShowAdd(false)
      setForm({ title: '', content: '', tags: '', source: 'manual', source_url: '' })
      loadMaterials()
      showToast('资料已添加', 'success')
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

  async function loadGlobalMats() {
    try {
      const data = await api.getMaterials('')
      setGlobalMats(data.materials || [])
      setShowSubscribe(true)
    } catch (e) { showToast('加载失败', 'error') }
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text)
    showToast('已复制 ID', 'success')
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Icon name="folder" size={28} /> 资料库
          </h1>
          <p className="text-zinc-500 mt-1 text-sm">所有项目共享的研究资料池，搜索、收藏、管理参考资料</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadGlobalMats}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-4 py-2.5 rounded-lg transition-colors text-sm flex items-center gap-2">
            <Icon name="search" size={14} /> 浏览全部
          </button>
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
          placeholder="搜索资料..."
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
          <p className="text-sm mb-6">添加研究资料，或通过 AI 自动收藏网页搜索结果</p>
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
              {m.tags && m.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {m.tags.map((t, i) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">{t}</span>
                  ))}
                </div>
              )}
              <p className="text-zinc-500 text-xs leading-relaxed line-clamp-4 whitespace-pre-wrap">
                {m.content ? m.content.slice(0, 300) : (m.snippet || '')}
              </p>
              {m.source && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-zinc-600">
                  <span>来源: {m.source}</span>
                  {m.source_url && (
                    <a href={m.source_url} target="_blank" rel="noopener" className="text-zinc-500 hover:text-zinc-300 underline truncate max-w-[200px]" onClick={e => e.stopPropagation()}>
                      {m.source_url}
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add Material Modal */}
      {showAdd && (
        <Modal open onClose={() => setShowAdd(false)} title="添加资料" size="lg">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-4">添加资料</h2>
            <div className="space-y-3">
              <input placeholder="资料标题" value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500" />
              <textarea placeholder="资料内容..." value={form.content} rows={5}
                onChange={e => setForm({ ...form, content: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 resize-none" />
              <input placeholder="标签（逗号分隔），如: 历史,唐代,服饰" value={form.tags}
                onChange={e => setForm({ ...form, tags: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500" />
              <input placeholder="来源说明（如: web_search, 书名）" value={form.source}
                onChange={e => setForm({ ...form, source: e.target.value })}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500" />
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAdd(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">取消</button>
              <button onClick={handleAdd}
                disabled={!form.title || !form.content}
                className="bg-zinc-200 hover:bg-white text-zinc-900 px-5 py-2 rounded-lg transition-colors text-sm font-medium disabled:opacity-40">提交</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Browse Global Modal */}
      {showSubscribe && (
        <Modal open onClose={() => setShowSubscribe(false)} title="浏览全部资料" size="xl">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-4">浏览全部资料</h2>
            {globalMats.length === 0 ? (
              <p className="text-zinc-500 text-sm">全局资料池为空</p>
            ) : (
              <div className="space-y-2">
                {globalMats.map(m => (
                  <div key={m.id} className="bg-zinc-800 rounded-lg p-3 flex items-start justify-between group cursor-pointer hover:bg-zinc-700/50 transition-colors">
                    <div className="flex-1 mr-3 min-w-0" onClick={() => setSelectedMat(m)}>
                      <p className="text-zinc-200 text-sm font-medium">{m.title}</p>
                      {m.tags && (<p className="text-zinc-500 text-xs mt-0.5">{m.tags.join(', ')}</p>)}
                      {m.content && (
                        <p className="text-zinc-600 text-xs mt-1 line-clamp-2">{m.content.slice(0, 120)}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0 mt-1">
                      <button onClick={(e) => { e.stopPropagation(); setSelectedMat(m) }}
                        className="text-zinc-600 hover:text-sky-400 text-xs opacity-0 group-hover:opacity-100 transition-all">
                        查看
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); copyToClipboard(m.id) }}
                        className="text-zinc-600 hover:text-zinc-300 text-xs transition-colors">
                        复制ID
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="text-zinc-600 text-xs mt-4">
              在书中对 AI 说 "subscribe_material material_id=xxx" 即可订阅资料到当前项目。
            </p>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowSubscribe(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">关闭</button>
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
            {selectedMat.tags && selectedMat.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                {selectedMat.tags.map((t, i) => (
                  <span key={i} className="text-xs px-2 py-0.5 rounded-lg bg-zinc-800 text-zinc-400 border border-zinc-700">{t}</span>
                ))}
              </div>
            )}
            <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-4">
              <pre className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap break-words font-sans m-0">{selectedMat.content || selectedMat.snippet || '无内容'}</pre>
            </div>
            {selectedMat.source && (
              <div className="mt-4 flex items-center gap-3 text-xs text-zinc-500">
                <span className="bg-zinc-800 px-2 py-0.5 rounded">来源: {selectedMat.source}</span>
                {selectedMat.source_url && (
                  <a href={selectedMat.source_url} target="_blank" rel="noopener" className="text-sky-400 hover:text-sky-300 underline truncate max-w-[400px]">
                    {selectedMat.source_url}
                  </a>
                )}
              </div>
            )}
            <p className="text-[10px] text-zinc-600 mt-4 font-mono truncate">ID: {selectedMat.id}</p>
          </div>
        </Modal>
      )}
    </div>
  )
}
