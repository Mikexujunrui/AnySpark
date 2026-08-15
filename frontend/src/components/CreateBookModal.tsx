// CreateBookModal — 新建项目（V4 适配版：POST /api/books）
// S135：创建职责单一化——本组件只收集输入，实际 POST/刷新/toast 由父组件
// onCreate 完成（此前组件自 POST + 父组件再 POST = 双重创建 → 成功+已存在同时弹）。
import { useState } from 'react'
import Modal from './ui/Modal'
import Icon from './ui/Icon'

export default function CreateBookModal({ onClose, onCreate }: { onClose: () => void; onCreate?: (data: { title: string }) => Promise<boolean> }) {
  const [title, setTitle] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleCreate() {
    if (!title.trim() || saving) return
    setSaving(true)
    try {
      // 父组件负责创建 + 刷新 + toast；返回 true 才关窗（失败保持打开可重试）
      const ok = await onCreate?.({ title: title.trim() })
      if (ok) onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="新建项目">
      <div className="p-6 space-y-4">
        <div>
          <label className="text-xs text-zinc-400 block mb-1.5">项目名（书名）</label>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
            placeholder="输入项目名，如：雾城之钥"
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600"
          />
          <p className="text-[11px] text-zinc-600 mt-1.5">每个项目拥有独立的知识库、章节、图谱与上传区</p>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors">
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={!title.trim() || saving}
            className="px-5 py-2 text-sm font-medium text-white bg-sky-600 hover:bg-sky-500 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-lg transition-colors flex items-center gap-1.5"
          >
            {saving ? <Icon name="circle" size={12} className="animate-spin" /> : <Icon name="plus" size={14} />}
            {saving ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
