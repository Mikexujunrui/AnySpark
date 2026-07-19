import Icon from './ui/Icon'

export default function ExportMenu({ open, onClose, onExport }) {
  if (!open) return null
  return (
    <>
      <div className="fixed inset-0 z-[9998]" onClick={onClose} />
      <div className="absolute right-0 top-full mt-1 z-[9999] w-40 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden" role="menu" aria-label="导出全文">
        <div className="px-3 py-2 border-b border-zinc-800">
          <span className="text-xs font-medium text-zinc-400">导出全文</span>
        </div>
        <div className="py-1">
          <button
            onClick={() => onExport('txt')}
            className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors flex items-center gap-2"
            role="menuitem"
          >
            <Icon name="file-text" size={14} className="text-zinc-500" /> TXT 纯文本
          </button>
          <button
            onClick={() => onExport('docx')}
            className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors flex items-center gap-2"
            role="menuitem"
          >
            <Icon name="file-pen" size={14} className="text-zinc-500" /> DOCX 文档
          </button>
          <button
            onClick={() => onExport('epub')}
            className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors flex items-center gap-2"
            role="menuitem"
          >
            <Icon name="book" size={14} className="text-zinc-500" /> EPUB 电子书
          </button>
        </div>
        <div className="px-3 py-2 border-t border-zinc-800">
          <span className="text-xs font-medium text-zinc-400">知识库归档</span>
        </div>
        <div className="py-1">
          <button
            onClick={() => onExport('spark')}
            className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors flex items-center gap-2"
            role="menuitem"
          >
            <Icon name="archive" size={14} className="text-amber-500" /> .spark 归档
          </button>
        </div>
      </div>
    </>
  )
}
