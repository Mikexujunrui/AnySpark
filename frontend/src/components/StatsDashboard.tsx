import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { api } from "../api"
import { useResizeObserver } from "../hooks/useResizeObserver"
import Icon from './ui/Icon'
import StatCard from './ui/StatCard'
import { showToast } from './ui/toast-utils'
import PacingCurve from './PacingCurve'
import CostDashboard from './CostDashboard'

function formatWords(n: number | null | undefined): string {
  if (n == null) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

function formatDate(d: string | undefined): string {
  if (!d) return '-'
  const [, m, day] = d.split('-')
  return `${parseInt(m)}/${parseInt(day)}`
}

export default function StatsDashboard() {
  const [stats, setStats] = useState<Record<string, any> | null>(null)
  const [agentMetrics, setAgentMetrics] = useState<Record<string, any> | null>(null)
  const [loading, setLoading] = useState(true)
  const [last30, setLast30] = useState(true)
  const [bookIdFilter, setBookIdFilter] = useState<string | null>(null)
  const [books, setBooks] = useState<Record<string, any>[]>([])

  const lineContainerRef = useRef<HTMLDivElement>(null)
  const lineSvgRef = useRef<SVGSVGElement>(null)
  const barContainerRef = useRef<HTMLDivElement>(null)
  const barSvgRef = useRef<SVGSVGElement>(null)
  const agentTrendRef = useRef<HTMLDivElement>(null)
  const agentTrendSvgRef = useRef<SVGSVGElement>(null)
  const lineDims = useResizeObserver(lineContainerRef)
  const barDims = useResizeObserver(barContainerRef)
  const agentTrendDims = useResizeObserver(agentTrendRef)

  useEffect(() => { loadBooks() }, [])
  useEffect(() => {
    if (bookIdFilter) {
      loadStats(bookIdFilter)
      loadAgentMetrics(bookIdFilter)
    }
  }, [bookIdFilter])

  useEffect(() => {
    if (!stats) return
    renderLineChart()
    renderBarChart()
  }, [stats, last30, lineDims, barDims])

  useEffect(() => {
    if (!agentMetrics?.trend?.length) return
    renderAgentTrend()
  }, [agentMetrics, agentTrendDims])

  async function loadBooks() {
    try {
      const bks = await api.getBooks()
      setBooks(Array.isArray(bks) ? bks as Record<string, any>[] : [])
      if (Array.isArray(bks) && bks.length > 0 && !bookIdFilter) {
        setBookIdFilter((bks as any[])[0].id)
      }
    } catch {
      showToast('加载书架失败', 'error')
    }
  }

  async function loadStats(bookId: string) {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/stats`)
      if (!res.ok) throw new Error('stats fetch failed')
      setStats(await res.json())
    } catch {
      showToast('加载统计失败', 'error')
      setStats(null)
    }
    setLoading(false)
  }

  async function loadAgentMetrics(bookId: string) {
    try {
      const res = await fetch(`/api/books/${bookId}/agent-metrics`)
      if (res.ok) setAgentMetrics(await res.json())
      else setAgentMetrics(null)
    } catch {
      setAgentMetrics(null)
    }
  }

  // ── 字数趋势折线图 ──
  function renderLineChart() {
    if (!lineSvgRef.current || !stats) return
    const container = lineContainerRef.current
    if (!container) return
    const { w, h } = lineDims
    if (w < 200 || h < 100) return

    const data = (stats.daily || []).slice(last30 ? -30 : -90)
    const svg = d3.select(lineSvgRef.current)
    svg.selectAll('*').remove()
    const FW = 600, FH = 260
    svg.attr('viewBox', `0 0 ${FW} ${FH}`).attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%').style('display', 'block')

    if (data.length === 0) {
      svg.append('text').attr('x', FW / 2).attr('y', FH / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无写作数据')
      return
    }

    const margin = { top: 20, right: 20, bottom: 50, left: 55 }
    const innerW = FW - margin.left - margin.right
    const innerH = FH - margin.top - margin.bottom
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const parseDate = d3.timeParse('%Y-%m-%d')
    const points = data.map((d: any) => ({
      date: parseDate(d.date) as Date,
      words: (d.wordsCreated || 0) + (d.wordsEdited || 0),
      created: d.wordsCreated || 0,
      edited: d.wordsEdited || 0,
      rawDate: d.date,
    }))

    const x = d3.scaleTime().domain(d3.extent(points, (p: any) => p.date) as [Date, Date]).range([0, innerW])
    const maxY = d3.max(points, (p: any) => p.words) || 1
    const y = d3.scaleLinear().domain([0, maxY * 1.1]).range([innerH, 0])

    g.selectAll('.grid-h').data(y.ticks(4)).enter().append('line')
      .attr('x1', 0).attr('x2', innerW)
      .attr('y1', (d: any) => y(d)).attr('y2', (d: any) => y(d))
      .attr('stroke', '#27272a').attr('stroke-dasharray', '2,3')

    const defs = svg.append('defs')
    const grad = defs.append('linearGradient').attr('id', 'areaGrad').attr('x1', '0').attr('x2', '0').attr('y1', '0').attr('y2', '1')
    grad.append('stop').attr('offset', '0%').attr('stop-color', '#0ea5e9').attr('stop-opacity', 0.4)
    grad.append('stop').attr('offset', '100%').attr('stop-color', '#0ea5e9').attr('stop-opacity', 0.02)

    const area = (d3.area() as any).x((d: any) => x(d.date)).y0(innerH).y1((d: any) => y(d.words)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('d', area).attr('fill', 'url(#areaGrad)')

    const line = (d3.line() as any).x((d: any) => x(d.date)).y((d: any) => y(d.words)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('fill', 'none').attr('stroke', '#0ea5e9').attr('stroke-width', 2).attr('d', line)

    const activePoints = points.filter((p: any) => p.words > 0)
    g.selectAll('.dot').data(activePoints).enter().append('circle')
      .attr('cx', (d: any) => x(d.date)).attr('cy', (d: any) => y(d.words))
      .attr('r', 3).attr('fill', '#0ea5e9').attr('stroke', '#0b1220').attr('stroke-width', 1.5)

    const tickCount = Math.min(points.length, 7)
    g.append('g').attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(tickCount).tickFormat(d3.timeFormat('%m/%d') as any))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))
      .call((g: any) => g.selectAll('line').attr('stroke', '#3f3f46'))

    g.append('g')
      .call(d3.axisLeft(y).ticks(4).tickFormat((d: any) => d >= 1000 ? `${(d/1000).toFixed(0)}k` : d) as any)
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))
      .call((g: any) => g.selectAll('line').attr('stroke', '#3f3f46'))

    const tooltip = d3.select(container).selectAll('.stats-tip').data([0]).join('div')
      .attr('class', 'stats-tip')
      .style('position', 'absolute').style('background', '#18181b')
      .style('border', '1px solid #3f3f46').style('border-radius', '8px')
      .style('padding', '8px 10px').style('font-size', '11px')
      .style('color', '#d4d4d8').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 30)

    const bisect = d3.bisector((d: any) => d.date).left
    const focus = g.append('g').style('display', 'none')
    focus.append('circle').attr('r', 5).attr('fill', '#0ea5e9').attr('stroke', '#fff').attr('stroke-width', 2)
    focus.append('line').attr('class', 'focus-v').attr('y1', 0).attr('y2', innerH)
      .attr('stroke', '#38bdf8').attr('stroke-width', 1).attr('stroke-dasharray', '3,3')

    svg.on('mousemove', (event: any) => {
      const [mx] = d3.pointer(event)
      const x0 = x.invert(mx - margin.left)
      const i = bisect(points, x0)
      const d0: any = points[i - 1]
      const d1: any = points[i]
      const d = !d1 ? d0 : !d0 ? d1 : (x0.getTime() - d0.date.getTime() > d1.date.getTime() - x0.getTime() ? d1 : d0)
      if (!d) return
      focus.style('display', null).attr('transform', `translate(${x(d.date)},${y(d.words)})`)
      focus.select('.focus-v').attr('y2', innerH - y(d.words))
      tooltip.style('opacity', 1)
        .style('left', `${event.offsetX + 12}px`)
        .style('top', `${event.offsetY - 8}px`)
        .html(`<div style="font-weight:600;color:#e4e4e7;margin-bottom:3px">${formatDate(d.rawDate)}</div>`
            + `<div>写字: <span style="color:#38bdf8">${d.created}</span></div>`
            + `<div>编辑: <span style="color:#34d399">${d.edited}</span></div>`
            + `<div style="border-top:1px solid #3f3f46;margin-top:4px;padding-top:4px">合计: <b>${d.words}</b></div>`)
    }).on('mouseleave', () => {
      focus.style('display', 'none')
      tooltip.style('opacity', 0)
    })
  }

  // ── 章节长度分布柱状图 ──
  function renderBarChart() {
    if (!barSvgRef.current || !stats) return
    const { w, h } = barDims
    if (w < 200 || h < 100) return

    const data = stats.perChapter || []
    const svg = d3.select(barSvgRef.current)
    svg.selectAll('*').remove()
    const FW = 600, FH = 260
    svg.attr('viewBox', `0 0 ${FW} ${FH}`).attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%').style('display', 'block')

    if (data.length === 0) {
      svg.append('text').attr('x', FW / 2).attr('y', FH / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无章节数据')
      return
    }

    const margin = { top: 20, right: 20, bottom: 60, left: 55 }
    const innerW = FW - margin.left - margin.right
    const innerH = FH - margin.top - margin.bottom
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const x = d3.scaleBand().domain(data.map((d: any) => String(d.idx))).range([0, innerW]).padding(0.2)
    const maxY = d3.max(data, (d: any) => d.wordCount) || 1
    const y = d3.scaleLinear().domain([0, maxY * 1.1]).range([innerH, 0])

    g.selectAll('.grid').data(y.ticks(4)).enter().append('line')
      .attr('x1', 0).attr('x2', innerW)
      .attr('y1', (d: any) => y(d)).attr('y2', (d: any) => y(d))
      .attr('stroke', '#27272a').attr('stroke-dasharray', '2,3')

    const barGroups = g.selectAll('.bar').data(data).enter().append('g').attr('class', 'bar')
    barGroups.append('rect')
      .attr('x', (d: any) => x(String(d.idx)) as any)
      .attr('y', (d: any) => y(d.wordCount))
      .attr('width', x.bandwidth())
      .attr('height', (d: any) => Math.max(0, innerH - y(d.wordCount)))
      .attr('fill', (d: any) => d.isExtra ? '#a78bfa' : '#0ea5e9')
      .attr('opacity', 0.85).attr('rx', 2)

    const tooltip = d3.select(barContainerRef.current!).selectAll('.bar-tip').data([0]).join('div')
      .attr('class', 'bar-tip')
      .style('position', 'absolute').style('background', '#18181b')
      .style('border', '1px solid #3f3f46').style('border-radius', '8px')
      .style('padding', '8px 10px').style('font-size', '11px')
      .style('color', '#d4d4d8').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 30)

    barGroups.on('mouseover', function(event: any, d: any) {
      d3.select(this).select('rect').attr('opacity', 1).attr('stroke', '#fff').attr('stroke-width', 1)
      tooltip.style('opacity', 1)
        .html(`<div style="font-weight:600;color:#e4e4e7">${d.isExtra ? '番外' : '第' + d.idx + '章'}: ${d.title}</div>`
            + `<div style="margin-top:3px"><span style="color:#38bdf8">${formatWords(d.wordCount)}</span> 字</div>`)
        .style('left', `${event.offsetX + 12}px`)
        .style('top', `${event.offsetY - 10}px`)
    }).on('mouseout', function() {
      d3.select(this).select('rect').attr('opacity', 0.85).attr('stroke', 'none')
      tooltip.style('opacity', 0)
    })

    const showEvery = Math.max(1, Math.ceil(data.length / 15))
    g.append('g').attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).tickValues(data.map((d: any) => String(d.idx)).filter((_: any, i: number) => i % showEvery === 0)))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10).attr('transform', 'rotate(-30)').attr('text-anchor', 'end'))
      .call((g: any) => g.selectAll('line').attr('stroke', '#3f3f46'))

    g.append('g')
      .call(d3.axisLeft(y).ticks(4).tickFormat((d: any) => d >= 1000 ? `${(d/1000).toFixed(0)}k` : d) as any)
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))
      .call((g: any) => g.selectAll('line').attr('stroke', '#3f3f46'))
  }

  // ── Agent 效能趋势图 ──
  function renderAgentTrend() {
    if (!agentTrendSvgRef.current || !agentMetrics?.trend) return
    const container = agentTrendRef.current
    if (!container) return
    const { w, h } = agentTrendDims
    if (w < 200 || h < 80) return

    const data = agentMetrics.trend
    const svg = d3.select(agentTrendSvgRef.current)
    svg.selectAll('*').remove()
    const FW = 600, FH = 120
    svg.attr('viewBox', `0 0 ${FW} ${FH}`).attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%').style('display', 'block')

    const margin = { top: 15, right: 20, bottom: 35, left: 40 }
    const innerW = FW - margin.left - margin.right
    const innerH = FH - margin.top - margin.bottom
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const parseDate = d3.timeParse('%Y-%m-%d')
    const points = data.map((d: any) => ({ date: parseDate(d.date) as Date, avgRounds: d.avgRounds, avgTokens: d.avgTokens, runs: d.runs }))

    const x = d3.scaleTime().domain(d3.extent(points, (p: any) => p.date) as [Date, Date]).range([0, innerW])
    const maxY = d3.max(points, (p: any) => p.avgRounds) || 10
    const y = d3.scaleLinear().domain([0, maxY * 1.2]).range([innerH, 0])

    g.selectAll('.grid-h').data(y.ticks(3)).enter().append('line')
      .attr('x1', 0).attr('x2', innerW)
      .attr('y1', (d: any) => y(d)).attr('y2', (d: any) => y(d))
      .attr('stroke', '#27272a').attr('stroke-dasharray', '2,3')

    const line = (d3.line() as any).x((d: any) => x(d.date)).y((d: any) => y(d.avgRounds)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('fill', 'none').attr('stroke', '#a78bfa').attr('stroke-width', 2).attr('d', line)

    g.selectAll('.dot').data(points).enter().append('circle')
      .attr('cx', (d: any) => x(d.date)).attr('cy', (d: any) => y(d.avgRounds))
      .attr('r', 3).attr('fill', '#a78bfa').attr('stroke', '#0b1220').attr('stroke-width', 1)

    g.append('g').attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(Math.min(points.length, 6)).tickFormat(d3.timeFormat('%m/%d') as any))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))
      .call((g: any) => g.selectAll('line').attr('stroke', '#3f3f46'))

    g.append('g')
      .call(d3.axisLeft(y).ticks(3).tickFormat((d: any) => `${d}`) as any)
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))
  }

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10">
        <header className="mb-6"><h1 className="text-3xl font-bold flex items-center gap-3"><Icon name="bar-chart" size={28} /> 写作统计</h1></header>
        <div className="flex items-center justify-center py-24 text-zinc-500">
          <div className="w-6 h-6 border-2 border-zinc-700 border-t-sky-400 rounded-full animate-spin mr-3" /> 加载中...
        </div>
      </div>
    )
  }

  const totals = stats?.totals || {}
  const wd = stats?.wordDistribution || {}
  const rev = stats?.revisionStats || {}
  const oc = stats?.outlineCompletion || {}
  const vp = stats?.volumeProgress || []
  const rs = stats?.reviewStats || {}
  const am = agentMetrics || {}
  const completionPercent = totals.completionPercent || 0
  const hasAgentData = am.totalRuns > 0

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3"><Icon name="bar-chart" size={28} /> 写作统计</h1>
          <p className="text-zinc-500 mt-1 text-sm">追踪写作进度、字数趋势、章节质量与 Agent 效能</p>
        </div>
        {books.length > 1 && (
          <select value={bookIdFilter || ''} onChange={e => setBookIdFilter(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500">
            {books.map(b => <option key={b.id} value={b.id}>{b.title}</option>)}
          </select>
        )}
      </header>

      {/* ── 第一层：完成进度横幅 ── */}
      <div className="bg-gradient-to-r from-sky-900/30 via-zinc-900/50 to-violet-900/20 border border-zinc-800 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Icon name="target" size={18} className="text-sky-400" />
            <span className="text-sm font-semibold text-zinc-200">完成进度</span>
            <span className="text-[10px] text-zinc-500">目标 {formatWords(totals.targetWords)} 字</span>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="text-zinc-400">
              <span className="text-2xl font-bold text-sky-300">{formatWords(totals.totalWords)}</span>
              <span className="text-zinc-600 ml-1">/ {formatWords(totals.targetWords)}</span>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-violet-300">{completionPercent}%</div>
              <div className="text-[10px] text-zinc-600">已完成</div>
            </div>
          </div>
        </div>
        <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-sky-500 to-violet-500 rounded-full transition-all duration-500"
            style={{ width: `${Math.min(completionPercent, 100)}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-2 text-[10px] text-zinc-500">
          <span>剩余 {formatWords(Math.max(0, (totals.targetWords || 0) - (totals.totalWords || 0)))} 字</span>
          <span>
            {totals.estimatedDaysToComplete != null
              ? `按日均 ${formatWords(totals.dailyAvg)} 字预计还需 ${totals.estimatedDaysToComplete} 天`
              : '暂无日均数据，无法预估'}
          </span>
        </div>
      </div>

      {/* ── 第二层：核心指标卡片 ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard icon="file-text" label="总字数" value={formatWords(totals.totalWords)} sub={`${totals.totalChapters || 0} 章 + ${totals.extrasCount || 0} 番外`} accent="sky" />
        <StatCard icon="bookmark" label="平均章节" value={formatWords(totals.avgWordsPerChapter)} sub={`最短 ${formatWords(wd.min)} / 最长 ${formatWords(wd.max)}`} accent="emerald" />
        <StatCard icon="zap" label="连续写作" value={`${totals.currentStreak || 0} 天`} sub={`最长 ${totals.bestStreak || 0} 天 / 活跃 ${totals.activeWritingDays || 0} 天`} accent="amber" />
        <StatCard icon="trending-up" label="日均产出" value={formatWords(totals.dailyAvg)} sub={`近7天 ${formatWords(totals.recent7DaysWords)} / 近30天 ${formatWords(totals.recent30DaysWords)}`} accent="purple" />
      </div>

      {/* ── 第三层：趋势图表 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* 字数趋势 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2"><Icon name="activity" size={14} /> 字数趋势</h3>
            <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
              <button onClick={() => setLast30(true)} className={`px-3 py-1 text-xs rounded-md transition-colors ${last30 ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>近 30 天</button>
              <button onClick={() => setLast30(false)} className={`px-3 py-1 text-xs rounded-md transition-colors ${!last30 ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>近 90 天</button>
            </div>
          </div>
          <div ref={lineContainerRef} className="relative" style={{ height: 260 }}><svg ref={lineSvgRef} className="w-full h-full" /></div>
        </div>
        {/* 章节分布 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2"><Icon name="bar-chart" size={14} /> 章节长度分布</h3>
            <div className="flex items-center gap-3 text-[10px] text-zinc-500">
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded bg-sky-500" /> 正文</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded bg-purple-400" /> 番外</span>
            </div>
          </div>
          <div ref={barContainerRef} className="relative" style={{ height: 260 }}><svg ref={barSvgRef} className="w-full h-full" /></div>
        </div>
      </div>

      {/* ── 第四层：质量与效率面板 ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* 章节质量 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3"><Icon name="pen-tool" size={14} className="text-emerald-400" /> 章节质量</h3>
          <div className="space-y-2.5">
            <QualityRow label="平均修改次数" value={rev.avgRevisions ?? 0} unit="次" warn={(rev.avgRevisions ?? 0) > 2} />
            <QualityRow label="一次性通过率" value={rev.onePassRate ?? 0} unit="%" good={(rev.onePassRate ?? 0) >= 50} />
            <QualityRow label="最大修改次数" value={rev.maxRevisions ?? 0} unit="次" />
            <QualityRow label="总修改版本" value={rev.totalRevisions ?? 0} unit="个" />
          </div>
        </div>
        {/* 大纲完成度 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3"><Icon name="clipboard-list" size={14} className="text-sky-400" /> 大纲完成度</h3>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">计划章节</span>
              <span className="text-zinc-300 font-medium">{oc.planned ?? 0} 章</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">已写章节</span>
              <span className="text-zinc-300 font-medium">{oc.written ?? 0} 章</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">完成比例</span>
              <span className={`font-medium ${(oc.percent ?? 0) >= 80 ? 'text-emerald-400' : (oc.percent ?? 0) >= 40 ? 'text-amber-400' : 'text-zinc-400'}`}>{oc.percent ?? 0}%</span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden mt-2">
              <div className={`h-full rounded-full transition-all ${oc.percent >= 80 ? 'bg-emerald-500' : 'bg-sky-500'}`} style={{ width: `${Math.min(oc.percent ?? 0, 100)}%` }} />
            </div>
          </div>
        </div>
        {/* 评审统计 */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3"><Icon name="award" size={14} className="text-amber-400" /> 评审统计</h3>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">评审次数</span>
              <span className="text-zinc-300 font-medium">{rs.totalReviews ?? 0} 次</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">平均评分</span>
              <span className={`font-medium ${(rs.avgScore ?? 0) >= 7 ? 'text-emerald-400' : (rs.avgScore ?? 0) >= 5 ? 'text-amber-400' : 'text-zinc-400'}`}>
                {rs.avgScore ? rs.avgScore.toFixed(1) : '—'} / 10
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">通过率 (≥7分)</span>
              <span className={`font-medium ${(rs.passRate ?? 0) >= 60 ? 'text-emerald-400' : 'text-amber-400'}`}>{rs.passRate ?? 0}%</span>
            </div>
            {rs.scoreTrend?.length > 0 && (
              <div className="flex items-end gap-1 h-8 mt-2">
                {rs.scoreTrend.slice(-12).map((s: any, i: number) => (
                  <div key={i} className="flex-1 bg-amber-600/60 rounded-sm" style={{ height: `${(s.score / 10) * 100}%` }} title={`${formatDate(s.date)}: ${s.score}`} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 第五层：Agent 效能面板 ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2"><Icon name="bot" size={16} className="text-violet-400" /> Agent 效能</h3>
          <span className="text-[10px] text-zinc-600">基于 {am.totalRuns ?? 0} 次运行记录</span>
        </div>

        {hasAgentData ? (
          <>
            {/* Agent 核心指标 */}
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
              <AgentMetric label="总运行" value={am.totalRuns ?? 0} unit="次" icon="activity" />
              <AgentMetric label="平均轮次" value={am.avgRounds ?? 0} unit="轮" icon="refresh" />
              <AgentMetric label="平均LLM" value={am.avgLlmCalls ?? 0} unit="次" icon="brain" />
              <AgentMetric label="平均Token" value={formatWords(am.avgTokens ?? 0)} unit="" icon="zap" />
              <AgentMetric label="成功率" value={am.successRate ?? 0} unit="%" icon="check-circle" good={(am.successRate ?? 0) >= 80} />
              <AgentMetric label="幻觉率" value={am.hallucinationRate ?? 0} unit="%" icon="alert-circle" warn={(am.hallucinationRate ?? 0) > 10} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Agent 趋势图 */}
              <div>
                <div className="text-[10px] text-zinc-500 mb-2">平均轮次趋势 (近30天)</div>
                <div ref={agentTrendRef} className="relative" style={{ height: 120 }}>
                  <svg ref={agentTrendSvgRef} className="w-full h-full" />
                </div>
              </div>

              {/* 工具使用 Top10 */}
              <div>
                <div className="text-[10px] text-zinc-500 mb-2">工具调用频率 Top 10</div>
                {am.topTools && Object.keys(am.topTools).length > 0 ? (
                  <div className="space-y-1.5">
                    {Object.entries(am.topTools).map(([name, count]: [string, any]) => {
                      const maxCount = Math.max(...Object.values(am.topTools as Record<string, number>))
                      return (
                        <div key={name} className="flex items-center gap-2">
                          <span className="text-[10px] text-zinc-400 w-32 truncate">{name}</span>
                          <div className="flex-1 h-4 bg-zinc-800 rounded overflow-hidden">
                            <div className="h-full bg-violet-600/60 rounded" style={{ width: `${(count / maxCount) * 100}%` }} />
                          </div>
                          <span className="text-[10px] text-zinc-500 w-8 text-right">{count}</span>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="text-[10px] text-zinc-600 flex items-center gap-1">
                    <Icon name="check" size={10} className="text-emerald-600" /> 暂无工具调用记录
                  </div>
                )}
              </div>
            </div>

            {/* 高消耗 outlier */}
            {am.outliers?.length > 0 && (
              <div className="mt-4">
                <div className="text-[10px] text-zinc-500 mb-2 flex items-center gap-1">
                  <Icon name="alert-triangle" size={12} className="text-amber-500" /> 高消耗任务 (≥20轮)
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {am.outliers.slice(0, 5).map((o: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 text-[10px] bg-zinc-950/50 rounded px-2 py-1">
                      <span className="text-zinc-600">{formatDate(o.timestamp)}</span>
                      <span className="text-violet-400 w-16 truncate">{o.agentType}</span>
                      <span className="text-amber-400">{o.rounds}轮</span>
                      <span className="text-zinc-500">{o.llmCalls} LLM</span>
                      <span className="text-zinc-600 truncate flex-1">{o.message}</span>
                      <span className="text-zinc-700">{o.finishReason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* finish_reason 分布 */}
            {am.finishReasons && Object.keys(am.finishReasons).length > 0 && (
              <div className="mt-3 flex items-center gap-3 flex-wrap">
                <span className="text-[10px] text-zinc-500">结束原因:</span>
                {Object.entries(am.finishReasons).map(([reason, count]: [string, any]) => (
                  <span key={reason} className="text-[10px] px-2 py-0.5 bg-zinc-800 text-zinc-400 rounded">
                    {reason} ×{count}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center py-12 text-zinc-600 text-sm">
            <Icon name="check-circle" size={14} className="text-emerald-600 mr-2" />
            暂无 Agent 运行记录
          </div>
        )}
      </div>

      {/* ── 第六层：分卷进度 ── */}
      {vp.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2 mb-3"><Icon name="layers" size={14} className="text-sky-400" /> 分卷进度</h3>
          <div className="space-y-2">
            {vp.map((vol: any) => (
              <div key={vol.id} className="flex items-center gap-3 text-xs">
                <span className="text-zinc-300 w-48 truncate">{vol.title}</span>
                <span className="text-zinc-500">{vol.chapterCount} 章</span>
                <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div className="h-full bg-sky-600/60 rounded" style={{ width: `${Math.min((vol.chapterCount / Math.max(totals.totalChapters || 1, 1)) * 100, 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 第七层：叙事节奏 + 成本分析 ── */}
      {bookIdFilter && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          <PacingCurve bookId={bookIdFilter} />
          <CostDashboard bookId={bookIdFilter} />
        </div>
      )}
    </div>
  )
}

// ── 内联子组件 ──

function QualityRow({ label, value, unit, good, warn }: { label: string; value: number; unit: string; good?: boolean; warn?: boolean }) {
  const colorClass = good ? 'text-emerald-400' : warn ? 'text-amber-400' : 'text-zinc-300'
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-medium ${colorClass}`}>{value}{unit}</span>
    </div>
  )
}

function AgentMetric({ label, value, unit, icon, good, warn }: { label: string; value: any; unit: string; icon: string; good?: boolean; warn?: boolean }) {
  const valueClass = good ? 'text-emerald-300' : warn ? 'text-amber-300' : 'text-zinc-200'
  return (
    <div className="bg-zinc-950/40 border border-zinc-800/50 rounded-lg p-2.5 text-center">
      <div className="flex items-center justify-center gap-1 mb-1">
        <Icon name={icon} size={12} className="text-zinc-600" />
        <span className="text-[9px] text-zinc-500">{label}</span>
      </div>
      <div className={`text-lg font-bold ${valueClass}`}>{value}{unit}</div>
    </div>
  )
}
