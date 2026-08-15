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

export default function CommandPalette({ open, onClose, onSwitchTab }: { open: boolean; onClose: () => void; onSwitchTab?: (tab: string) => void }) {
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
    { id: 'chat', label: '对话', category: '写作', icon: 'message-circle', action: () => onSwitchTab?.('chat'), shortcut: 'Ctrl+1' },
    { id: 'chapters', label: '章节', category: '写作', icon: 'file-text', action: () => onSwitchTab?.('chapters'), shortcut: 'Ctrl+2' },
    { id: 'storytree', label: '叙事树', category: '写作', icon: 'git-branch', action: () => onSwitchTab?.('storytree'), shortcut: 'Ctrl+3' },
    { id: 'workflow', label: '工作流', category: '写作', icon: 'settings', action: () => onSwitchTab?.('workflow'), shortcut: 'Ctrl+4' },
    { id: 'search', label: '搜索', category: '写作', icon: 'search', action: () => onSwitchTab?.('search') },
    { id: 'knowledge', label: '知识库', category: '设定', icon: 'database', action: () => onSwitchTab?.('knowledge'), shortcut: 'Ctrl+5' },
    { id: 'outline', label: '大纲', category: '设定', icon: 'list', action: () => onSwitchTab?.('outline'), shortcut: 'Ctrl+6' },
    { id: 'materials', label: '资料', category: '设定', icon: 'book-open', action: () => onSwitchTab?.('materials') },
    { id: 'review', label: '评审团', category: '辅助', icon: 'clipboard-list', action: () => onSwitchTab?.('review'), shortcut: 'Ctrl+7' },
    { id: 'brief', label: '项目简介', category: '辅助', icon: 'file-text', action: () => onSwitchTab?.('brief') },
    { id: 'bias', label: 'AI 倾向', category: '辅助', icon: 'brain', action: () => onSwitchTab?.('bias') },
    { id: 'batch', label: '批量操作', category: '工具', icon: 'layers', action: () => onSwitchTab?.('batch') },
    { id: 'templates', label: '模板库', category: '工具', icon: 'copy', action: () => onSwitchTab?.('templates') },
    { id: 'tools', label: '扩展工具', category: '工具', icon: 'wrench', action: () => onSwitchTab?.('tools') },
    { id: 'play', label: '互动推演', category: '工具', icon: 'compass', action: () => onSwitchTab?.('play') },
    { id: 'role', label: '角色推演', category: '工具', icon: 'users', action: () => onSwitchTab?.('role') },
    { id: 'dims', label: '探索维度', category: '工具', icon: 'grid', action: () => onSwitchTab?.('dims') },
    { id: 'impact', label: '影响分析', category: '工具', icon: 'zap', action: () => onSwitchTab?.('impact') },
    { id: 'upload', label: '上传消化', category: '工具', icon: 'upload', action: () => onSwitchTab?.('upload') },
    { id: 'export', label: '导出全书', category: '工具', icon: 'download', action: () => {} },
  ], [navigate, onSwitchTab])

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
