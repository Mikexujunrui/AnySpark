import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import Icon from './ui/Icon.jsx'
import LoadingState from './ui/Skeleton.jsx'
import Modal from './ui/Modal.jsx'
import { showToast } from './ui/Toast.jsx'

export default function ReferenceBooksPanel({ bookId }) {
  const [references, setReferences] = useState([])
  const [allBooks, setAllBooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showPicker, setShowPicker] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [refRes, booksData] = await Promise.all([
        fetch(`/api/books/${bookId}/references`),
        api.getBooks(),
      ])
      const refData = await refRes.json()
      const refIds = refData.reference_book_ids || []
      const refBooks = refData.references || []
      setReferences(refBooks)
      // Filter out current book and already-referenced books
      setAllBooks((Array.isArray(booksData) ? booksData : []).filter(
        b => b.id !== bookId && !refIds.includes(b.id)
      ))
    } catch (e) {
      showToast('加载参考书失败', 'error')
    }
    setLoading(false)
  }, [bookId])

  useEffect(() => { loadData() }, [loadData])

  async function addReference(refBookId) {
    const refIds = references.map(r => r.id).concat(refBookId)
    try {
      await api.setReferences(bookId, refIds)
      setShowPicker(false)
      loadData()
      showToast('参考书已添加', 'success')
    } catch (e) {
      showToast('添加失败', 'error')
    }
  }

  async function removeReference(refBookId) {
    const refIds = references.filter(r => r.id !== refBookId).map(r => r.id)
    try {
      await api.setReferences(bookId, refIds)
      loadData()
      showToast('已移除', 'success')
    } catch (e) {
      showToast('移除失败', 'error')
    }
  }

  if (loading) {
    return <LoadingState text="加载参考书..." />
  }

  const colors = [
    'from-rose-600 to-orange-500', 'from-violet-600 to-indigo-500',
    'from-emerald-600 to-teal-500', 'from-amber-500 to-yellow-400',
    'from-cyan-500 to-blue-500', 'from-fuchsia-600 to-pink-500',
  ]

  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Icon name="book-open" size={20} /> 参考书
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            指定其他项目为参考书，其角色/设定/关系会以只读方式注入写作上下文
          </p>
        </div>
        {allBooks.length > 0 && (
          <button onClick={() => setShowPicker(true)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-2">
            <Icon name="plus" size={14} /> 添加参考书
          </button>
        )}
      </header>

      {references.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-600">
          <Icon name="book-open" size={36} className="mb-3 text-zinc-700" />
          <p className="text-sm mb-1">未设置参考书</p>
          <p className="text-xs mb-4">如同人小说可指定原著为参考书，写作时自动参考原著设定</p>
          {allBooks.length > 0 ? (
            <button onClick={() => setShowPicker(true)}
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-5 py-2 rounded-lg transition-colors text-sm flex items-center gap-2">
              <Icon name="plus" size={14} /> 选择参考书
            </button>
          ) : (
            <p className="text-xs text-zinc-600">当前没有其他项目可选</p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {references.map((book, i) => (
            <div key={book.id}
              className="relative group bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors">
              <div className={`h-2 bg-gradient-to-r ${colors[i % colors.length]}`} />
              <div className="p-4">
                <h3 className="text-sm font-semibold text-zinc-200 mb-2">{book.title}</h3>
                <div className="flex gap-3 text-[10px] text-zinc-500 mb-3">
                  {book.entityCount > 0 && <span>{book.entityCount} 个实体</span>}
                  {book.chapterCount > 0 && <span>{book.chapterCount} 章</span>}
                </div>
                <button onClick={() => removeReference(book.id)}
                  className="text-xs text-zinc-600 hover:text-red-400 transition-colors flex items-center gap-1">
                  <Icon name="x" size={12} /> 移除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {references.length > 0 && (
        <div className="mt-8 p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl">
          <h3 className="text-sm font-semibold text-zinc-300 mb-2 flex items-center gap-2">
            <Icon name="info" size={14} /> 提示
          </h3>
          <p className="text-xs text-zinc-500 leading-relaxed">
            参考书的知识图谱（角色名、设定、关系）会自动注入写作上下文和评审团"原著党"评审中。
            AI 写同人时会自动遵守原著设定。如需取消，点击每个参考书下方的"移除"按钮即可。
          </p>
        </div>
      )}

      {/* Book Picker Modal */}
      {showPicker && (
        <Modal open onClose={() => setShowPicker(false)} title="选择参考书" size="lg">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-4">选择参考书</h2>
            {allBooks.length === 0 ? (
              <p className="text-zinc-500 text-sm">没有可选项目</p>
            ) : (
              <div className="space-y-2">
                {allBooks.map((b, i) => (
                  <div key={b.id}
                    onClick={() => addReference(b.id)}
                    className={`flex items-center gap-4 p-3 rounded-lg cursor-pointer hover:bg-zinc-800 transition-colors border border-zinc-800 hover:border-zinc-600`}>
                    <div className={`w-8 h-8 rounded-md bg-gradient-to-br ${colors[i % colors.length]} flex items-center justify-center text-white text-xs font-bold shrink-0`}>
                      {b.title.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200 font-medium truncate">{b.title}</p>
                      <p className="text-[10px] text-zinc-500">
                        {b.entityCount || 0} 实体 · {b.chapterCount || 0} 章
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowPicker(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg transition-colors text-sm">取消</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
