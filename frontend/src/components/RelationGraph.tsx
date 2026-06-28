import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import { useResizeObserver } from '../hooks/useResizeObserver'
import Icon from './ui/Icon'
import { DATA_COLORS, RELATION_COLORS } from './ui/colors'

const RELATION_COLORS_MAP = RELATION_COLORS

const NODE_STYLES = {
  character:     { color: DATA_COLORS.character.fill, stroke: DATA_COLORS.character.stroke, emoji: '👤', icon: 'user' },
  location:      { color: DATA_COLORS.location.fill, stroke: DATA_COLORS.location.stroke, emoji: '📍', icon: 'map-pin' },
  organization:  { color: DATA_COLORS.organization.fill, stroke: DATA_COLORS.organization.stroke, emoji: '🏛', icon: 'building' },
  event:         { color: DATA_COLORS.event.fill, stroke: DATA_COLORS.event.stroke, emoji: '⚡', icon: 'zap' },
  item:          { color: DATA_COLORS.item.fill, stroke: DATA_COLORS.item.stroke, emoji: '🔮', icon: 'star' },
  concept:       { color: DATA_COLORS.concept.fill, stroke: DATA_COLORS.concept.stroke, emoji: '💡', icon: 'lightbulb' },
  unknown:       { color: DATA_COLORS.unknown.fill, stroke: DATA_COLORS.unknown.stroke, emoji: '?', icon: 'info' },
}

