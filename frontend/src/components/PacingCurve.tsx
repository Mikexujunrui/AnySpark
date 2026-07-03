import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon'
import { useResizeObserver } from '../hooks/useResizeObserver'

interface ChapterPacing {
  chapter_id: string
  title: string
  chapter_index: number
  word_count: number
  dialogue_ratio: number
  sentence_length_variance: number
  scene_transition_count: number
  emotional_volatility: number
  pacing_score: number
}

const METRIC_CONFIG = [
  { key: 'pacing_score', label: '综合节奏', color: '#0ea5e9', enabled: true },
  { key: 'dialogue_ratio', label: '对话占比', color: '#a78bfa', enabled: false },
  { key: 'sentence_length_variance', label: '句长方差', color: '#34d399', enabled: false },
  { key: 'scene_transition_count', label: '场景转换', color: '#fbbf24', enabled: false },
  { key: 'emotional_volatility', label: '情感波动', color: '#f87171', enabled: false },
] as const

export default function PacingCurve({ bookId }: { bookId: string }) {
  const [data, setData] = useState<ChapterPacing[]>([])
  const [loading, setLoading] = useState(true)
  const [metrics, setMetrics] = useState<Record<string, boolean>>(
    Object.fromEntries(METRIC_CONFIG.map(m => [m.key, m.enabled]))
  )
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const dims = useResizeObserver(containerRef)

  useEffect(() => { loadData() }, [bookId])
  useEffect(() => { renderChart() }, [data, metrics, dims])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/pacing`)
      if (res.ok) {
        const json = await res.json()
        setData(json.chapters || [])
      }
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  function renderChart() {
    if (!svgRef.current || !data.length) return
    const container = containerRef.current
    if (!container) return
    const { w, h } = dims
    if (w < 200 || h < 100) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Use fixed internal coordinate space, scale to fit container via viewBox
    // This guarantees axis labels are never clipped regardless of container size
    const FIXED_W = 600
    const FIXED_H = 320
    svg.attr('viewBox', `0 0 ${FIXED_W} ${FIXED_H}`)
     .attr('preserveAspectRatio', 'xMidYMid meet')
     .attr('width', '100%').attr('height', '100%')
     .style('display', 'block')

    const margin = { top: 16, right: 20, bottom: 60, left: 44 }
    const innerW = FIXED_W - margin.left - margin.right
    const innerH = FIXED_H - margin.top - margin.bottom
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const x = d3.scaleLinear()
      .domain([1, data.length])
      .range([0, innerW])

    const activeMetrics = METRIC_CONFIG.filter(m => metrics[m.key])
    const allValues = data.flatMap(d =>
      activeMetrics.map(m => {
        const v = (d as any)[m.key]
        return typeof v === 'number' ? v : 0
      })
    )
    const maxY = d3.max(allValues) || 100
    const y = d3.scaleLinear().domain([0, maxY * 1.15]).range([innerH, 0])

    // Grid
    g.selectAll('.grid-h').data(y.ticks(4)).enter().append('line')
      .attr('x1', 0).attr('x2', innerW)
      .attr('y1', (d: any) => y(d)).attr('y2', (d: any) => y(d))
      .attr('stroke', '#27272a').attr('stroke-dasharray', '2,3')

    // Draw lines for each enabled metric
    activeMetrics.forEach(m => {
      const line = (d3.line() as any)
        .x((d: any) => x(d.chapter_index))
        .y((d: any) => y((d as any)[m.key] || 0))
        .curve(d3.curveMonotoneX)
      g.append('path').datum(data).attr('fill', 'none')
        .attr('stroke', m.color).attr('stroke-width', 2).attr('d', line)

      // Dots
      g.selectAll(`.dot-${m.key}`).data(data).enter().append('circle')
        .attr('cx', (d: any) => x(d.chapter_index))
        .attr('cy', (d: any) => y((d as any)[m.key] || 0))
        .attr('r', 3).attr('fill', m.color).attr('stroke', '#0b1220').attr('stroke-width', 1)
    })

    // X axis
    g.append('g').attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(Math.min(data.length, 12)).tickFormat(d => `第${d}章`))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 9)
        .attr('transform', 'rotate(-25)').attr('text-anchor', 'end').attr('dy', '0.5em'))

    // Y axis
    g.append('g')
      .call(d3.axisLeft(y).ticks(4))
      .call((g: any) => g.select('.domain').attr('stroke', '#3f3f46'))
      .call((g: any) => g.selectAll('text').attr('fill', '#71717a').attr('font-size', 10))

    // Tooltip
    const tooltip = d3.select(container).selectAll('.pacing-tip').data([0]).join('div')
      .attr('class', 'pacing-tip')
      .style('position', 'absolute').style('background', '#18181b')
      .style('border', '1px solid #3f3f46').style('border-radius', '8px')
      .style('padding', '8px 10px').style('font-size', '11px')
      .style('color', '#d4d4d8').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 30)

    g.selectAll('.hover-zone').data(data).enter().append('rect')
      .attr('class', 'hover-zone')
      .attr('x', (d: any) => x(d.chapter_index) - innerW / data.length / 2)
      .attr('y', 0).attr('width', innerW / data.length)
      .attr('height', innerH).attr('fill', 'transparent')
      .on('mouseover', (event: any, d: any) => {
        tooltip.style('opacity', 1)
          .html(`<div style="font-weight:600;color:#e4e4e7;margin-bottom:3px">第${d.chapter_index}章: ${d.title}</div>`
            + `<div>节奏分: <span style="color:#0ea5e9">${d.pacing_score}</span></div>`
            + `<div>对话: <span style="color:#a78bfa">${(d.dialogue_ratio * 100).toFixed(0)}%</span></div>`
            + `<div>场景转换: <span style="color:#fbbf24">${d.scene_transition_count}</span></div>`)
          .style('left', `${event.offsetX + 12}px`)
          .style('top', `${event.offsetY - 8}px`)
      })
      .on('mouseout', () => tooltip.style('opacity', 0))
  }

  function toggleMetric(key: string) {
    setMetrics(prev => ({ ...prev, [key]: !prev[key] }))
  }

  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="activity" size={16} className="text-sky-400" />
          <h3 className="text-sm font-semibold text-zinc-200">叙事节奏曲线</h3>
        </div>
        <div className="flex items-center justify-center py-16 text-zinc-600 text-sm">
          <div className="w-5 h-5 border-2 border-zinc-700 border-t-sky-400 rounded-full animate-spin mr-2" /> 加载节奏数据...
        </div>
      </div>
    )
  }

  if (!data.length) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="activity" size={16} className="text-sky-400" />
          <h3 className="text-sm font-semibold text-zinc-200">叙事节奏曲线</h3>
        </div>
        <div className="flex flex-col items-center gap-2 py-12 text-zinc-600">
          <Icon name="activity" size={28} />
          <p className="text-xs">暂无章节内容，无法分析节奏</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
          <Icon name="activity" size={14} /> 叙事节奏曲线
        </h3>
        <div className="flex flex-wrap gap-1">
          {METRIC_CONFIG.map(m => (
            <button
              key={m.key}
              onClick={() => toggleMetric(m.key)}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                metrics[m.key]
                  ? 'border-zinc-600 bg-zinc-700/50 text-zinc-200'
                  : 'border-zinc-800 text-zinc-600 hover:text-zinc-400'
              }`}
            >
              <span className="inline-block w-1.5 h-1.5 rounded-full mr-1" style={{ background: m.color }} />
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="relative" style={{ height: 260 }}>
        <svg ref={svgRef} className="w-full h-full" />
      </div>
    </div>
  )
}
