import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { api } from "../api"
import { useResizeObserver } from "../hooks/useResizeObserver"
import Icon from './ui/Icon'
import StatCard from './ui/StatCard'
import { showToast } from './ui/Toast'

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
  const [loading, setLoading] = useState(true)
  const [last30, setLast30] = useState(true)
  const [bookIdFilter, setBookIdFilter] = useState<string | null>(null)
  const [books, setBooks] = useState<Record<string, any>[]>([])

  const lineContainerRef = useRef<HTMLDivElement>(null)
  const lineSvgRef = useRef<SVGSVGElement>(null)
  const barContainerRef = useRef<HTMLDivElement>(null)
  const barSvgRef = useRef<SVGSVGElement>(null)
  const lineDims = useResizeObserver(lineContainerRef)
  const barDims = useResizeObserver(barContainerRef)

  useEffect(() => { loadBooks() }, [])
  useEffect(() => { if (bookIdFilter) loadStats(bookIdFilter) }, [bookIdFilter])

  useEffect(() => {
    if (!stats) return
    renderLineChart()
    renderBarChart()
  }, [stats, last30, lineDims, barDims])

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
      const data = await res.json()
      setStats(data)
    } catch {
      showToast('加载统计失败', 'error')
      setStats(null)
    }
    setLoading(false)
  }

  function renderLineChart() {
    if (!lineSvgRef.current || !stats) return
    const container = lineContainerRef.current
    if (!container) return
    const { w, h } = lineDims
    if (w < 200 || h < 100) return

    const data = (stats.daily || []).slice(last30 ? -30 : -90)
    const svg = d3.select(lineSvgRef.current)
    svg.selectAll('*').remove()
    svg.attr('width', w).attr('height', h)

    if (data.length === 0) {
      svg.append('text').attr('x', w / 2).attr('y', h / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无写作数据')
      return
    }

    const margin = { top: 20, right: 20, bottom: 40, left: 55 }
    const innerW = w - margin.left - margin.right
    const innerH = h - margin.top - margin.bottom
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

    const area = (d3.area() as any).x((d: any) => x(d.date)).y0(innerH).y1((d: any) => y(d.words)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('d', area).attr('fill', 'url(#areaGrad)')

    const defs = svg.append('defs')
    const grad = defs.append('linearGradient').attr('id', 'areaGrad').attr('x1', '0').attr('x2', '0').attr('y1', '0').attr('y2', '1')
    grad.append('stop').attr('offset', '0%').attr('stop-color', '#0ea5e9').attr('stop-opacity', 0.4)
    grad.append('stop').attr('offset', '100%').attr('stop-color', '#0ea5e9').attr('stop-opacity', 0.02)

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
      .style('box-shadow', '0 4px 12px rgb(0 0 0 / 0.4)')

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
        .style('left', `${x(d.date) + margin.left + 12}px`)
        .style('top', `${y(d.words) + margin.top - 8}px`)
        .html(`<div style="font-weight:600;color:#e4e4e7;margin-bottom:3px">${formatDate(d.rawDate)}</div>`
            + `<div>写字: <span style="color:#38bdf8">${d.created}</span></div>`
            + `<div>编辑: <span style="color:#34d399">${d.edited}</span></div>`
            + `<div style="border-top:1px solid #3f3f46;margin-top:4px;padding-top:4px">合计: <b>${d.words}</b></div>`)
    }).on('mouseleave', () => {
      focus.style('display', 'none')
      tooltip.style('opacity', 0)
    })
  }

  function renderBarChart() {
    if (!barSvgRef.current || !stats) return
    const { w, h } = barDims
    if (w < 200 || h < 100) return

    const data = stats.perChapter || []
    const svg = d3.select(barSvgRef.current)
    svg.selectAll('*').remove()
    svg.attr('width', w).attr('height', h)

    if (data.length === 0) {
      svg.append('text').attr('x', w / 2).attr('y', h / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无章节数据')
      return
    }

    const margin = { top: 20, right: 20, bottom: 50, left: 55 }
    const innerW = w - margin.left - margin.right
    const innerH = h - margin.top - margin.bottom
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
        .style('left', `${x(String(d.idx))! + margin.left}px`)
        .style('top', `${y(d.wordCount) + margin.top - 10}px`)
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
  const currentBook = books.find(b => b.id === bookIdFilter)

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div><h1 className="text-3xl font-bold flex items-center gap-3"><Icon name="bar-chart" size={28} /> 写作统计</h1><p className="text-zinc-500 mt-1 text-sm">追踪写作进度、字数趋势与章节分布</p></div>
        {books.length > 1 && (
          <select value={bookIdFilter || ''} onChange={e => setBookIdFilter(e.target.value)} className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500">
            {books.map(b => <option key={b.id} value={b.id}>{b.title}</option>)}
          </select>
        )}
      </header>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard icon="file-text" label="总字数" value={formatWords(totals.totalWords)} sub={`${totals.totalChapters || 0} 章 + ${totals.extrasCount || 0} 番外`} accent="sky" />
        <StatCard icon="bookmark" label="平均章节" value={formatWords(totals.avgWordsPerChapter)} sub="每章平均字数" accent="emerald" />
        <StatCard icon="zap" label="连续写作" value={`${totals.currentStreak || 0} 天`} sub={`最长 ${totals.bestStreak || 0} 天`} accent="amber" />
        <StatCard icon="calendar" label="最后活跃" value={totals.lastActiveDate ? formatDate(totals.lastActiveDate) : '—'} sub={totals.lastActiveDate ? '最近写作日期' : '尚未开始'} accent="purple" />
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2"><Icon name="activity" size={14} /> 字数趋势</h3>
          <div className="flex gap-1 bg-zinc-800 rounded-lg p-0.5">
            <button onClick={() => setLast30(true)} className={`px-3 py-1 text-xs rounded-md transition-colors ${last30 ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>近 30 天</button>
            <button onClick={() => setLast30(false)} className={`px-3 py-1 text-xs rounded-md transition-colors ${!last30 ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>近 90 天</button>
          </div>
        </div>
        <div ref={lineContainerRef} className="relative" style={{ height: 280 }}><svg ref={lineSvgRef} className="w-full h-full" /></div>
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2"><Icon name="bar-chart" size={14} /> 章节长度分布</h3>
          <div className="flex items-center gap-3 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded bg-sky-500" /> 正文</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded bg-purple-400" /> 番外</span>
          </div>
        </div>
        <div ref={barContainerRef} className="relative" style={{ height: 300 }}><svg ref={barSvgRef} className="w-full h-full" /></div>
      </div>
    </div>
  )
}
