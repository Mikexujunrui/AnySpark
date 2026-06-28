import { useEffect, useRef } from 'react'

export default function ConfirmModal({
  open,
  title = '确认操作',
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}) {
  const confirmRef = useRef(null)

  useEffect(() => {
    if (open) {
      confirmRef.current?.focus()
      function onKey(e) {
        if (e.key === 'Escape') onCancel?.()
        if (e.key === 'Enter') onConfirm?.()
      }
      document.addEventListener('keydown', onKey)
      return () => document.removeEventListener('keydown', onKey)
    }
  }, [open, onConfirm, onCancel])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[100] bg-black/70 flex items-center justify-center" onClick={onCancel}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm mx-4"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-zinc-100 mb-2">{title}</h3>
        {message && <p className="text-sm text-zinc-400 mb-5 leading-relaxed">{message}</p>}
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
          >
            {cancelText}
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className={`px-5 py-2 text-sm font-medium rounded-lg transition-colors ${
              danger
                ? 'bg-red-600 hover:bg-red-500 text-white'
                : 'bg-zinc-200 hover:bg-white text-zinc-900'
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
