import { useState } from 'react'

interface WordCountGoalProps {
  /** 当前字数 */
  current: number
  /** 目标字数（受控） */
  target: number
  /** 目标字数变更 */
  onTargetChange: (target: number) => void
}

/**
 * 字数目标进度条 — 独立组件，可嵌入编辑器工具栏。
 * 点击目标数字可编辑目标字数。
 */
export default function WordCountGoal({ current, target, onTargetChange }: WordCountGoalProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(target || 3000))
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0

  const apply = () => {
    const n = parseInt(draft, 10)
    if (n > 0 && n !== target) onTargetChange(n)
    setEditing(false)
  }

  return (
    <div className="flex items-center gap-2 text-[10px] shrink-0">
      {/* 进度条 */}
      <div className="w-16 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            pct >= 100 ? 'bg-emerald-500' : pct > 70 ? 'bg-amber-500' : 'bg-sky-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* 字数显示 */}
      {editing ? (
        <input
          type="number"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={apply}
          onKeyDown={e => { if (e.key === 'Enter') apply(); if (e.key === 'Escape') setEditing(false) }}
          className="w-14 bg-zinc-800 border border-zinc-600 rounded px-1 py-0.5 text-zinc-200 text-center"
          autoFocus
          min={1}
        />
      ) : (
        <button
          onClick={() => { setDraft(String(target || 3000)); setEditing(true) }}
          className="text-zinc-400 hover:text-zinc-200 tabular-nums transition-colors"
          title="点击设置字数目标"
        >
          {current.toLocaleString()} / {target.toLocaleString()}
        </button>
      )}
    </div>
  )
}