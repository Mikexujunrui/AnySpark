import { useState } from 'react'
import Icon from './ui/Icon.jsx'
import Modal from './ui/Modal.jsx'

export default function CreateBookModal({ onClose, onCreate }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [touched, setTouched] = useState(false)

  function handleSubmit(e) {
    e.preventDefault()
    if (!title.trim()) return
    onCreate({ title: title.trim(), description: description.trim() })
  }

  const titleError = touched && !title.trim()
  const titleValid = title.trim().length > 0

  return (
    <Modal open onClose={onClose} title="创建新项目">
      <div className="p-6">
        <h2 className="text-lg font-bold mb-4">创建新项目</h2>
        <form onSubmit={handleSubmit}>
          <label className="block text-sm text-zinc-400 mb-1">书名 <span className="text-red-400">*</span></label>
          <div className="relative">
            <input
              autoFocus
              value={title}
              onChange={(e) => { setTitle(e.target.value); if (!touched) setTouched(true) }}
              onBlur={() => setTouched(true)}
              className={`w-full bg-zinc-800 border rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none pr-8 ${
                titleError ? 'border-red-500 focus:border-red-500' : titleValid ? 'border-emerald-500 focus:border-emerald-500' : 'border-zinc-700 focus:border-zinc-500'
              }`}
              placeholder="输入书名..."
            />
            {titleError && (
              <Icon name="alert-circle" size={16} className="absolute right-2 top-1/2 -translate-y-1/2 text-red-400" />
            )}
            {titleValid && (
              <Icon name="check-circle" size={16} className="absolute right-2 top-1/2 -translate-y-1/2 text-emerald-400" />
            )}
          </div>
          {titleError && (
            <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
              <Icon name="alert-triangle" size={12} /> 请输入书名
            </p>
          )}
          <label className="block text-sm text-zinc-400 mb-1 mt-3">简介（可选）</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500 mb-6 resize-none h-20"
            placeholder="简短描述你的故事..."
          />
          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors">取消</button>
            <button type="submit"
              className="px-5 py-2 text-sm bg-zinc-100 text-zinc-900 rounded-lg font-medium hover:bg-white transition-colors disabled:opacity-50"
              disabled={!title.trim()}>创建</button>
          </div>
        </form>
      </div>
    </Modal>
  )
}
