import { useState } from 'react'
import Icon from '../../../components/ui/Icon'

interface SnapshotPanelProps {
  state: Record<string, unknown> | null
  loading?: boolean
}

/** 结构化状态快照面板 — 展示当前推演的运行时状态。 */
export default function SnapshotPanel({ state, loading }: SnapshotPanelProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <span className="w-3 h-3 border-2 border-zinc-600/30 border-t-zinc-600 rounded-full animate-spin" />
          加载状态...
        </div>
      </div>
    )
  }

  if (!state || Object.keys(state).length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-zinc-600 gap-2 p-6">
        <Icon name="activity" size={20} className="text-zinc-700" />
        <p className="text-xs">暂无推演状态</p>
        <p className="text-[10px] text-zinc-700 text-center">开始推演后，每回合的状态变化将在此显示</p>
      </div>
    )
  }

  const toggleSection = (key: string) => {
    setCollapsed(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-4 py-3 border-b border-zinc-800/50">
        <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">推演状态</h3>
      </div>
      <div className="p-3 space-y-1.5">
        {/* On Stage */}
        {renderArraySection('on_stage', state, '在场角色', collapsed, toggleSection)}

        {/* Scene / Location / Time */}
        {renderStringField(state, 'scene', '场景')}
        {renderStringField(state, 'location', '位置')}
        {renderStringField(state, 'time', '时间')}

        {/* Characters */}
        {renderCharactersSection(state, collapsed, toggleSection)}

        {/* Threads */}
        {renderArraySection('threads', state, '未解决线索', collapsed, toggleSection)}

        {/* Inventory */}
        {renderArraySection('inventory', state, '物品', collapsed, toggleSection)}

        {/* World Flags */}
        {renderObjectSection('world_flags', state, '世界标记', collapsed, toggleSection)}
      </div>
    </div>
  )
}

function renderStringField(state: Record<string, unknown>, key: string, label: string) {
  const value = state[key]
  if (!value) return null
  return (
    <div className="flex items-start gap-2 py-1">
      <span className="text-[10px] text-zinc-600 shrink-0 w-12">{label}</span>
      <span className="text-[11px] text-zinc-300 break-words">{String(value).slice(0, 80)}</span>
    </div>
  )
}

function renderArraySection(
  key: string, state: Record<string, unknown>, label: string,
  collapsed: Record<string, boolean>, toggle: (k: string) => void,
) {
  const items = state[key]
  if (!Array.isArray(items) || items.length === 0) return null
  const isCollapsed = collapsed[key]

  return (
    <div className="border-t border-zinc-800/30 pt-2 mt-2">
      <button
        onClick={() => toggle(key)}
        className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 hover:text-zinc-300 transition-colors w-full text-left"
      >
        <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} size={10} />
        {label}
        <span className="text-zinc-700 font-mono">({items.length})</span>
      </button>
      {!isCollapsed && (
        <div className="mt-1 space-y-0.5">
          {items.map((item, i) => (
            <p key={i} className="text-[10px] text-zinc-400 pl-4 leading-relaxed">
              &#8226; {String(item).slice(0, 60)}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function renderObjectSection(
  key: string, state: Record<string, unknown>, label: string,
  collapsed: Record<string, boolean>, toggle: (k: string) => void,
) {
  const obj = state[key]
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null
  const entries = Object.entries(obj as Record<string, unknown>)
  if (entries.length === 0) return null
  const isCollapsed = collapsed[key]

  return (
    <div className="border-t border-zinc-800/30 pt-2 mt-2">
      <button
        onClick={() => toggle(key)}
        className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 hover:text-zinc-300 transition-colors w-full text-left"
      >
        <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} size={10} />
        {label}
        <span className="text-zinc-700 font-mono">({entries.length})</span>
      </button>
      {!isCollapsed && (
        <div className="mt-1 space-y-0.5">
          {entries.map(([k, v]) => {
            const displayText = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)
            return (
              <p key={k} className="text-[10px] pl-4 leading-relaxed">
                <span className="text-zinc-500">{k}: </span>
                <span className="text-zinc-400">{displayText.slice(0, 50)}</span>
              </p>
            )
          })}
        </div>
      )}
    </div>
  )
}

function renderCharactersSection(
  state: Record<string, unknown>,
  collapsed: Record<string, boolean>, toggle: (k: string) => void,
) {
  const chars = state.characters
  if (!chars || typeof chars !== 'object' || Array.isArray(chars)) return null
  const entries = Object.entries(chars as Record<string, unknown>)
  if (entries.length === 0) return null
  const key = 'characters'
  const isCollapsed = collapsed[key]

  return (
    <div className="border-t border-zinc-800/30 pt-2 mt-2">
      <button
        onClick={() => toggle(key)}
        className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 hover:text-zinc-300 transition-colors w-full text-left"
      >
        <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} size={10} />
        角色状态
        <span className="text-zinc-700 font-mono">({entries.length})</span>
      </button>
      {!isCollapsed && (
        <div className="mt-1 space-y-2">
          {entries.map(([name, info]) => (
            <div key={name} className="bg-zinc-900/50 rounded-lg p-2 border border-zinc-800/50">
              <p className="text-[11px] text-zinc-300 font-medium mb-1">{name}</p>
              {info && typeof info === 'object' && (
                <div className="space-y-0.5">
                  {Object.entries(info as Record<string, unknown>).map(([k, v]) => {
                    const txt = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)
                    return (
                      <p key={k} className="text-[9px] leading-relaxed">
                        <span className="text-zinc-600">{k}: </span>
                        <span className="text-zinc-400">{txt.slice(0, 40)}</span>
                      </p>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
