import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon.jsx'
import LoadingState from './ui/Skeleton.jsx'
import { useRefreshKey } from '../store.js'
import { DATA_COLORS } from './ui/colors.js'

const FLOAT_COLOR = DATA_COLORS.unknown.stroke

export default function TimelineView({ bookId }) {
  const refreshKey = useRefreshKey()
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dims, setDims] = useState({ w: 900, h: 500 })
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    loadData()
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0) setDims({ w: width, h: Math.max(height, 400) })
    })
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [bookId, refreshKey])

  async function loadData() {
    try {
      const res = await fetch(`/api/books/${bookId}/timeline-data`)
      setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    if (!data || dims.w < 100) return
    renderTimeline()
  }, [data, dims, selected])

  function renderTimeline() {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    const { w, h } = dims
    svg.attr('width', w).attr('height', h)

    const tracks = data.tracks || []
    const events = data.events || []

    if (events.length === 0) {
      svg.append('text').attr('x', w / 2).attr('y', h / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无时间线数据。在对话中说"生成时间线"来自动创建。')
      return
    }

    const margin = { top: 60, right: 50, bottom: 40, left: 110 }
    const innerW = w - margin.left - margin.right
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const zoom = d3.zoom().scaleExtent([0.3, 5]).on('zoom', (event) => {
      g.attr('transform', `translate(${margin.left + event.transform.x},${margin.top + event.transform.y}) scale(${event.transform.k})`)
    })
    svg.call(zoom)

    const tooltip = d3.select(containerRef.current).selectAll('.tl-tooltip').data([0]).join('div')
      .attr('class', 'tl-tooltip')
      .style('position', 'absolute').style('background', '#27272a')
      .style('border', '1px solid #52525b').style('border-radius', '8px')
      .style('padding', '8px 12px').style('font-size', '11px').style('max-width', '220px')
      .style('color', '#d4d4d8').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 20)

    const floatingEvents = events.filter(e => !e.track_id)
    const trackSpacing = 90
    const nodeR = 7

    tracks.forEach((track, ti) => {
      const ty = ti * trackSpacing
      const trackEvents = events
        .filter(e => e.track_id === track.id)
        .sort((a, b) => (a.order || 0) - (b.order || 0))

      if (trackEvents.length === 0) return

      const minSpacing = 80
      const totalNeeded = trackEvents.length * minSpacing
      const trackW = Math.max(innerW, totalNeeded)

      const scaleX = d3.scaleLinear()
        .domain([0, Math.max(trackEvents.length - 1, 1)])
        .range([0, trackW])

      g.append('line')
        .attr('x1', 0).attr('y1', ty).attr('x2', trackW).attr('y2', ty)
        .attr('stroke', track.color).attr('stroke-width', 2).attr('stroke-opacity', 0.3)

      g.append('text')
        .attr('x', -10).attr('y', ty + 4)
        .attr('text-anchor', 'end').attr('fill', track.color)
        .attr('font-size', 12).attr('font-weight', 600)
        .text(track.name)

      trackEvents.forEach((ev, ei) => {
        const cx = scaleX(ei)
        const isSelected = selected?.id === ev.id

        g.append('circle')
          .attr('cx', cx).attr('cy', ty).attr('r', isSelected ? nodeR + 3 : nodeR)
          .attr('fill', isSelected ? '#fff' : track.color)
          .attr('stroke', isSelected ? track.color : '#18181b')
          .attr('stroke-width', isSelected ? 3 : 2)
          .attr('cursor', 'pointer')
          .on('click', () => setSelected(selected?.id === ev.id ? null : ev))
          .on('mouseenter', function (event) {
            const lines = [`<b>${ev.label}</b>`]
            if (ev.description) lines.push(ev.description)
            if (ev.characters?.length) lines.push(`👤 ${ev.characters.join(', ')}`)
            if (ev.chapter_ref) lines.push(`📖 ${ev.chapter_ref}`)
            tooltip.html(lines.join('<br/>'))
              .style('opacity', 1)
              .style('left', `${event.offsetX + 15}px`)
              .style('top', `${event.offsetY - 10}px`)
          })
          .on('mouseleave', () => tooltip.style('opacity', 0))

        const timeText = ev.time_label || ev.chapter_ref || ''
        if (timeText) {
          g.append('text')
            .attr('x', cx).attr('y', ty + nodeR + 16)
            .attr('text-anchor', 'middle').attr('fill', '#52525b')
            .attr('font-size', 8)
            .text(timeText.length > 8 ? timeText.slice(0, 7) + '…' : timeText)
        }

        const spacing = trackW / trackEvents.length
        if (spacing >= 50 || ei % Math.ceil(50 / Math.max(spacing, 1)) === 0) {
          g.append('text')
            .attr('x', cx).attr('y', ty - nodeR - 8)
            .attr('text-anchor', 'middle').attr('fill', '#d4d4d8')
            .attr('font-size', spacing >= 70 ? 10 : 9)
            .attr('font-weight', 500)
            .text(ev.label.length > 6 ? ev.label.slice(0, 5) + '…' : ev.label)
        }
      })
    })

    if (floatingEvents.length > 0) {
      const floatY = tracks.length * trackSpacing + 40

      g.append('text')
        .attr('x', -10).attr('y', floatY + 4)
        .attr('text-anchor', 'end').attr('fill', FLOAT_COLOR)
        .attr('font-size', 11).attr('font-weight', 500)
        .text('散点')

      g.append('line')
        .attr('x1', 0).attr('y1', floatY).attr('x2', innerW).attr('y2', floatY)
        .attr('stroke', FLOAT_COLOR).attr('stroke-width', 1).attr('stroke-dasharray', '4,4')

      const fSpacing = Math.max(60, innerW / floatingEvents.length)
      floatingEvents.forEach((ev, fi) => {
        const cx = (fi + 0.5) * fSpacing
        const isSelected = selected?.id === ev.id

        g.append('rect')
          .attr('x', cx - 5).attr('y', floatY - 5)
          .attr('width', 10).attr('height', 10).attr('rx', 2)
          .attr('fill', isSelected ? '#fff' : FLOAT_COLOR)
          .attr('stroke', '#18181b').attr('stroke-width', 1.5)
          .attr('cursor', 'pointer')
          .on('click', () => setSelected(selected?.id === ev.id ? null : ev))
          .on('mouseenter', function (event) {
            tooltip.html(`<b>${ev.label}</b>${ev.description ? '<br/>' + ev.description : ''}`)
              .style('opacity', 1)
              .style('left', `${event.offsetX + 15}px`)
              .style('top', `${event.offsetY - 10}px`)
          })
          .on('mouseleave', () => tooltip.style('opacity', 0))

        if (fSpacing >= 50) {
          g.append('text')
            .attr('x', cx).attr('y', floatY - 12)
            .attr('text-anchor', 'middle').attr('fill', '#a1a1aa')
            .attr('font-size', 9)
            .text(ev.label.length > 6 ? ev.label.slice(0, 5) + '…' : ev.label)
        }
      })
    }
  }

  if (loading) return <LoadingState text="加载时间线..." />

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="clock" size={16} /> 多轨时间线</h3>
        <span className="text-xs text-zinc-600">
          {(data?.tracks || []).length} 轨道 · {(data?.events || []).length} 事件 · 滚轮缩放 · 悬浮查看详情
        </span>
      </div>

      <div className="flex-1 flex">
        <div ref={containerRef} className="flex-1 overflow-auto bg-zinc-950 relative">
          <svg ref={svgRef} className="w-full" style={{ minHeight: 400 }} />
        </div>

        {selected && (
          <div className="w-56 border-l border-zinc-800 bg-zinc-900/80 p-4 shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-zinc-200">{selected.label}</h4>
              <button onClick={() => setSelected(null)} className="text-xs text-zinc-600 hover:text-zinc-300">✕</button>
            </div>
            {selected.time_label && (
              <p className="text-xs text-cyan-400 mb-2 flex items-center gap-1"><Icon name="clock" size={12} /> {selected.time_label}</p>
            )}
            {selected.description && (
              <p className="text-xs text-zinc-400 mb-2">{selected.description}</p>
            )}
            <div className="space-y-1.5 text-[11px]">
              {selected.track_id && (
                <p className="text-zinc-500">轨道: <span className="text-zinc-300">{data?.tracks?.find(t => t.id === selected.track_id)?.name || '?'}</span></p>
              )}
              {!selected.track_id && <p className="text-zinc-500">类型: <span className="text-zinc-400">散点</span></p>}
              {selected.chapter_ref && <p className="text-zinc-500">章节: <span className="text-zinc-300">{selected.chapter_ref}</span></p>}
              {selected.characters?.length > 0 && (
                <p className="text-zinc-500">角色: <span className="text-zinc-300">{selected.characters.join(', ')}</span></p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
