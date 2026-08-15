// ChapterFindReplace — 章节查找替换面板（V4 适配版）
// 纯前端文本操作（ChaptersPanel 已提供匹配/替换逻辑）
import Icon from './ui/Icon'

interface Props {
  findText: string
  setFindText: (v: string) => void
  replaceText: string
  setReplaceText: (v: string) => void
  caseSensitive: boolean
  setCaseSensitive: (v: boolean) => void
  matches: unknown[]
  matchIndex: number
  onFindNext: () => void
  onFindPrev: () => void
  onReplace: () => void
  onReplaceAll: () => void
  onClose: () => void
  findInputRef?: React.RefObject<HTMLInputElement | null>
}

export default function ChapterFindReplace({
  findText, setFindText, replaceText, setReplaceText,
  caseSensitive, setCaseSensitive, matches, matchIndex,
  onFindNext, onFindPrev, onReplace, onReplaceAll, onClose, findInputRef,
}: Props) {
  return (
    <div className="border-b border-zinc-800 bg-zinc-900/60 px-3 py-2 shrink-0">
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-1.5">
          <input
            ref={findInputRef}
            value={findText}
            onChange={(e) => setFindText(e.target.value)}
            placeholder="查找..."
            className="flex-1 min-w-0 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600"
          />
          <span className="text-[10px] text-zinc-500 shrink-0 w-10 text-center">
            {matches.length > 0 ? `${matchIndex + 1}/${matches.length}` : '0/0'}
          </span>
          <button onClick={onFindPrev} disabled={matches.length === 0} title="上一个 (Shift+Enter)" className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 rounded disabled:opacity-40">
            <Icon name="chevron-up" size={12} />
          </button>
          <button onClick={onFindNext} disabled={matches.length === 0} title="下一个 (Enter)" className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 rounded disabled:opacity-40">
            <Icon name="chevron-down" size={12} />
          </button>
        </div>
        <input
          value={replaceText}
          onChange={(e) => setReplaceText(e.target.value)}
          placeholder="替换为..."
          className="flex-1 min-w-0 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600"
        />
        <button
          onClick={() => setCaseSensitive(!caseSensitive)}
          title="区分大小写"
          className={`p-1.5 rounded ${caseSensitive ? 'bg-sky-900/40 text-sky-300' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700'}`}
        >
          Aa
        </button>
        <button onClick={onReplace} disabled={matches.length === 0} className="text-[11px] px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded disabled:opacity-40">
          替换
        </button>
        <button onClick={onReplaceAll} disabled={matches.length === 0} className="text-[11px] px-2 py-1 bg-amber-900/40 hover:bg-amber-800/50 text-amber-300 rounded disabled:opacity-40">
          全部
        </button>
        <button onClick={onClose} className="p-1 text-zinc-500 hover:text-zinc-300">
          <Icon name="x" size={14} />
        </button>
      </div>
    </div>
  )
}
