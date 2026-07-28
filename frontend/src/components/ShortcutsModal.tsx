import Modal from './ui/Modal'
import Icon from './ui/Icon'

function Kbd({ children }) {
  return (
    <kbd className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-zinc-400">{children}</kbd>
  )
}

function Row({ label, combo }) {
  return (
    <div className="flex items-center justify-between text-zinc-300">
      <span>{label}</span>
      <Kbd>{combo}</Kbd>
    </div>
  )
}

export default function ShortcutsModal({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} title="键盘快捷键">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-zinc-200 flex items-center gap-2">
            <Icon name="keyboard" size={20} aria-label="键盘" /> 键盘快捷键
          </h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800" aria-label="关闭">
            <Icon name="x" size={18} />
          </button>
        </div>
        <div className="space-y-3 text-sm">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">导航</h3>
            <Row label="切换标签页" combo="Ctrl + 1-9" />
            <Row label="会话菜单" combo="Ctrl + ." />
            <Row label="显示快捷键帮助" combo="Ctrl + /" />
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-zinc-800 text-center">
          <p className="text-xs text-zinc-500">按 Ctrl+/ 可随时打开此帮助</p>
        </div>
      </div>
    </Modal>
  )
}
