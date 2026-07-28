import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { useRefreshKey, useSelectedTimeOrder, setTimeOrder } from '../store'
import { DATA_COLORS } from './ui/colors'

const FLOAT_COLOR = DATA_COLORS.unknown.stroke

export default function TimelineView({ bookId }) {
  const refreshKey = useRefreshKey()
  const selectedTimeOrder = useSelectedTimeOrder()
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dims, setDims] = useState({ w: 900, h: 500 })
  const [selected, setSelected] = useState(null)
  const [eventEntities, setEventEntities] = useState<string[]>([])

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
      const res = await fetch(`/api/books/${bookId}/graph/timeline`)
      setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    if (!data || dims.w < 100) return
    renderTimeline()
  }, [data, dims, selected, selectedTimeOrder])

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
      .style('position', 'absolute').style('background', 'var(--color-zinc-800)')
      .style('border', '1px solid var(--color-zinc-700)').style('border-radius', '8px')
      .style('padding', '8px 12px').style('font-size', '11px').style('max-width', '220px')
      .style('color', 'var(--color-zinc-300)').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 20)

    const floatingEvents = events.filter(e => !e.track_id || e.track_id === 'main' && tracks.length === 1)
    const trackEvents = floatingEvents.length === events.length ? [] : events.filter(e => !floatingEvents.includes(e))
    const trackSpacing = 100

    // Use tracks that actually have events
    const activeTracks = tracks.filter(t => {
      const hasEvents = events.some(e => e.track_id === t.id)
      return hasEvents || t.id === 'main'
    })

    if (activeTracks.length === 0) {
      // Fallback: render all events on a single track
      const dispEvents = floatingEvents.length > 0 ? floatingEvents : events
      const track = { id: 'main', name: '时间线', color: '#22d3ee' }
      const ty = 0
      const scaleX = d3.scaleLinear().domain([0, Math.max(dispEvents.length - 1, 1)]).range([0, innerW])
      g.append('line').attr('x1', 0).attr('y1', ty).attr('x2', innerW).attr('y2', ty)
        .attr('stroke', track.color).attr('stroke-width', 2).attr('stroke-opacity', 0.3)
      g.append('text').attr('x', -10).attr('y', ty + 4).attr('text-anchor', 'end')
        .attr('fill', track.color).attr('font-size', 12).attr('font-weight', 600).text(track.name)
      renderTrackEvents(g, dispEvents, scaleX, ty, track.color, tooltip, '')
      return
    }

    activeTracks.forEach((track, ti) => {
      const ty = ti * trackSpacing
      const trackEvts = events
        .filter(e => e.track_id === track.id)
        .sort((a, b) => (a.order || 0) - (b.order || 0))

      if (trackEvts.length === 0) return

      const minSpacing = 80
      const totalNeeded = trackEvts.length * minSpacing
      const trackW = Math.max(innerW, totalNeeded)
      const scaleX = d3.scaleLinear().domain([0, Math.max(trackEvts.length - 1, 1)]).range([0, trackW])

      g.append('line').attr('x1', 0).attr('y1', ty).attr('x2', trackW).attr('y2', ty)
        .attr('stroke', track.color).attr('stroke-width', 2).attr('stroke-opacity', 0.3)
      g.append('text').attr('x', -10).attr('y', ty + 4).attr('text-anchor', 'end')
        .attr('fill', track.color).attr('font-size', 12).attr('font-weight', 600).text(track.name)

      renderTrackEvents(g, trackEvts, scaleX, ty, track.color, tooltip, trackW)
    })

    // Current time vertical indicator across all tracks
    if (selectedTimeOrder > 0) {
      const allEvts = events.sort((a, b) => (a.order || 0) - (b.order || 0))
      const currentEv = allEvts.find(e => (e.order || 0) === selectedTimeOrder)
        || allEvts.reduce((prev, curr) =>
          Math.abs((curr.order || 0) - selectedTimeOrder) < Math.abs((prev.order || 0) - selectedTimeOrder) ? curr : prev
        , allEvts[0])
      if (currentEv) {
        const allSorted = activeTracks.length > 0
          ? activeTracks.flatMap(t => events.filter(e => e.track_id === t.id).sort((a, b) => (a.order || 0) - (b.order || 0)))
          : allEvts
        const idx = allSorted.indexOf(currentEv)
        const totalW = Math.max(innerW, allSorted.length * 80)
        const cx = (idx / Math.max(allSorted.length - 1, 1)) * totalW
        g.append('line')
          .attr('x1', cx).attr('y1', -20).attr('x2', cx).attr('y2', activeTracks.length * trackSpacing)
          .attr('stroke', '#22d3ee').attr('stroke-width', 1.5).attr('stroke-dasharray', '4 4').attr('opacity', 0.5)
        g.append('text').attr('x', cx + 4).attr('y', -8).attr('fill', '#22d3ee').attr('font-size', 9)
          .text(`T${selectedTimeOrder}`)
      }
    }
  }

  const CHAR_DOT_COLORS = ['#a78bfa', '#34d399', '#fbbf24', '#60a5fa', '#f87171', '#c084fc', '#22d3ee', '#fb7185']

  function renderTrackEvents(g, evts, scaleX, ty, color, tooltip, trackW) {
    evts.forEach((ev, ei) => {
      const cx = scaleX(ei)
      const isSelected = selected?.id === ev.id
      const isCurrentTime = selectedTimeOrder > 0 && (ev.order || 0) === selectedTimeOrder
      const charCount = ev.characters?.length || 0
      // Dynamic node radius: base 5 + 1.5 per character (max +8), selected/current gets +3
      const nodeR = 5 + Math.min(charCount * 1.5, 8) + (isSelected ? 3 : 0) + (isCurrentTime ? 2 : 0)

      // Glow halo for important events (3+ characters)
      if (charCount >= 3 || isCurrentTime) {
        g.append('circle')
          .attr('cx', cx).attr('cy', ty).attr('r', nodeR + 6)
          .attr('fill', color).attr('opacity', isCurrentTime ? 0.25 : 0.12)
      }

      // Main event node
      g.append('circle')
        .attr('cx', cx).attr('cy', ty).attr('r', nodeR)
        .attr('fill', isSelected ? '#fff' : color)
        .attr('stroke', isCurrentTime ? '#22d3ee' : (isSelected ? color : 'var(--color-zinc-900)'))
        .attr('stroke-width', isCurrentTime ? 3 : (isSelected ? 3 : 2))
        .attr('cursor', 'pointer')
        .on('click', () => {
          setSelected(selected?.id === ev.id ? null : ev)
          if (selected?.id !== ev.id) {
            setTimeOrder(ev.order || 0)
            fetchEventEntities(ev.id)
          }
        })
        .on('mouseenter', function (event) {
          const lines = [`<b>${ev.label}</b>`]
          if (ev.description) lines.push(ev.description)
          if (charCount > 0) lines.push(`[角色 ${charCount}] ${ev.characters.join(', ')}`)
          if (ev.chapter_ref) lines.push(`[章节] ${ev.chapter_ref}`)
          if (ev.time_label) lines.push(`[时间] ${ev.time_label}`)
          tooltip.html(lines.join('<br/>'))
            .style('opacity', 1)
            .style('left', `${event.offsetX + 15}px`)
            .style('top', `${event.offsetY - 10}px`)
        })
        .on('mouseleave', () => tooltip.style('opacity', 0))

      // Character participation dots around the event node
      if (charCount > 0 && charCount <= 8) {
        ev.characters.forEach((charName: string, ci: number) => {
          const angle = (ci / charCount) * 2 * Math.PI - Math.PI / 2
          const dotR = nodeR + 7
          const dx = cx + dotR * Math.cos(angle)
          const dy = ty + dotR * Math.sin(angle)
          g.append('circle')
            .attr('cx', dx).attr('cy', dy).attr('r', 2.5)
            .attr('fill', CHAR_DOT_COLORS[ci % CHAR_DOT_COLORS.length])
            .attr('stroke', 'var(--color-zinc-900)').attr('stroke-width', 0.5)
            .attr('pointer-events', 'none')
        })
      }

      // Time label below node (show more characters)
      const timeText = ev.time_label || ev.chapter_ref || ''
      if (timeText) {
        g.append('text')
          .attr('x', cx).attr('y', ty + nodeR + 16)
          .attr('text-anchor', 'middle').attr('fill', isCurrentTime ? '#22d3ee' : 'var(--color-zinc-600)')
          .attr('font-size', 9)
          .text(timeText.length > 12 ? timeText.slice(0, 11) + '…' : timeText)
      }

      // Event label above node (show more characters, not just 5)
      const spacing = (trackW || 0) / evts.length
      if (spacing >= 50 || ei % Math.ceil(50 / Math.max(spacing, 1)) === 0) {
        const maxLabelLen = spacing >= 100 ? 12 : spacing >= 70 ? 10 : 8
        g.append('text')
          .attr('x', cx).attr('y', ty - nodeR - 8)
          .attr('text-anchor', 'middle').attr('fill', isCurrentTime ? '#67e8f9' : 'var(--color-zinc-300)')
          .attr('font-size', spacing >= 70 ? 10 : 9).attr('font-weight', isCurrentTime ? 700 : 500)
          .text(ev.label.length > maxLabelLen ? ev.label.slice(0, maxLabelLen - 1) + '…' : ev.label)
      }
    })
  }

  async function fetchEventEntities(eventId: string) {
    try {
      const res = await fetch(`/api/books/${bookId}/graph/impact/${eventId}`)
      if (res.ok) {
        const data = await res.json()
        setEventEntities(data.affected_entities || [])
      }
    } catch (e) { /* silent */ }
  }

  if (loading) return <LoadingState text="加载时间线..." />

  const totalTracks = (data?.tracks || []).length
  const totalEvents = (data?.events || []).length

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/40 backdrop-blur-sm shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5">
          <Icon name="clock" size={16} /> 时间线
        </h3>
        <div className="flex items-center gap-3 text-xs text-zinc-500">
          <span>{totalTracks} 轨道</span>
          <span className="text-zinc-700">·</span>
          <span>{totalEvents} 事件</span>
          <span className="text-zinc-700">·</span>
          <span>滚轮缩放 · 悬浮详情</span>
        </div>
      </div>

      {/* 4D identity banner */}
      <div className="px-6 py-2 bg-gradient-to-r from-cyan-950/30 to-blue-950/20 border-b border-cyan-900/30">
        <div className="flex items-center gap-3 text-[10px]">
          <span className="text-cyan-400 font-medium flex items-center gap-1">
            <Icon name="clock" size={12} /> 时间维度
          </span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-500">知识库 4D 图谱的时间侧面——点击事件同步时间轴到全局</span>
        </div>
      </div>

      <div className="flex-1 flex">
        <div ref={containerRef} className="flex-1 overflow-auto bg-zinc-950/60 relative">
          <svg ref={svgRef} className="w-full" style={{ minHeight: 400 }} />
        </div>

        {/* Detail sidebar */}
        {selected && (
          <div className="w-56 border-l border-zinc-800 bg-zinc-900/60 backdrop-blur-sm p-4 shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-zinc-200">{selected.label}</h4>
              <button onClick={() => setSelected(null)} className="text-xs text-zinc-500 hover:text-zinc-300 p-0.5">
                <Icon name="x" size={12} />
              </button>
            </div>

            {selected.time_label && (
              <p className="text-xs text-cyan-400 mb-2 flex items-center gap-1">
                <Icon name="clock" size={12} /> {selected.time_label}
              </p>
            )}
            {selected.description && (
              <p className="text-xs text-zinc-400 mb-2">{selected.description}</p>
            )}

            <div className="space-y-1.5 text-[11px]">
              {selected.track_id && (
                <p className="text-zinc-500">
                  轨道: <span className="text-zinc-300">{data?.tracks?.find(t => t.id === selected.track_id)?.name || '?'}</span>
                </p>
              )}
              {selected.chapter_ref && (
                <p className="text-zinc-500">章节: <span className="text-zinc-300">{selected.chapter_ref}</span></p>
              )}
              {selected.characters?.length > 0 && (
                <p className="text-zinc-500">角色: <span className="text-zinc-300">{selected.characters.join(', ')}</span></p>
              )}

              {eventEntities.length > 0 && (
                <div className="mt-3 pt-3 border-t border-zinc-800">
                  <p className="text-[10px] text-blue-400 font-medium mb-1.5 flex items-center gap-1">
                    <Icon name="link" size={10} /> 关联实体
                  </p>
                  {eventEntities.map((name: string, i: number) => (
                    <p key={i} className="text-[10px] text-zinc-400 flex items-center gap-1">
                      <Icon name="user" size={10} />{name}
                    </p>
                  ))}
                </div>
              )}

              <div className="mt-3 pt-3 border-t border-zinc-800">
                <p className="text-[10px] text-zinc-600">
                  时间顺序 #{selected.order || '?'}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}