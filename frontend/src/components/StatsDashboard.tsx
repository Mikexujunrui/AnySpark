// StatsDashboard — V4 适配版（书架统计面板）
// 数据源：/api/stats（写作指标：修改率/提问率/按天分布）+ /api/books（章节统计）
import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import StatCard from './ui/StatCard'
import { showToast } from './ui/toast-utils'

function formatWords(n: number | null | undefined): string {
  if (n == null) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

interface BookStat { id: string; title: string; chapterCount: number; totalChars: number }

export default function StatsDashboard() {
  const [stats, setStats] = useState<Record<string, any> | null>(null)
  const [books, setBooks] = useState<BookStat[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [s, b] = await Promise.all([
          fetch('/api/stats').then(r => r.json()).catch(() => null),
          fetch('/api/books').then(r => r.json()).catch(() => []),
        ])
        if (cancelled) return
        setStats(s)
        setBooks(Array.isArray(b) ? b : [])
      } catch (e) {
        showToast('加载统计失败', 'error')
      }
      if (!cancelled) setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-full text-zinc-500 text-sm gap-2">
      <div className="w-5 h-5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
      加载统计...
    </div>
  }

  const totalChapters = books.reduce((s, b) => s + (b.chapterCount || 0), 0)
  const totalChars = books.reduce((s, b) => s + (b.totalChars || 0), 0)
  const modify = stats?.modify_rate || {}
  const question = stats?.question_rate || {}
  const byDay: { bucket: string; rate: number; total: number }[] = modify.by_day || []
  const maxDayTotal = Math.max(1, ...byDay.map(d => d.total || 0))

  return (
    <div className="h-full overflow-y-auto p-5 space-y-5">
      {/* 概览卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon="book-open" label="项目数" value={books.length} sub="全部项目" accent="sky" />
        <StatCard icon="file-text" label="章节数" value={totalChapters} sub="全部项目合计" accent="emerald" />
        <StatCard icon="type" label="总字数" value={formatWords(totalChars)} sub="全部项目合计" accent="purple" />
        <StatCard
          icon="check-circle"
          label="AI 采纳率"
          value={modify.overall != null ? `${Math.round(modify.overall * 100)}%` : '-'}
          sub={modify.total ? `采纳 ${modify.accepted || 0} / 变更 ${modify.changed || 0} / 共 ${modify.total}` : '暂无数据'}
          accent="amber"
        />
      </div>

      {/* 项目明细 */}
      <div>
        <h3 className="text-xs text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
          <Icon name="database" size={12} /> 项目明细
        </h3>
        <div className="space-y-1.5">
          {books.length === 0 && <p className="text-sm text-zinc-600">暂无项目</p>}
          {books.map(b => (
            <div key={b.id} className="flex items-center gap-3 px-3 py-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
              <span className="text-sm text-zinc-200 truncate flex-1">{b.title || b.id}</span>
              <span className="text-xs text-zinc-500 shrink-0">{b.chapterCount || 0} 章</span>
              <span className="text-xs text-zinc-500 shrink-0 w-16 text-right">{formatWords(b.totalChars)} 字</span>
            </div>
          ))}
        </div>
      </div>

      {/* 每日修改率 */}
      {byDay.length > 0 && (
        <div>
          <h3 className="text-xs text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Icon name="activity" size={12} /> 每日 AI 采纳分布
          </h3>
          <div className="flex items-end gap-1.5 h-28 px-2 pt-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
            {byDay.map(d => (
              <div key={d.bucket} className="flex-1 flex flex-col items-center gap-1 min-w-0" title={`${d.bucket}: ${d.total} 次（采纳率 ${Math.round((d.rate || 0) * 100)}%）`}>
                <span className="text-[9px] text-zinc-500">{d.total}</span>
                <div
                  className={`w-full rounded-t ${(d.rate || 0) > 0.5 ? 'bg-amber-500/70' : (d.rate || 0) > 0 ? 'bg-sky-500/60' : 'bg-zinc-700'}`}
                  style={{ height: `${Math.max(6, ((d.total || 0) / maxDayTotal) * 70)}px` }}
                />
                <span className="text-[9px] text-zinc-600 truncate w-full text-center">{d.bucket.slice(5)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 提问率 */}
      {question.total_questions != null && (
        <div>
          <h3 className="text-xs text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Icon name="message-circle" size={12} /> 提问密度
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <StatCard icon="help-circle" label="每千字提问" value={question.overall_per_1k_chars?.toFixed(1) ?? '-'} sub="AI 提问密度" accent="sky" />
            <StatCard icon="message-circle" label="总提问数" value={question.total_questions ?? 0} sub="全部会话" accent="emerald" />
            <StatCard icon="type" label="总字数" value={formatWords(question.total_chars)} sub="统计口径" accent="purple" />
          </div>
        </div>
      )}
    </div>
  )
}
