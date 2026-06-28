import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { useResizeObserver } from '../hooks/useResizeObserver'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { useRefreshKey } from '../store'
import { DATA_COLORS, RELATION_COLORS, NODE_RADIUS, CONN_DASH } from './ui/colors'

const TYPE_STYLES = {
  world:    { color: DATA_COLORS.world.fill, stroke: DATA_COLORS.world.stroke, r: NODE_RADIUS.world },
  region:   { color: DATA_COLORS.region.fill, stroke: DATA_COLORS.region.stroke, r: NODE_RADIUS.region },
  city:     { color: DATA_COLORS.city.fill, stroke: DATA_COLORS.city.stroke, r: NODE_RADIUS.city },
  building: { color: DATA_COLORS.building.fill, stroke: DATA_COLORS.building.stroke, r: NODE_RADIUS.building },
  room:     { color: DATA_COLORS.room.fill, stroke: DATA_COLORS.room.stroke, r: NODE_RADIUS.room },
  other:    { color: DATA_COLORS.other.fill, stroke: DATA_COLORS.other.stroke, r: NODE_RADIUS.other },
}

const CONN_STYLES = {
  path:     { color: RELATION_COLORS.path, dash: CONN_DASH.path },
  portal:   { color: RELATION_COLORS.portal, dash: CONN_DASH.portal },
  contains: { color: RELATION_COLORS.contains, dash: CONN_DASH.contains },
  near:     { color: RELATION_COLORS.near, dash: CONN_DASH.near },
}

