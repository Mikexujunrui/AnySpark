import { useEffect, useState } from 'react'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import { showToast } from './ui/toast-utils'
import { api } from '../api'

export interface VersionData {
  id: string
  version_label?: string
  message?: string
  is_current?: boolean
  has_diff?: boolean
  timestamp?: string
  word_count?: number
  content?: string
  original_content?: string | null
  patches_summary?: unknown[]
}

interface ChapterHistoryPanelProps {
  bookId: string
  chapterId: string
  onClose: () => void
  onRevert: () => void
  onVersionSelect?: (versionId: string) => void
}

export default function ChapterHistoryPanel({
  bookId,
  chapterId,
  onClose,
  onRevert,
  onVersionSelect,
}: ChapterHistoryPanelProps) {
  const [history, setHistory] = useState<VersionData[]>([])
  const [loading, setLoading] = useState(false)
  const [revertTarget, setRevertTarget] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  useEffect(() => { loadHistory() }, [bookId, chapterId])

  async function loadHistory() {
    setLoading(true)
    try {
      const data = await api.getChapterHistory(bookId, chapterId)
      setHistory(Array.isArray(data) ? data as VersionData[] : [])
    } catch (e) {
      showToast('加载版本历史失败', 'error')
    }
    setLoading(false)
  }

  async function confirmRevert() {
    if (!revertTarget) return
    try {
      await api.revertChapter(bookId, chapterId, revertTarget)
      loadHistory()
      onRevert()
      showToast('已回退', 'success')
    } catch (e) {
      showToast('回退失败', 'error')
    }
    setRevertTarget(null)
  }

  async function handleDeleteVersion(versionId: string) {
    try {
      await api.deleteChapterVersion(bookId, chapterId, versionId)
      loadHistory()
      showToast('版本已删除', 'success')
    } catch (e) {
      showToast('删除失败', 'error')
    }
    setDeleteTarget(null)
  }

  function handleClickVersion(v: VersionData) {
    if (onVersionSelect) {
      onVersionSelect(v.id)
    }
  }

  return (
    <>
      <div className="border-b border-zinc-800 bg-zinc-900/80 max-h-64 overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-2 border-b border-zinc-800/50">
          <span className="text-xs font-semibold text-zinc-400">版本历史</span>
          <button onClick={onClose} className="text-xs text-zinc-600 hover:text-zinc-300 flex items-center gap-1">
            <Icon name="x" size={12} /> 关闭
          </button>
        </div>
        {loading ? (
          <div className="p-4 text-xs text-zinc-600 text-center">加载中...</div>
        ) : history.length === 0 ? (
          <div className="p-4 text-xs text-zinc-600 text-center">暂无版本历史</div>
        ) : (
          <div className="divide-y divide-zinc-800/50">
            {history.map(v => (
              <div
                key={v.id}
                className={`px-6 py-2 flex items-center gap-3 text-xs transition-colors cursor-pointer hover:bg-zinc-800/50`}
                onClick={() => handleClickVersion(v)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`shrink-0 text-[10px] px-1.5 rounded font-mono ${
                      v.version_label?.includes('.')
                        ? 'bg-blue-900/50 text-blue-400'
                        : 'bg-zinc-700 text-zinc-300'
                    }`}>
                      {v.version_label || `v${history.length}`}
                    </span>
                    <span className="text-zinc-300 font-medium truncate">{v.message || '未命名版本'}</span>
                    {v.is_current && (
                      <span className="shrink-0 text-[10px] bg-emerald-900/50 text-emerald-400 px-1.5 rounded">当前</span>
                    )}
                    {v.has_diff && (
                      <span className="shrink-0 text-[10px] bg-orange-900/50 text-orange-400 px-1.5 rounded">局部</span>
                    )}
                  </div>
                  <div className="text-zinc-600 text-[10px] mt-0.5">
                    {v.timestamp?.slice(0, 16).replace('T', ' ')} · {v.word_count} 字
                  </div>
                </div>
                {!v.is_current && (
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); setRevertTarget(v.id) }}
                      className="text-[10px] text-zinc-500 hover:text-amber-400 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors"
                    >
                      回退
                    </button>
                    {history.length > 1 && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(v.id) }}
                        className="text-[10px] text-zinc-600 hover:text-red-400 bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors"
                      >
                        删除
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {revertTarget && (
        <ConfirmModal
          open={true}
          title="确认回退"
          message="回退后当前版本将不再是当前版本。确定要回退吗？"
          onConfirm={confirmRevert}
          onCancel={() => setRevertTarget(null)}
        />
      )}
      {deleteTarget && (
        <ConfirmModal
          open={true}
          title="确认删除版本"
          message="删除后不可恢复。确定要删除此版本吗？"
          danger
          onConfirm={() => handleDeleteVersion(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  )
}
