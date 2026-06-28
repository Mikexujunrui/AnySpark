import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import CreateBookModal from './CreateBookModal'
import MaterialsPanel from './MaterialsPanel'
import WorkflowPoolPanel from './WorkflowPoolPanel'
import StatsDashboard from './StatsDashboard'
import SettingsModal from './SettingsModal'
import ConfirmModal from './ui/ConfirmModal'
import Modal from './ui/Modal'
import Icon from './ui/Icon'
import { showToast } from './ui/Toast'
import { SkeletonGrid } from './ui/Skeleton'

export default function Bookshelf() {
  const [books, setBooks] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [editTouched, setEditTouched] = useState(false)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('books')
  const [deleteBookId, setDeleteBookId] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    loadBooks()
  }, [])

  async function loadBooks() {
    setLoading(true)
    try {
      const data = await api.getBooks()
      setBooks(Array.isArray(data) ? data : [])
    } catch (e) {
      showToast('加载书架失败', 'error')
    }
    setLoading(false)
  }

  async function handleCreate(bookData) {
    try {
      await api.createBook(bookData)
      setShowCreate(false)
      loadBooks()
      showToast('项目创建成功', 'success')
    } catch (e) {
      showToast('创建失败', 'error')
    }
  }

  async function handleDelete() {
    if (!deleteBookId) return
    try {
      await api.deleteBook(deleteBookId)
      setDeleteBookId(null)
      loadBooks()
      showToast('已删除', 'success')
    } catch (e) {
      showToast('删除失败', 'error')
    }
  }

  async function handleEdit(book, e) {
    e.stopPropagation()
    setEditing({ ...book })
    setEditTouched(false)
  }

  async function handleSaveEdit() {
    if (!editing.title?.trim()) return
    try {
      await api.updateBook(editing.id, {
        title: editing.title,
        description: editing.description || '',
      })
      setEditing(null)
      loadBooks()
      showToast('已保存', 'success')
    } catch (e) {
      showToast('保存失败', 'error')
    }
  }

  function formatWords(n) {
    if (n >= 10000) return (n / 10000).toFixed(1) + '万'
    return n.toLocaleString()
  }

  function progressColor(words) {
    if (words >= 100000) return 'from-purple-600 to-fuchsia-500'
    if (words >= 30000) return 'from-amber-500 to-orange-400'
    if (words >= 5000) return 'from-emerald-600 to-teal-500'
    if (words > 0) return 'from-sky-500 to-blue-400'
    return 'from-zinc-600 to-zinc-500'
  }

  function progressLabel(words) {
    if (words >= 100000) return '长篇'
    if (words >= 30000) return '中篇'
    if (words >= 5000) return '连载'
    if (words > 0) return '起步'
    return '草稿'
  }

  return (
    <div>
      {/* Tab bar */}
      <div className="border-b border-zinc-800 bg-zinc-950">
        <div className="max-w-6xl mx-auto px-6 flex gap-0">
          <button
            onClick={() => setTab('books')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
              tab === 'books'
                ? 'text-zinc-200 border-accent'
                : 'text-zinc-500 border-transparent hover:text-zinc-400'
            }`}
          >
            <Icon name="library" size={16} /> 书架
          </button>
          <button
            onClick={() => setTab('materials')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
              tab === 'materials'
                ? 'text-zinc-200 border-accent'
                : 'text-zinc-500 border-transparent hover:text-zinc-400'
            }`}
          >
            <Icon name="folder" size={16} /> 资料库
          </button>
          <button
            onClick={() => setTab('workflows')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
              tab === 'workflows'
                ? 'text-zinc-200 border-accent'
                : 'text-zinc-500 border-transparent hover:text-zinc-400'
            }`}
          >
            <Icon name="settings" size={16} /> 工作流
          </button>
          <button
            onClick={() => setTab('stats')}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
              tab === 'stats'
                ? 'text-zinc-200 border-accent'
                : 'text-zinc-500 border-transparent hover:text-zinc-400'
            }`}
          >
            <Icon name="bar-chart" size={16} /> 统计
          </button>
        </div>
      </div>

      {tab === 'stats' ? (
        <StatsDashboard />
      ) : tab === 'workflows' ? (
        <WorkflowPoolPanel />
      ) : tab === 'materials' ? (
        <MaterialsPanel />
      ) : (
        <div className="max-w-6xl mx-auto px-6 py-10">
          <header className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
                <Icon name="library" size={28} /> 我的书架
              </h1>
              <p className="text-zinc-500 mt-1 text-sm">每个项目拥有独立的知识库与写作空间</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowSettings(true)}
                className="bg-zinc-800 hover:bg-zinc-700 active:scale-95 text-zinc-400 px-3 py-2.5 rounded-lg transition-all text-sm flex items-center gap-2"
                title="API 设置"
              >
                <Icon name="settings" size={16} /> 设置
              </button>
              <button
                onClick={() => setShowCreate(true)}
                className="bg-accent hover:bg-accent-hover text-white px-5 py-2.5 rounded-lg transition-all active:scale-95 text-sm font-medium flex items-center gap-2 shadow-sm"
              >
                <Icon name="plus" size={16} /> 新建项目
              </button>
            </div>
          </header>

          {loading ? (
            <SkeletonGrid count={8} />
          ) : books.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-zinc-600">
              <Icon name="book-open" size={48} className="mb-4 text-zinc-700" />
              <p className="text-lg mb-2">书架空空如也</p>
              <p className="text-sm mb-6">创建你的第一部小说，开始 AI 辅助创作</p>
              <button
                onClick={() => setShowCreate(true)}
                className="bg-zinc-800 hover:bg-zinc-700 active:scale-95 text-zinc-300 px-6 py-3 rounded-lg transition-all flex items-center gap-2"
              >
                <Icon name="plus" size={16} /> 创建第一部作品
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {books.map((book) => (
                <div
                  key={book.id}
                  onClick={() => navigate(`/book/${book.id}`)}
                  className="group cursor-pointer relative"
                >
                  <div className={`aspect-[3/4] rounded-xl bg-gradient-to-br ${progressColor(book.totalWords || 0)} p-4 flex flex-col justify-end relative overflow-hidden shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all duration-200`}>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                    <div className="relative z-10">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[9px] uppercase tracking-wider text-white/60 font-medium">{progressLabel(book.totalWords || 0)}</span>
                      </div>
                      <h3 className="text-white text-base font-bold leading-tight">{book.title}</h3>
                      <div className="flex items-center gap-2 text-white/50 text-[10px] mt-1">
                        {book.chapterCount > 0 && <span>{book.chapterCount} 章</span>}
                        {book.totalWords > 0 && <span>{formatWords(book.totalWords)} 字</span>}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={(e) => handleEdit(book, e)}
                    className="absolute top-2 left-2 z-20 opacity-0 group-hover:opacity-100 bg-black/40 hover:bg-zinc-700 text-white rounded-lg w-7 h-7 flex items-center justify-center transition-all"
                    title="编辑信息"
                  >
                    <Icon name="edit" size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteBookId(book.id) }}
                    className="absolute top-2 right-2 z-20 opacity-0 group-hover:opacity-100 bg-black/40 hover:bg-red-600 text-white rounded-lg w-7 h-7 flex items-center justify-center transition-all"
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {showCreate && (
            <CreateBookModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
          )}

          {editing && (
            <Modal open onClose={() => setEditing(null)} title="编辑项目信息">
              <div className="p-6">
                <h2 className="text-lg font-bold text-zinc-200 mb-4">编辑项目信息</h2>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-zinc-400 block mb-1">书名 <span className="text-red-400">*</span></label>
                    <input value={editing.title || ''}
                      onChange={e => { setEditing({ ...editing, title: e.target.value }); if (!editTouched) setEditTouched(true) }}
                      onBlur={() => setEditTouched(true)}
                      className={`w-full bg-zinc-800 border rounded-lg px-4 py-2.5 text-sm text-zinc-200 focus:outline-none ${
                        editTouched && !editing.title?.trim() ? 'border-red-500' : 'border-zinc-700 focus:border-zinc-500'
                      }`} />
                    {editTouched && !editing.title?.trim() && (
                      <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
                        <Icon name="alert-triangle" size={12} /> 请输入书名
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="text-xs text-zinc-400 block mb-1">简介</label>
                    <textarea value={editing.description || ''} rows={3}
                      onChange={e => setEditing({ ...editing, description: e.target.value })}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500 resize-none" />
                  </div>
                </div>
                <div className="flex gap-2 mt-4 justify-end">
                  <button onClick={() => setEditing(null)}
                    className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">取消</button>
                  <button onClick={handleSaveEdit}
                    disabled={!editing.title?.trim()}
                    className="bg-zinc-200 hover:bg-white text-zinc-900 px-5 py-2 rounded-lg transition-colors text-sm font-medium disabled:opacity-50">保存</button>
                </div>
              </div>
            </Modal>
          )}
        </div>
      )}

      {showSettings && (
        <SettingsModal
          onClose={() => setShowSettings(false)}
          onModeChanged={() => {}}
        />
      )}

      <ConfirmModal
        open={!!deleteBookId}
        title="删除项目"
        message="确定删除这本书？知识库数据将一并删除，此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteBookId(null)}
      />
    </div>
  )
}