export default function RelationGraph({ bookId, characters, timelineEvents, selectedTime, onSelectChar }) {
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const dimensions = useResizeObserver(containerRef)
  const [error, setError] = useState(null)
  const simulationRef = useRef(null)

  useEffect(() => {
    if (!characters || characters.length === 0) return
    if (!svgRef.current) return
    const { w, h } = dimensions
    if (w < 100 || h < 100) return

    try {
      renderGraph()
    } catch (e) {
      console.error(e)
      setError(e.message)
    }

    return () => {
      if (simulationRef.current) simulationRef.current.stop()
      const svg = d3.select(svgRef.current)
      if (!svg.empty()) svg.selectAll('*').remove()
    }
  }, [characters, selectedTime, dimensions])

  function renderGraph() {
    if (simulationRef.current) simulationRef.current.stop()

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const { w, h } = dimensions
    svg.attr('width', w).attr('height', h)

    const g = svg.append('g')

    const getTimeOrder = (tp) => {
      const ev = timelineEvents?.find(e => e.timePoint === tp)
      return ev?.timeOrder ?? 0
    }
    const selOrder = selectedTime === 'all' ? Infinity : getTimeOrder(selectedTime)

    const nodes = characters.map(c => ({
      id: c.id, name: c.name || '?', relationCount: c.relationCount || 0, nodeType: 'character',
    }))
    const nodeIds = new Set(nodes.map(n => n.id))

    const links = []
    const processedPairs = new Set()
    for (const c of characters) {
      for (const r of (c.relations || [])) {
        const pair = [c.id, r.targetId].sort().join('|') + '|' + r.type
        if (processedPairs.has(pair)) continue
        processedPairs.add(pair)
        const rTimeOrder = r.timePoint ? getTimeOrder(r.timePoint) : 0
        if (selOrder < Infinity && rTimeOrder > selOrder && r.timePoint) continue

        if (!nodeIds.has(r.targetId)) {
          nodes.push({
            id: r.targetId,
            name: r.targetName || r.targetId.slice(0, 8),
            relationCount: 0,
            nodeType: r.targetType || 'unknown',
          })
          nodeIds.add(r.targetId)
        }
        links.push({ source: c.id, target: r.targetId, type: r.type, timePoint: r.timePoint || '' })
      }
    }

    const linkedIds = new Set()
    links.forEach(l => { linkedIds.add(l.source); linkedIds.add(l.target) })
    const visibleNodes = links.length > 0 ? nodes.filter(n => linkedIds.has(n.id)) : nodes

    if (visibleNodes.length === 0) return

    const nodeCount = visibleNodes.length
    const padding = 80
    const availW = w - padding * 2
    const availH = h - padding * 2

    visibleNodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / nodeCount + (Math.random() - 0.5) * 0.8
      const r = Math.min(availW, availH) * (0.25 + Math.random() * 0.2)
      n.x = w / 2 + r * Math.cos(angle)
      n.y = h / 2 + r * Math.sin(angle)
    })

    const density = links.length / Math.max(nodeCount, 1)
    const linkDistance = Math.max(120, Math.min(300, Math.sqrt(availW * availH / nodeCount) * 0.9))
    const chargeStrength = -Math.max(1000, nodeCount * 180 + density * 100)

    const simulation = d3.forceSimulation(visibleNodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(linkDistance).strength(0.15))
      .force('charge', d3.forceManyBody().strength(chargeStrength).distanceMin(40).distanceMax(Math.max(w, h) * 0.8))
      .force('x', d3.forceX(w / 2).strength(0.02))
      .force('y', d3.forceY(h / 2).strength(0.02))
      .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 35).strength(1))
      .velocityDecay(0.35)
      .alpha(1)
      .alphaDecay(0.008)

    simulationRef.current = simulation

    const pairCounts = {}
    links.forEach(l => {
      const key = [l.source?.id || l.source, l.target?.id || l.target].sort().join('|')
      pairCounts[key] = (pairCounts[key] || 0) + 1
    })
    const pairIndex = {}
    links.forEach(l => {
      const key = [l.source?.id || l.source, l.target?.id || l.target].sort().join('|')
      pairIndex[key] = (pairIndex[key] || 0)
      l._curveIndex = pairIndex[key]
      l._curveTotal = pairCounts[key]
      pairIndex[key]++
    })

    simulation.stop()
    for (let i = 0; i < 350; i++) simulation.tick()

    visibleNodes.forEach(n => {
      n.x = Math.max(padding, Math.min(w - padding, n.x))
      n.y = Math.max(padding, Math.min(h - padding, n.y))
    })

    const zoom = d3.zoom().scaleExtent([0.3, 4]).on('zoom', (event) => {
      g.attr('transform', event.transform)
    })
    svg.call(zoom)

    function linkPath(d) {
      const sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
      if (d._curveTotal <= 1) {
        const dx = tx - sx, dy = ty - sy
        const dr = Math.sqrt(dx * dx + dy * dy) * 2.5
        return `M${sx},${sy} A${dr},${dr} 0 0,1 ${tx},${ty}`
      }
      const offset = (d._curveIndex - (d._curveTotal - 1) / 2) * 40
      const mx = (sx + tx) / 2, my = (sy + ty) / 2
      const dx = tx - sx, dy = ty - sy
      const len = Math.sqrt(dx * dx + dy * dy) || 1
      const cx = mx + (-dy / len) * offset
      const cy = my + (dx / len) * offset
      return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
    }

    function linkMidpoint(d) {
      const sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
      if (d._curveTotal <= 1) return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
      const offset = (d._curveIndex - (d._curveTotal - 1) / 2) * 40
      const mx = (sx + tx) / 2, my = (sy + ty) / 2
      const dx = tx - sx, dy = ty - sy
      const len = Math.sqrt(dx * dx + dy * dy) || 1
      return { x: mx + (-dy / len) * offset * 0.5, y: my + (dx / len) * offset * 0.5 }
    }

    const link = g.append('g').attr('class', 'links').selectAll('path').data(links).join('path')
      .attr('stroke', d => RELATION_COLORS_MAP[d.type] || DATA_COLORS.unknown.stroke)
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.45)
      .attr('fill', 'none')
      .attr('d', linkPath)

    const linkLabel = g.append('g').attr('class', 'link-labels').selectAll('text').data(links).join('text')
      .text(d => d.type)
      .attr('font-size', 8)
      .attr('fill', '#52525b')
      .attr('text-anchor', 'middle')
      .attr('dy', -4)
      .each(function(d) {
        const m = linkMidpoint(d)
        d3.select(this).attr('x', m.x).attr('y', m.y)
      })

    const node = g.append('g').attr('class', 'nodes').selectAll('circle').data(visibleNodes).join('circle')
      .attr('r', d => getNodeRadius(d))
      .attr('fill', d => (NODE_STYLES[d.nodeType] || NODE_STYLES.unknown).color)
      .attr('stroke', d => (NODE_STYLES[d.nodeType] || NODE_STYLES.unknown).stroke)
      .attr('stroke-width', d => d.nodeType === 'character' ? 2 : 1.5)
      .attr('opacity', d => d.nodeType === 'character' ? 1 : 0.8)
      .attr('cursor', 'pointer')
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)
      .call(d3.drag()
        .on('start', (event, d) => {
          simulation.alphaTarget(0.3).restart()
          d.fx = d.x; d.fy = d.y
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => {
          simulation.alphaTarget(0)
          d.fx = null; d.fy = null
        }))
      .on('click', (event, d) => {
        const char = characters.find(c => c.id === d.id)
        if (char && onSelectChar) onSelectChar(char)
      })

    const label = g.append('g').attr('class', 'labels').selectAll('text').data(visibleNodes).join('text')
      .text(d => {
        if (d.nodeType === 'character') return d.name
        const emoji = (NODE_STYLES[d.nodeType] || NODE_STYLES.unknown).emoji
        return `${emoji}${d.name}`
      })
      .attr('font-size', d => d.nodeType === 'character' ? 11 : 9)
      .attr('font-weight', d => d.nodeType === 'character' ? 500 : 400)
      .attr('fill', d => d.nodeType === 'character' ? '#e4e4e7' : '#a1a1aa')
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(getNodeRadius(d) + 8))
      .attr('pointer-events', 'none')
      .attr('x', d => d.x)
      .attr('y', d => d.y)

    simulation.on('tick', () => {
      link.attr('d', linkPath)
      linkLabel.each(function(d) {
        const m = linkMidpoint(d)
        d3.select(this).attr('x', m.x).attr('y', m.y)
      })
      node.attr('cx', d => d.x).attr('cy', d => d.y)
      label.attr('x', d => d.x).attr('y', d => d.y)
    })

    simulation.alpha(0.3).restart()
  }

  function getNodeRadius(d) {
    if (d.nodeType !== 'character') return 8
    return Math.min(14 + (d.relationCount || 0) * 2, 30)
  }

  if (error) return <div className="flex-1 flex items-center justify-center text-red-400 text-sm">⚠️ {error}</div>
  if (!characters || characters.length === 0)
    return <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">无角色数据</div>

  return (
    <div className="flex-1 flex flex-col relative overflow-hidden">
      <div className="px-4 py-2 border-b border-zinc-800 flex gap-4 flex-wrap text-[10px] text-zinc-500">
        {Object.entries(NODE_STYLES).filter(([k]) => k !== 'unknown').map(([type, s]) => (
          <span key={type} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full border" style={{ background: s.color, borderColor: s.stroke }}></span>
            <Icon name={s.icon} size={10} />{type}
          </span>
        ))}
        <span className="text-zinc-700 mx-1">|</span>
        {Object.entries(RELATION_COLORS).map(([type, color]) => (
          <span key={type} className="flex items-center gap-1">
            <span className="w-3 h-0.5" style={{ background: color }}></span>
            {type}
          </span>
        ))}
      </div>
      <div ref={containerRef} className="flex-1 relative">
        <svg ref={svgRef} className="w-full h-full" />
      </div>
      <div className="px-4 py-1.5 border-t border-zinc-800 text-[10px] text-zinc-600">
        拖拽节点移动 · 滚轮缩放 · 点击角色查看详情
      </div>
    </div>
  )
}
