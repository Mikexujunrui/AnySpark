import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon'
import { useResizeObserver } from '../hooks/useResizeObserver'

interface CostSummary {
  total_tokens: number
  total_input_tokens: number
  total_output_tokens: number
  estimated_cost_usd: number
  total_calls: number
  by_tool: Record<string, { tokens: number; cost: number; calls: number }>
  by_model: Record<string, { tokens: number; cost: number; calls: number }>
  by_day: Record<string, { tokens: number; cost: number; calls: number }>
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function formatCost(n: number): string {
  if (n >= 1) return `$${n.toFixed(2)}`
  if (n > 0) return `$${n.toFixed(4)}`
  return '$0'
}

export default function CostDashboard({ bookId }: { bookId: string }) {
  const [cost, setCost] = useState<CostSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const pieRef = useRef<HTMLDivElement>(null)
  const pieSvgRef = useRef<SVGSVGElement>(null)
  const trendRef = useRef<HTMLDivElement>(null)
  const trendSvgRef = useRef<SVGSVGElement>(null)
  const pieDims = useResizeObserver(pieRef)
  const trendDims = useResizeObserver(trendRef)

  useEffect(() => { loadData() }, [bookId])
  useEffect(() => {
    if (cost) {
      renderPieChart()
      renderTrendChart()
    }
  }, [cost, pieDims, trendDims])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/cost`)
      if (res.ok) setCost(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  function renderPieChart() {
    if (!pieSvgRef.current || !cost) return
    const { w, h } = pieDims
    if (w < 150 || h < 150) return

    const entries = Object.entries(cost.by_tool).sort((a, b) => b[1].tokens - a[1].tokens).slice(0, 8)
    if (entries.length === 0) return

    const total = entries.reduce((sum, [, v]) => sum + v.tokens, 0)
    const data = entries.map(([name, v]) => ({ name, value: v.tokens, percent: (v.tokens / total) * 100 }))

    const svg = d3.select(pieSvgRef.current)
    svg.selectAll('*').remove()
    const FW = 200, FH = 160
    svg.attr('viewBox', `0 0 ${FW} ${FH}`).attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%').style('display', 'block')

    const radius = Math.min(FW, FH) / 2 - 10
    const g = svg.append('g').attr('transform', `translate(${FW / 2},${FH / 2})`)

    const color = d3.scaleOrdinal(d3.schemeCategory10)
    const pie = d3.pie<any>().value((d: any) => d.value).sort(null)
    const arc = d3.arc<any>().innerRadius(radius * 0.5).outerRadius(radius)

    const arcs = g.selectAll('.arc').data(pie(data)).enter().append('g').attr('class', 'arc')
    arcs.append('path').attr('d', arc).attr('fill', (_: any, i: number) => color(String(i)))
      .attr('stroke', '#0b1220').attr('stroke-width', 1.5)

    arcs.on('mouseover', function(event: any, d: any) {
      d3.select(this).select('path').attr('opacity', 0.8)
    }).on('mouseout', function() {
      d3.select(this).select('path').attr('opacity', 1)
    })

    // Center label
    g.append('text').attr('text-anchor', 'middle').attr('y', -5)
      .attr('fill', '#e4e4e7').attr('font-size', 14).attr('font-weight', 'bold')
      .text(formatTokens(total))
    g.append('text').attr('text-anchor', 'middle').attr('y', 12)
      .attr('fill', '#71717a').attr('font-size', 10)
      .text('总 Token')
  }

  function renderTrendChart() {
    if (!trendSvgRef.current || !cost) return
    const { w, h } = trendDims
    if (w < 200 || h < 80) return

    const days = Object.entries(cost.by_day).slice(-30)
    if (days.length === 0) return

    const svg = d3.select(trendSvgRef.current)
    svg.selectAll('*').remove()
    const FW = 600, FH = 160
    svg.attr('viewBox', `0 0 ${FW} ${FH}`).attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%').style('display', 'block')

    const margin = { top: 10, right: 20, bottom: 35, left: 40 }
    const innerW = FW - margin.left - margin.right
    const innerH = FH - margin.top - margin.bottom
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const parseDate = d3.timeParse('%Y-%m-%d')
    const points = days.map(([date, v]) => ({ date: parseDate(date) as Date, tokens: v.tokens, cost: v.cost }))

    const x = d3.scaleTime().domain(d3.extent(points, p => p.date) as [Date, Date]).range([0, innerW])
    const maxY = d3.max(points, p => p.tokens) || 1
    const y = d3.scaleLinear().domain([0, maxY * 1.2]).range([innerH, 0])

    const area = (d3.area() as any).x((d: any) => x(d.date)).y0(innerH).y1((d: any) => y(d.tokens)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('d', area).attr('fill', '#f59e0b').attr('opacity', 0.15)
    const line = (d3.line() as any).x((d: any) => x(d.date)).y((d: any) => y(d.tokens)).curve(d3.curveMonotoneX)
    g.append('path').datum(points).attr('fill', 'none').attr('stroke', '#f59e0b').attr('stroke-width', 2).attr('d', line)

    g.append('g').attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(Math.min(points.length, 6)).tickFormat(d3.timeFormat('%m/%d') as any))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 9))

    g.append('g')
      .call(d3.axisLeft(y).ticks(3).tickFormat((d: any) => formatTokens(d)) as any)
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 9))
  }

  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="zap" size={16} className="text-amber-400" />
          <h3 className="text-sm font-semibold text-zinc-200">创作成本分析</h3>
        </div>
        <div className="flex items-center justify-center py-16 text-zinc-600 text-sm">
          <div className="w-5 h-5 border-2 border-zinc-700 border-t-amber-400 rounded-full animate-spin mr-2" /> 加载成本数据...
        </div>
      </div>
    )
  }

  if (!cost || cost.total_calls === 0) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="zap" size={16} className="text-amber-400" />
          <h3 className="text-sm font-semibold text-zinc-200">创作成本分析</h3>
        </div>
        <div className="flex flex-col items-center gap-2 py-12 text-zinc-600">
          <Icon name="zap" size={28} />
          <p className="text-xs">暂无 API 使用记录</p>
        </div>
      </div>
    )
  }

  const topTools = Object.entries(cost.by_tool).sort((a, b) => b[1].tokens - a[1].tokens).slice(0, 5)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
          <Icon name="zap" size={14} className="text-amber-400" /> 创作成本分析
        </h3>
        <span className="text-[10px] text-zinc-600">基于 {cost.total_calls} 次 API 调用</span>
      </div>

      {/* Core metrics */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="bg-zinc-950/40 border border-zinc-800/50 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-zinc-500 mb-1">总 Token</div>
          <div className="text-lg font-bold text-amber-300">{formatTokens(cost.total_tokens)}</div>
        </div>
        <div className="bg-zinc-950/40 border border-zinc-800/50 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-zinc-500 mb-1">预估成本</div>
          <div className="text-lg font-bold text-emerald-300">{formatCost(cost.estimated_cost_usd)}</div>
        </div>
        <div className="bg-zinc-950/40 border border-zinc-800/50 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-zinc-500 mb-1">输入 Token</div>
          <div className="text-sm font-bold text-sky-300">{formatTokens(cost.total_input_tokens)}</div>
        </div>
        <div className="bg-zinc-950/40 border border-zinc-800/50 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-zinc-500 mb-1">输出 Token</div>
          <div className="text-sm font-bold text-violet-300">{formatTokens(cost.total_output_tokens)}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pie chart */}
        <div>
          <div className="text-[10px] text-zinc-500 mb-2">工具消耗分布</div>
          <div ref={pieRef} className="relative" style={{ height: 160 }}>
            <svg ref={pieSvgRef} className="w-full h-full" />
          </div>
        </div>

        {/* Trend chart */}
        <div>
          <div className="text-[10px] text-zinc-500 mb-2">日 Token 趋势 (近30天)</div>
          <div ref={trendRef} className="relative" style={{ height: 160 }}>
            <svg ref={trendSvgRef} className="w-full h-full" />
          </div>
        </div>
      </div>

      {/* Top tools */}
      <div className="mt-4">
        <div className="text-[10px] text-zinc-500 mb-2">工具消耗 Top 5</div>
        <div className="space-y-1.5">
          {topTools.map(([name, v]) => {
            const maxTokens = Math.max(...topTools.map(([, t]) => t.tokens))
            return (
              <div key={name} className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-400 w-32 truncate">{name}</span>
                <div className="flex-1 h-4 bg-zinc-800 rounded overflow-hidden">
                  <div className="h-full bg-amber-600/60 rounded" style={{ width: `${(v.tokens / maxTokens) * 100}%` }} />
                </div>
                <span className="text-[10px] text-zinc-500 w-20 text-right">{formatTokens(v.tokens)}</span>
                <span className="text-[10px] text-emerald-500 w-16 text-right">{formatCost(v.cost)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
