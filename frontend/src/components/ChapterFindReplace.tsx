// ChapterFindReplace — find & replace bar for ChaptersPanel (extracted to
// keep ChaptersPanel under ~1100 lines). Pure presentational; all state and
// callbacks live in the parent.
import Icon from './ui/Icon'

interface Props {
  findText: string
  setFindText: (v: string) => void
  replaceText: string
  setReplaceText: (v: string) => void
  caseSensitive: boolean
  setCaseSensitive: (v: boolean) => void
  matches: { start: number; end: number }[]
  matchIndex: number
  onFindNext: () => void
  onFindPrev: () => void
  onReplace: () => void
  onReplaceAll: () => void
  onClose: () => void
  findInputRef?: React.RefObject<HTMLInputElement | null>
}

export default function ChapterFindReplace({
  findText,
  setFindText,
  replaceText,
  setReplaceText,
  caseSensitive,
  setCaseSensitive,
  matches,
  matchIndex,
  onFindNext,
  onFindPrev,
  onReplace,
  onReplaceAll,
  onClose,
  findInputRef,
}: Props) {

  return (
    <div className="border-b border-zinc-800 bg-zinc-900/70 px-6 py-2 shrink-0">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Find row */}
        <div className="flex items-center gap-2 flex-1 min-w-[300px]">
          <div className="relative flex-1">
            <input
              ref={findInputRef}
              type="text"
              value={findText}
              onChange={(e) => setFindText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) onFindPrev(); else onFindNext() }
              }}
              placeholder="查找内容..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
            />
          </div>
          <span className="text-[10px] text-zinc-500 tabular-nums shrink-0 min-w-[60px]">
            {matches.length === 0
              ? (findText ? '无匹配' : '')
              : `${matchIndex + 1} / ${matches.length}`
            }
          </span>
          <button onClick={onFindPrev} disabled={matches.length === 0}
            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors disabled:opacity-30"
            title="上一处 (Shift+F3)">
            <Icon name="arrow-up" size={12} />
          </button>
          <button onClick={onFindNext} disabled={matches.length === 0}
            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors disabled:opacity-30"
            title="下一处 (F3)">
            <Icon name="arrow-down" size={12} />
          </button>
          <button onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 p-1 rounded transition-colors"
            title="关闭 (Esc)">
            <Icon name="x" size={12} />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {/* Replace row */}
        <div className="flex items-center gap-2 flex-1 min-w-[300px]">
          <input
            type="text"
            value={replaceText}
            onChange={(e) => setReplaceText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); onReplace() }
            }}
            placeholder="替换为..."
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          />
          <button onClick={onReplace} disabled={matches.length === 0}
            className="text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
            title="替换当前">
            替换
          </button>
          <button onClick={onReplaceAll} disabled={matches.length === 0}
            className="text-xs bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
            title="全部替换">
            全部替换
          </button>
          <label className="flex items-center gap-1.5 text-[10px] text-zinc-500 select-none cursor-pointer ml-auto shrink-0">
            <input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)}
              className="accent-sky-500" />
            区分大小写
          </label>
        </div>
      </div>
    </div>
  )
}