export default function WorldMap({ bookId }) {
  const refreshKey = useRefreshKey()
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const dimensions = useResizeObserver(containerRef)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const simRef = useRef(null)

  useEffect(() => { loadData() }, [bookId, refreshKey])

  async function loadData() {
    try {
      const res = await fetch(`/api/books/${bookId}/location-map`)
      setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    if (!data || !dimensions || dimensions.w < 100) return
    renderGraph()
    return () => { if (simRef.current) simRef.current.stop() }
  }, [data, dimensions])

  function renderGraph() {
    if (simRef.current) simRef.current.stop()
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const { w, h } = dimensions
    svg.attr('width', w).attr('height', h)

    const rawNodes = data.nodes || []
    const rawConns = data.connections || []

    if (rawNodes.length === 0) {
      svg.append('text').attr('x', w / 2).attr('y', h / 2)
        .attr('text-anchor', 'middle').attr('fill', '#52525b').attr('font-size', 13)
        .text('暂无地点数据。在对话中说"生成地图"来自动创建。')
      return
    }

    const g = svg.append('g')
    const zoom = d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform))
    svg.call(zoom)

    const nameToNode = {}
    const nodes = rawNodes.map(n => {
      const s = TYPE_STYLES[n.type] || TYPE_STYLES.other
      const node = { ...n, r: s.r, color: s.color, stroke: s.stroke }
      nameToNode[n.name] = node
      return node
    })

    const links = rawConns
      .map(c => {
        const src = nameToNode[c.from]
        const tgt = nameToNode[c.to]
        if (!src || !tgt) return null
        const cs = CONN_STYLES[c.type] || CONN_STYLES.path
        return { source: src, target: tgt, label: c.label || c.type, color: cs.color, dash: cs.dash }
      })
      .filter(Boolean)

    const connectedIds = new Set()
    links.forEach(l => { connectedIds.add(l.source.id); connectedIds.add(l.target.id) })

    const padding = 60
    const nodeCount = nodes.length
    nodes.forEach((n, i) => {
      const golden = 2.399963
      const angle = i * golden + (Math.random() - 0.5) * 1.2
      const spread = Math.min(w, h) * (0.15 + Math.random() * 0.25)
      n.x = w / 2 + spread * Math.cos(angle)
      n.y = h / 2 + spread * Math.sin(angle)
    })

    const density = links.length / Math.max(nodeCount, 1)
    const charge = -Math.max(1200, nodeCount * 200 + density * 150)
    const linkDist = Math.max(120, Math.min(300, Math.sqrt(w * h / nodeCount) * 0.9))

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).distance(linkDist).strength(0.12))
      .force('charge', d3.forceManyBody().strength(charge).distanceMin(40).distanceMax(Math.max(w, h)))
      .force('x', d3.forceX(w / 2).strength(0.02))
      .force('y', d3.forceY(h / 2).strength(0.02))
      .force('collision', d3.forceCollide().radius(d => d.r + 30).strength(1))
      .velocityDecay(0.3).alpha(1).alphaDecay(0.006)
    simRef.current = simulation

    const pairCounts = {}
    links.forEach(l => {
      const key = [l.source.id || l.source, l.target.id || l.target].sort().join('|')
      pairCounts[key] = (pairCounts[key] || 0) + 1
    })
    const pairIndex = {}
    links.forEach(l => {
      const key = [l.source.id || l.source, l.target.id || l.target].sort().join('|')
      pairIndex[key] = (pairIndex[key] || 0)
      l._ci = pairIndex[key]
      l._ct = pairCounts[key]
      pairIndex[key]++
    })

    simulation.stop()
    for (let i = 0; i < 400; i++) simulation.tick()
    nodes.forEach(n => {
      n.x = Math.max(padding, Math.min(w - padding, n.x))
      n.y = Math.max(padding, Math.min(h - padding, n.y))
    })

    function edgePath(d) {
      const sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
      if (d._ct <= 1) {
        const dx = tx - sx, dy = ty - sy, dr = Math.sqrt(dx * dx + dy * dy) * 2
        return `M${sx},${sy} A${dr},${dr} 0 0,1 ${tx},${ty}`
      }
      const off = (d._ci - (d._ct - 1) / 2) * 35
      const mx = (sx + tx) / 2, my = (sy + ty) / 2
      const dx = tx - sx, dy = ty - sy, len = Math.sqrt(dx * dx + dy * dy) || 1
      return `M${sx},${sy} Q${mx + (-dy / len) * off},${my + (dx / len) * off} ${tx},${ty}`
    }
    function edgeMid(d) {
      const sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
      if (d._ct <= 1) return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
      const off = (d._ci - (d._ct - 1) / 2) * 35
      const mx = (sx + tx) / 2, my = (sy + ty) / 2
      const dx = tx - sx, dy = ty - sy, len = Math.sqrt(dx * dx + dy * dy) || 1
      return { x: mx + (-dy / len) * off * 0.5, y: my + (dx / len) * off * 0.5 }
    }

    const link = g.append('g').selectAll('path').data(links).join('path')
      .attr('stroke', d => d.color).attr('stroke-width', 1.5).attr('stroke-opacity', 0.45)
      .attr('fill', 'none').attr('stroke-dasharray', d => d.dash)
      .attr('d', edgePath)

    const linkLabel = g.append('g').selectAll('text').data(links).join('text')
      .text(d => d.label).attr('font-size', 8).attr('fill', '#52525b')
      .attr('text-anchor', 'middle').attr('dy', -4)
      .each(function(d) { const m = edgeMid(d); d3.select(this).attr('x', m.x).attr('y', m.y) })

    const node = g.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('r', d => d.r).attr('fill', d => d.color).attr('stroke', d => d.stroke)
      .attr('stroke-width', 2).attr('opacity', d => connectedIds.has(d.id) ? 1 : 0.6)
      .attr('cursor', 'pointer').attr('cx', d => d.x).attr('cy', d => d.y)
      .call(d3.drag()
        .on('start', (e, d) => { simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
        .on('end', (e, d) => { simulation.alphaTarget(0); d.fx = null; d.fy = null }))
      .on('click', (e, d) => setSelected(selected?.id === d.id ? null : d))

    const label = g.append('g').selectAll('text').data(nodes).join('text')
      .text(d => d.name).attr('font-size', d => d.r >= 13 ? 11 : 9)
      .attr('font-weight', 500).attr('fill', '#e4e4e7')
      .attr('text-anchor', 'middle').attr('dy', d => -(d.r + 8))
      .attr('pointer-events', 'none').attr('x', d => d.x).attr('y', d => d.y)

    simulation.on('tick', () => {
      link.attr('d', edgePath)
      linkLabel.each(function(d) { const m = edgeMid(d); d3.select(this).attr('x', m.x).attr('y', m.y) })
      node.attr('cx', d => d.x).attr('cy', d => d.y)
      label.attr('x', d => d.x).attr('y', d => d.y)
    })
    simulation.alpha(0.3).restart()
  }

  if (loading) return <LoadingState text="加载地图..." />

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="map" size={16} /> 地点关系图</h3>
        <div className="flex gap-3 text-[10px] text-zinc-500">
          {Object.entries(TYPE_STYLES).filter(([k]) => k !== 'other').map(([type, s]) => (
            <span key={type} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full border" style={{ background: s.color, borderColor: s.stroke }}></span>
              {type}
            </span>
          ))}
          <span className="text-zinc-700 mx-1">|</span>
          {Object.entries(CONN_STYLES).map(([type, s]) => (
            <span key={type} className="flex items-center gap-1">
              <span className="w-3 h-0.5" style={{ background: s.color, borderTop: s.dash ? '1px dashed' : 'none' }}></span>
              {type}
            </span>
          ))}
        </div>
      </div>

      <div className="flex-1 flex">
        <div ref={containerRef} className="flex-1 relative overflow-hidden bg-zinc-950">
          <svg ref={svgRef} className="w-full h-full" />
        </div>

        {selected && (
          <div className="w-56 border-l border-zinc-800 bg-zinc-900/80 p-4 shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-zinc-200 flex items-center gap-1"><Icon name="map-pin" size={14} /> {selected.name}</h4>
              <button onClick={() => setSelected(null)} className="text-xs text-zinc-600 hover:text-zinc-300"><Icon name="x" size={12} /></button>
            </div>
            {selected.type && (
              <p className="text-[10px] text-zinc-500 mb-2">类型: <span className="text-zinc-300">{selected.type}</span></p>
            )}
            {selected.description && (
              <p className="text-xs text-zinc-400 mb-2">{selected.description}</p>
            )}
            {selected.parent && (
              <p className="text-[10px] text-zinc-500">所属: <span className="text-zinc-300">{selected.parent}</span></p>
            )}
          </div>
        )}
      </div>

      <div className="px-4 py-1.5 border-t border-zinc-800 text-[10px] text-zinc-600">
        拖拽节点移动 · 滚轮缩放 · 点击地点查看详情 · 实线=物理路径 虚线=传送/包含
      </div>
    </div>
  )
}
