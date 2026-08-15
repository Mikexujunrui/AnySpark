import { useRef, useEffect } from 'react'
import Icon from '../ui/Icon'

interface SlashItem {
  name: string
  description: string
  icon?: string
}

interface SlashMenuProps {
  items: SlashItem[]
  selectedIdx: number
  allSkills: { name: string; description: string; icon?: string; type?: string }[]
  onSelect: (item: SlashItem | { name: string; description: string }) => void
  onNavigate: (idx: number) => void
  onClose: () => void
}

export default function SlashMenu({ items, selectedIdx, allSkills, onSelect, onNavigate, onClose }: SlashMenuProps) {
  const ref = useRef<HTMLDivElement>(null)

  // Keyboard navigation (called from parent via DOM hack for textarea integration)
  useEffect(() => {
    const el = ref.current as HTMLDivElement & { _slashNav?: (e: KeyboardEvent) => boolean }
    if (!el) return
    el._slashNav = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); onNavigate(Math.min(selectedIdx + 1, allItems.length - 1)); return true }
      if (e.key === 'ArrowUp') { e.preventDefault(); onNavigate(Math.max(selectedIdx - 1, 0)); return true }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        const target = allItems[selectedIdx]
        if (target) { onSelect(target); onClose() }
        return true
      }
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return true }
      return false
    }
  })

  const hasItems = items.length > 0
  const allItems = hasItems ? items : allSkills

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    const timer = setTimeout(() => document.addEventListener('mousedown', handleClick), 0)
    return () => { clearTimeout(timer); document.removeEventListener('mousedown', handleClick) }
  }, [onClose])

  return (
    <div
      ref={ref}
      data-slash-menu
      className="absolute bottom-full left-0 right-0 mb-1 mx-3 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl max-h-72 overflow-y-auto z-50"
    >
      <div className="py-1">
        <div className="px-3 py-1.5 text-[10px] text-zinc-600 font-semibold uppercase tracking-wider">
          {hasItems ? `快捷命令 (${items.length})` : `技能 (${allSkills.length})`}
        </div>
        {allItems.map((item, i) => (
          <button
            key={item.name}
            onClick={() => { onSelect(item); onClose() }}
            className={`w-full text-left px-3 py-2 flex items-center gap-3 text-xs transition-colors ${
              i === selectedIdx
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
            }`}
          >
            <Icon name={(item.icon || 'terminal') as any} size={14} className="text-zinc-500 shrink-0" />
            <div className="min-w-0 flex-1">
              <span className="font-medium text-zinc-200">{item.name}</span>
              <span className="ml-2 text-zinc-500">{item.description}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
