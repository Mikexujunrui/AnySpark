import Icon from './ui/Icon'

export default function SessionMenu({ open, sessions, sessionId, onSwitch, onNew, onDelete, onClose }) {
  if (!open) return null
  return (
    <>
      <div className="fixed inset-0 z-[9998]" onClick={onClose} />
      <div className="absolute right-0 top-full mt-1 z-[9999] w-64 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden" role="menu" aria-label="会话列表">
        <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
          <span className="text-xs font-medium text-zinc-400">会话列表</span>
          <button
            onClick={onNew}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
            aria-label="新建会话"
          >
            <Icon name="plus" size={12} /> 新建
          </button>
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {sessions.map(s => (
            <div
              key={s.id}
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors ${
                s.id === sessionId ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
              }`}
              onClick={() => onSwitch(s.id)}
              role="menuitem"
            >
              <Icon name="message-circle" size={14} className="shrink-0 text-zinc-600" />
              <span className="flex-1 truncate text-sm">{s.title}</span>
              <span className="text-[10px] text-zinc-600 shrink-0">{s.messageCount || 0}</span>
              {sessions.length > 1 && (
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(s.id) }}
                  className="text-zinc-600 hover:text-red-400 p-0.5 shrink-0"
                  aria-label={`删除会话 ${s.title}`}
                >
                  <Icon name="trash" size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
