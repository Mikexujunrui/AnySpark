// ChapterHistoryPanel — 章节版本历史（V4 适配版）
// 数据：GET /api/chapters/{chapterId} 的 versions（content/note/saved_at）
import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import { showToast } from './ui/toast-utils'

interface Version { content: string; note: string | null; saved_at: string }

interface Props {
  bookId: string
  chapterId: string
  onClose: () => void
  onRevert?: (versionId: string) => void
  onVersionSelect?: (versionId: string) => void
}

export default function ChapterHistoryPanel({ bookId, chapterId, onClose, onVersionSelect }: Props) {
  const [versions, setVersions] = useState<Version[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSavedAt, setSelectedSavedAt] = useState<string | null>(null)
  const [preview, setPreview] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`/api/chapters/${chapterId}`)
      .then(r => r.json())
      .then((d) => {
        if (cancelled) return
        setVersions(d.versions || [])
        setLoading(false)
      })
      .catch(() => { if (!cancelled) { setLoading(false); showToast('加载版本历史失败', 'error') } })
    return () => { cancelled = true }
  }, [bookId, chapterId])

  function selectVersion(v: Version) {
    setSelectedSavedAt(v.saved_at)
    setPreview(v.content || '')
    onVersionSelect?.(v.saved_at)
  }

  return (
    <div className="h-full flex flex-col bg-zinc-950 border-r border-zinc-800 w-80 shrink-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-300 flex items-center gap-1.5">
          <Icon name="clock" size={12} /> 版本历史
        </span>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
          <Icon name="x" size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-zinc-500 text-xs gap-2">
            <div className="w-4 h-4 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
            加载中...
          </div>
        ) : versions.length === 0 ? (
          <p className="text-center text-zinc-600 text-xs py-8">暂无版本历史（修改保存时自动记录）</p>
        ) : (
          <div className="p-2 space-y-1.5">
            {versions.map((v, i) => (
              <button
                key={v.saved_at}
                onClick={() => selectVersion(v)}
                className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                  selectedSavedAt === v.saved_at ? 'bg-sky-900/30 border-sky-700/60' : 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-zinc-400">
                    {new Date(v.saved_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="text-[10px] text-zinc-600">{versions.length - i}</span>
                </div>
                <div className="text-[10px] text-zinc-500 mt-0.5 truncate">{v.note || '修改前'}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      {preview && (
        <div className="border-t border-zinc-800 shrink-0 max-h-48 overflow-y-auto px-3 py-2 bg-zinc-900/30">
          <p className="text-[10px] text-zinc-600 uppercase tracking-wide mb-1">版本预览</p>
          <p className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">{preview.slice(0, 600)}{preview.length > 600 ? '…' : ''}</p>
        </div>
      )}
    </div>
  )
}
