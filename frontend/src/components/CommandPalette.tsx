import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import Icon from './ui/Icon'

interface Command {
  id: string
  label: string
  category: string
  icon: string
  action: () => void
  shortcut?: string
}

export default function CommandPalette({ open, onClose }) {
  const [query, setQuery] = useState('')
  const [selectedIdx, setSelectedIdx] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIdx(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); onClose() }
      if (e.key === 'k' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); onClose() }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  const commands: Command[] = useMemo(() => [
    { id: 'bookshelf', label: '书架', category: '导航', icon: 'home', action: () => navigate('/') },
    { id: 'chat', label: '对话面板', category: '面板', icon: 'message-circle', action: () => {}, shortcut: 'Ctrl+1' },
    { id: 'chapters', label: '章节面板', category: '面板', icon: 'file-text', action: () => {}, shortcut: 'Ctrl+2' },
    { id: 'characters', label: '角色面板', category: '面板', icon: 'users', action: () => {}, shortcut: 'Ctrl+5' },
    { id: 'outline', label: '大纲面板', category: '面板', icon: 'list', action: () => {}, shortcut: 'Ctrl+9' },
    { id: 'knowledge', label: '知识库', category: '面板', icon: 'database', action: () => {}, shortcut: 'Ctrl+8' },
    { id: 'review', label: '评审团', category: '面板', icon: 'clipboard-list', action: () => {}, shortcut: 'Ctrl+14' },
    { id: 'settings', label: 'API 设置', category: '设置', icon: 'settings', action: () => {} },
    { id: 'autopilot', label: 'Autopilot 自主写作', category: '写作', icon: 'bot', action: () => {} },
    { id: 'transform', label: '全书变换', category: '写作', icon: 'layers', action: () => {} },
    { id: 'export', label: '导出全书', category: '写作', icon: 'download', action: () => {} },
    { id: 'import', label: '导入小说', category: '写作', icon: 'upload', action: () => {} },
    { id: 'search', label: '全文搜索', category: '工具', icon: 'search', action: () => {} },
    { id: 'stats', label: '写作统计', category: '工具', icon: 'bar-chart', action: () => navigate('/') },
  ], [navigate])

  const filtered = useMemo(() => {
    if (!query) return commands
    const q = query.toLowerCase()
    return commands.filter(c =>
      c.label.toLowerCase().includes(q) || c.category.toLowerCase().includes(q)
    )
  }, [query, commands])

  useEffect(() => { setSelectedIdx(0) }, [query])

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)) }
    if (e.key === 'Enter' && filtered[selectedIdx]) {
      e.preventDefault()
      filtered[selectedIdx].action()
      onClose()
    }
  }

  // Group by category
  const grouped = useMemo(() => {
    const map = {}
    filtered.forEach(c => {
      if (!map[c.category]) map[c.category] = []
      map[c.category].push(c)
    })
    return Object.entries(map)
  }, [filtered])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[150] bg-black/60 flex items-start justify-center pt-[15vh]"
          onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -10 }}
            transition={{ duration: 0.15 }}
            className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
              <Icon name="search" size={14} className="text-zinc-500" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="搜索命令..."
                className="flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 outline-none"
              />
              <kbd className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">Esc</kbd>
            </div>
            <div className="max-h-72 overflow-y-auto p-2">
              {grouped.map(([category, cmds]) => (
                <div key={category} className="mb-1">
                  <div className="text-[10px] text-zinc-600 px-3 py-1 font-medium uppercase tracking-wider">{category}</div>
                  {(cmds as Command[]).map((cmd, i) => {
                    const globalIdx = filtered.indexOf(cmd)
                    const isSelected = globalIdx === selectedIdx
                    return (
                      <button
                        key={cmd.id}
                        onClick={() => { cmd.action(); onClose() }}
                        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left ${
                          isSelected ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
                        }`}
                      >
                        <Icon name={cmd.icon} size={14} className={isSelected ? 'text-accent' : 'text-zinc-600'} />
                        <span className="flex-1">{cmd.label}</span>
                        {cmd.shortcut && (
                          <kbd className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">{cmd.shortcut}</kbd>
                        )}
                      </button>
                    )
                  })}
                </div>
              ))}
              {filtered.length === 0 && (
                <div className="text-center text-zinc-600 py-8 text-sm">无匹配命令</div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
