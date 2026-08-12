// StatsDashboard — 作者视角写作统计面板（S101 重写）
// 美术对齐老版本：渐变横幅 + 分层圆角卡片 + 彩色图标标题 + SVG 趋势图（零依赖，不引 d3）
// 数据源：
//   /api/stats/writing — 写作进度（趋势/连续写作/日均/版本质量/大纲完成度/线进度/每章明细）
//   /api/stats        — T7 代理指标（修改率/提问率/完成率，AI 协作维度）
//   /api/books        — 项目枚举
import { useState, useEffect, useMemo } from 'react'
import Icon from './ui/Icon'
import StatCard from './ui/StatCard'

function fmtWords(n: number | null | undefined): string {
  if (!n) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

// ── SVG 手写折线（零依赖）──
function TrendChart({ data, days, onToggle }: { data: { date: string; words: number }[]; days: number; onToggle: (d: number) => void }) {
  const slice = data.slice(-days)
  const W = 560, H = 130, PAD = 4
  const max = Math.max(1, ...slice.map(d => d.words))
  const pts = slice.map((d, i) => {
    const x = PAD + (i / Math.max(slice.length - 1, 1)) * (W - PAD * 2)
    const y = H - PAD - (d.words / max) * (H - PAD * 2)
    return { x, y, d }
  })
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const area = `${line} L${pts.length ? pts[pts.length - 1].x : PAD},${H - PAD} L${pts.length ? pts[0].x : PAD},${H - PAD} Z`
  const avg = slice.reduce((s, d) => s + d.words, 0) / Math.max(slice.length, 1)
  const avgY = H - PAD - (avg / max) * (H - PAD * 2)
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-zinc-500">按天字数 · 近 {days} 天</span>
        <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
          {[30, 90].map(d => (
            <button key={d} onClick={() => onToggle(d)}
              className={`px-2.5 py-0.5 text-[10px] rounded-md transition-colors ${days === d ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {d} 天
            </button>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 130 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
          </linearGradient>
        </defs>
        {pts.length > 1 && <path d={area} fill="url(#trendFill)" />}
        <line x1={PAD} x2={W - PAD} y1={avgY} y2={avgY} stroke="#52525b" strokeDasharray="3 3" strokeWidth="0.6" />
        {pts.length > 1 && <path d={line} fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeLinejoin="round" />}
        {pts.filter(p => p.d.words > 0).map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="2" fill="#7dd3fc" />
        ))}
        <text x={W - PAD - 2} y={avgY - 3} textAnchor="end" fill="#71717a" fontSize="8">日均 {Math.round(avg)}</text>
      </svg>
    </div>
  )
}

// ── 迷你条形（字数分布 / 大纲完成度通用）──
function MiniBar({ label, value, total, color }: { label: string; value: string; total?: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-500 w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(((total ?? 0) / 100) * 100, 100)}%` }} />
      </div>
      <span className="text-zinc-300 font-medium w-14 text-right shrink-0">{value}</span>
    </div>
  )
}

export default function StatsDashboard() {
  const [writing, setWriting] = useState<Record<string, any> | null>(null)
  const [t7, setT7] = useState<Record<string, any> | null>(null)
  const [books, setBooks] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [trendDays, setTrendDays] = useState(30)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [w, t, b] = await Promise.all([
          fetch('/api/stats/writing').then(r => r.json()).catch(() => null),
          fetch('/api/stats').then(r => r.json()).catch(() => null),
          fetch('/api/books').then(r => r.json()).catch(() => []),
        ])
        if (cancelled) return
        setWriting(w)
        setT7(t)
        setBooks(Array.isArray(b) ? b : [])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const t = useMemo(() => writing?.totals || {}, [writing])
  const dist = writing?.wordDistribution || {}
  const vers = writing?.versionStats || {}
  const oc = writing?.outline || {}
  const lines = writing?.lines || []
  const perChapter = writing?.perChapter || []
  const modify = t7?.modify_rate || {}
  const question = t7?.question_rate || {}
  const completion = t7?.completion_rate || {}
  const byDay = modify.by_day || []
  const maxDayTotal = Math.max(1, ...byDay.map((d: any) => d.total || 0))
  const recent30 = t.recent30Words || 0

  if (loading) {
    return <div className="flex items-center justify-center h-full text-zinc-500 text-sm gap-2">
      <div className="w-5 h-5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
      加载统计...
    </div>
  }

  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      {/* ── 第一层：写作总览横幅（渐变，老版美术）── */}
      <div className="bg-gradient-to-r from-sky-900/30 via-zinc-900/50 to-violet-900/20 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Icon name="book-open" size={16} className="text-sky-400" />
            <span className="text-sm font-semibold text-zinc-200">写作总览</span>
            <span className="text-[10px] text-zinc-500">{books.length} 个项目 · 最近活跃 {new Date().toLocaleDateString()}</span>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="text-zinc-400">
              <span className="text-2xl font-bold text-sky-300">{fmtWords(t.totalWords)}</span>
              <span className="text-zinc-600 ml-1">总字数</span>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-violet-300">{t.currentStreak || 0}<span className="text-sm text-violet-400"> 天</span></div>
              <div className="text-[10px] text-zinc-600">连续写作</div>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-2">
          <span>{t.totalChapters || 0} 章 · 活跃 {t.activeDays || 0} 天</span>
          <span>近30天 {fmtWords(recent30)} 字 · 日均 {fmtWords(t.dailyAvg)} 字</span>
        </div>
        {/* 近30天产出 sparkline（渐变底） */}
        {(writing?.daily || []).length > 0 && (
          <div className="mt-2">
            <TrendChart data={writing.daily} days={Math.min(trendDays, 90)} onToggle={setTrendDays} />
          </div>
        )}
      </div>

      {/* ── 第二层：核心指标卡 ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon="file-text" label="章节数" value={t.totalChapters ?? 0} sub={`${lines.length} 条线`} accent="sky" />
        <StatCard icon="bookmark" label="平均章节" value={fmtWords(t.avgWordsPerChapter)} sub={`最短 ${fmtWords(dist.min)} / 最长 ${fmtWords(dist.max)}`} accent="emerald" />
        <StatCard icon="zap" label="连续写作" value={`${t.currentStreak ?? 0} 天`} sub={`活跃 ${t.activeDays ?? 0} 天`} accent="amber" />
        <StatCard icon="trending-up" label="日均产出" value={fmtWords(t.dailyAvg)} sub={`近7天 ${fmtWords(t.recent7Words)}`} accent="purple" />
        <StatCard icon="check-circle" label="一次通过率" value={vers.onePassRate != null ? `${vers.onePassRate}%` : '-'} sub={`平均改 ${vers.avgRevisions ?? 0} 次`} accent="emerald" />
        <StatCard icon="award" label="大纲完成度" value={oc.percent != null ? `${oc.percent}%` : '-'} sub={oc.planned ? `${oc.written}/${oc.planned} 章` : '暂无大纲'} accent="sky" />
      </div>

      {/* ── 第三层：写作质量 + 大纲 + 分布 ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 章节版本质量 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="pen-tool" size={14} className="text-emerald-400" /> 章节打磨
          </h3>
          <div className="space-y-2.5">
            <Row label="平均修改次数" value={`${vers.avgRevisions ?? 0} 次`} tone={(vers.avgRevisions ?? 0) > 2 ? 'warn' : 'ok'} />
            <Row label="一次通过率" value={`${vers.onePassRate ?? 0}%`} tone={(vers.onePassRate ?? 0) >= 50 ? 'ok' : 'warn'} />
            <Row label="最多修改" value={`${vers.maxRevisions ?? 0} 次`} />
            <Row label="版本快照" value={`${vers.totalVersions ?? 0} 个`} />
          </div>
        </div>
        {/* 大纲完成度 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="clipboard-list" size={14} className="text-sky-400" /> 大纲完成度
          </h3>
          {oc.planned ? (
            <div className="space-y-2.5">
              <Row label="计划章节" value={`${oc.planned} 章`} />
              <Row label="已写章节" value={`${oc.written} 章`} />
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-500">完成比例</span>
                <span className={`font-medium ${(oc.percent ?? 0) >= 80 ? 'text-emerald-400' : (oc.percent ?? 0) >= 40 ? 'text-amber-400' : 'text-zinc-400'}`}>{oc.percent}%</span>
              </div>
              <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${(oc.percent ?? 0) >= 80 ? 'bg-emerald-500' : 'bg-sky-500'}`} style={{ width: `${Math.min(oc.percent ?? 0, 100)}%` }} />
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center py-8 text-zinc-600 text-xs gap-1.5">
              <Icon name="info" size={12} /> 暂无大纲计划（可在计划面板添加章节计划）
            </div>
          )}
        </div>
        {/* 字数分布 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="bar-chart" size={14} className="text-violet-400" /> 章节字数分布
          </h3>
          <div className="space-y-2.5">
            <Row label="最短章节" value={fmtWords(dist.min)} />
            <Row label="最长章节" value={fmtWords(dist.max)} />
            <Row label="中位数" value={fmtWords(dist.median)} />
            <Row label="标准差" value={`±${dist.stdDev ?? 0}`} />
            {dist.count > 0 && <div className="text-[10px] text-zinc-600">基于 {dist.count} 章 · 波动越小越稳定</div>}
          </div>
        </div>
      </div>

      {/* ── 第四层：线进度（narrative_line）── */}
      {lines.length > 1 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="git-branch" size={14} className="text-sky-400" /> 线进度
          </h3>
          <div className="space-y-2">
            {lines.map((ln: any) => (
              <div key={ln.line} className="flex items-center gap-3 text-xs">
                <span className="text-zinc-300 w-24 truncate shrink-0">{ln.line === 'main' ? '主线' : ln.line}</span>
                <span className="text-zinc-500 w-14 shrink-0">{ln.chapterCount} 章</span>
                <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-sky-600/60 rounded" style={{ width: `${Math.min((ln.chapterCount / Math.max(t.totalChapters || 1, 1)) * 100, 100)}%` }} />
                </div>
                <span className="text-zinc-400 w-16 text-right shrink-0">{fmtWords(ln.words)} 字</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 第五层：AI 协作（T7 保留）── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="activity" size={14} className="text-amber-400" /> AI 采纳率
          </h3>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-3xl font-bold text-amber-300">{modify.overall != null ? `${Math.round(modify.overall * 100)}%` : '-'}</span>
            <span className="text-[10px] text-zinc-500">采纳 {modify.accepted ?? 0} / 变更 {modify.changed ?? 0} / 共 {modify.total ?? 0}</span>
          </div>
          {byDay.length > 0 && (
            <div className="flex items-end gap-1 h-16 mt-2">
              {byDay.map((d: any) => (
                <div key={d.bucket} className="flex-1 flex flex-col items-center gap-0.5 min-w-0" title={`${d.bucket}: ${d.total} 次`}>
                  <div className={`w-full rounded-t ${(d.rate || 0) > 0.5 ? 'bg-amber-500/70' : (d.rate || 0) > 0 ? 'bg-sky-500/60' : 'bg-zinc-700'}`}
                    style={{ height: `${Math.max(4, ((d.total || 0) / maxDayTotal) * 40)}px` }} />
                  <span className="text-[8px] text-zinc-600 truncate w-full text-center">{d.bucket.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="message-circle" size={14} className="text-sky-400" /> 提问密度
          </h3>
          <div className="space-y-2.5">
            <Row label="每千字提问" value={question.overall_per_1k_chars != null ? question.overall_per_1k_chars.toFixed(1) : '-'} />
            <Row label="总提问数" value={`${question.total_questions ?? 0}`} />
            <Row label="统计字数" value={fmtWords(question.total_chars)} />
          </div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
            <Icon name="target" size={14} className="text-emerald-400" /> 完成漏斗
          </h3>
          <div className="space-y-2.5">
            <Row label="方向固化" value={`${completion.directions ?? 0} 条`} />
            <Row label="章节产出" value={`${completion.chapters ?? 0} 章`} />
            <div className="text-[10px] text-zinc-600 mt-1">{completion.note}</div>
          </div>
        </div>
      </div>

      {/* ── 第六层：每章明细 ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3">
          <Icon name="list" size={14} className="text-zinc-400" /> 每章明细
          <span className="ml-auto text-[10px] text-zinc-600">{perChapter.length} 章</span>
        </h3>
        {perChapter.length === 0 ? (
          <p className="text-sm text-zinc-600">暂无章节</p>
        ) : (
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-zinc-600 sticky top-0 bg-zinc-900">
                <tr>
                  <th className="text-left py-1.5 pr-2 font-medium">章节</th>
                  <th className="text-right py-1.5 px-2 font-medium w-16">字数</th>
                  <th className="text-right py-1.5 px-2 font-medium w-12">版本</th>
                  <th className="text-left py-1.5 px-2 font-medium w-16">线</th>
                  <th className="text-right py-1.5 pl-2 font-medium w-24">更新时间</th>
                </tr>
              </thead>
              <tbody className="text-zinc-400">
                {[...perChapter].reverse().map((c: any, i: number) => (
                  <tr key={i} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="py-1.5 pr-2 text-zinc-300 truncate max-w-[240px]">{c.title}</td>
                    <td className="text-right py-1.5 px-2 tabular-nums">{fmtWords(c.words)}</td>
                    <td className="text-right py-1.5 px-2 tabular-nums">{c.versions > 0 ? `${c.versions}` : '-'}</td>
                    <td className="py-1.5 px-2"><span className="text-[10px] px-1.5 py-0.5 bg-zinc-800 text-zinc-500 rounded">{c.line === 'main' ? '主线' : c.line}</span></td>
                    <td className="text-right py-1.5 pl-2 tabular-nums text-zinc-600">{(c.updatedAt || '').slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' }) {
  const color = tone === 'ok' ? 'text-emerald-400' : tone === 'warn' ? 'text-amber-400' : 'text-zinc-300'
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-medium ${color}`}>{value}</span>
    </div>
  )
}
