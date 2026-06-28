import { useState } from 'react'
import Icon from '../ui/Icon.jsx'

const OP_LABELS = {
  insert_after: '后方插入',
  insert_before: '前方插入',
  replace: '替换',
  delete: '删除',
  append: '追加末尾',
  prepend: '插入开头',
}

const OP_ICONS = {
  insert_after: 'chevron-down',
  insert_before: 'chevron-up',
  replace: 'refresh',
  delete: 'trash',
  append: 'plus',
  prepend: 'plus',
}

export default function PatchNotification({ data }) {
  const [expanded, setExpanded] = useState(false)

  if (!data || data.error) return null

  const { chapter_title, operations, patched_count, total_count, word_count } = data

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-3 my-2">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon name="edit" size={14} />
          <span className="text-xs font-semibold text-zinc-300 truncate">
            章节编辑: {chapter_title}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/50 text-emerald-400">
            {patched_count}/{total_count} 成功
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {expanded ? '收起' : '展开'}
          </button>
        </div>
      </div>

      {/* Operations */}
      <div className="space-y-1">
        {operations.slice(0, expanded ? undefined : 3).map((op, i) => (
          <div
            key={i}
            className={`flex items-start gap-2 border rounded-lg px-2.5 py-1.5 text-xs transition-colors ${
              op.success
                ? 'border-emerald-700 bg-emerald-950/30 text-emerald-400'
                : 'border-red-700 bg-red-950/30 text-red-400'
            }`}
          >
            <Icon name={OP_ICONS[op.op] || 'edit'} size={12} className="mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{OP_LABELS[op.op] || op.op}</span>
                <span className={`shrink-0 ${op.success ? 'text-emerald-400' : 'text-red-400'}`}>
                  {op.success ? '✓' : '✗'}
                </span>
              </div>
              {op.content && (
                <div className="text-[10px] text-zinc-500 mt-0.5 truncate">
                  {op.content}
                </div>
              )}
              {op.new_text && (
                <div className="text-[10px] text-zinc-500 mt-0.5 truncate">
                  → {op.new_text}
                </div>
              )}
              {op.error && (
                <div className="text-[10px] text-red-500 mt-0.5">
                  {op.error}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      {!expanded && operations.length > 3 && (
        <div className="text-[10px] text-zinc-500 mt-1.5 text-center">
          还有 {operations.length - 3} 个操作...
        </div>
      )}
      <div className="text-[10px] text-zinc-600 mt-2 text-right">
        总字数: {word_count}
      </div>
    </div>
  )
}
