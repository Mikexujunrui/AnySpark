import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { useResizeObserver } from '../hooks/useResizeObserver'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { useRefreshKey, useSelectedTimeOrder } from '../store'
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
  path:        { color: RELATION_COLORS.path, dash: CONN_DASH.path },
  portal:      { color: RELATION_COLORS.portal, dash: CONN_DASH.portal },
  contains:    { color: RELATION_COLORS.contains, dash: CONN_DASH.contains },
  near:        { color: RELATION_COLORS.near, dash: CONN_DASH.near },
  located_in:  { color: RELATION_COLORS.located_in, dash: CONN_DASH.located_in },
  adjacent_to: { color: RELATION_COLORS.adjacent_to, dash: CONN_DASH.adjacent_to },
  belongs_to:  { color: RELATION_COLORS.belongs_to, dash: CONN_DASH.contains },
  located_at:  { color: RELATION_COLORS.located_at, dash: CONN_DASH.path },
}

export default function WorldMap({ bookId }) {
  const refreshKey = useRefreshKey()
  const selectedTimeOrder = useSelectedTimeOrder()
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const dimensions = useResizeObserver(containerRef)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const simRef = useRef(null)
  // 4D Map: Time-aware character positions
  const [timeMap, setTimeMap] = useState<any>(null)

  useEffect(() => { loadData() }, [bookId, refreshKey])

  useEffect(() => {
    if (selectedTimeOrder >= 0) fetchTimeMap()
  }, [bookId, selectedTimeOrder])

  async function fetchTimeMap() {
    try {
      const res = await fetch(`/api/books/${bookId}/graph/map-at-time?time_order=${selectedTimeOrder}`)
      if (res.ok) setTimeMap(await res.json())
    } catch (e) { /* silent */ }
  }

  async function loadData() {
    try {
      const res = await fetch(`/api/books/${bookId}/graph/location-map`)
      setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    if (!data || !dimensions || dimensions.w < 100) return
    renderGraph()
    return () => { if (simRef.current) simRef.current.stop() }
  }, [data, dimensions, timeMap])

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

    const linkDist = Math.max(120, Math.min(300, Math.sqrt(w * h / nodeCount) * 0.9))

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).distance(linkDist).strength(0.12))
      .force('charge', d3.forceManyBody().strength(-400).distanceMin(40).distanceMax(Math.max(w, h)))
      .force('x', d3.forceX(w / 2).strength(0.02))
      .force('y', d3.forceY(h / 2).strength(0.02))
      .force('collision', d3.forceCollide().radius(d => d.r + 30).strength(1))
      .velocityDecay(0.4)
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

    // ── Hierarchy bounding circles: group children with their parent ──
    const parentGroups: Record<string, any[]> = {}
    nodes.forEach(n => {
      if (n.parent) {
        if (!parentGroups[n.parent]) parentGroups[n.parent] = []
        parentGroups[n.parent].push(n)
      }
    })
    Object.entries(parentGroups).forEach(([parentName, children]) => {
      const parentNode = nameToNode[parentName]
      if (!parentNode) return
      const allNodes = [parentNode, ...children]
      const xs = allNodes.map((n: any) => n.x || 0)
      const ys = allNodes.map((n: any) => n.y || 0)
      const minX = Math.min(...xs), maxX = Math.max(...xs)
      const minY = Math.min(...ys), maxY = Math.max(...ys)
      const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
      const radius = Math.max(Math.max(maxX - minX, maxY - minY) / 2 + 25, 35)
      g.append('circle')
        .attr('cx', cx).attr('cy', cy).attr('r', radius)
        .attr('fill', parentNode.color).attr('fill-opacity', 0.04)
        .attr('stroke', parentNode.stroke).attr('stroke-width', 1)
        .attr('stroke-opacity', 0.15).attr('stroke-dasharray', '4 4')
        .attr('pointer-events', 'none')
      g.append('text')
        .attr('x', cx).attr('y', cy - radius - 4)
        .attr('text-anchor', 'middle').attr('font-size', 8)
        .attr('fill', parentNode.stroke).attr('opacity', 0.4)
        .attr('pointer-events', 'none').text(parentNode.name)
    })

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
      .attr('font-weight', 500).attr('fill', 'var(--color-zinc-200)')
      .attr('text-anchor', 'middle').attr('dy', d => -(d.r + 8))
      .attr('pointer-events', 'none').attr('x', d => d.x).attr('y', d => d.y)

    // ── Character dots on map nodes (time-aware) ──
    const CHAR_COLORS = ['#a78bfa', '#34d399', '#fbbf24', '#60a5fa', '#f87171', '#c084fc', '#22d3ee', '#fb7185']
    const idToNode: Record<string, any> = {}
    nodes.forEach(n => { idToNode[n.id] = n })
    const charDotData: { node: any; angle: number; dotR: number; color: string; charName: string }[] = []
    if (timeMap?.characters_at_locations) {
      Object.entries(timeMap.characters_at_locations).forEach(([locId, locData]: [string, any]) => {
        const node = idToNode[locId]
        if (!node) return
        const chars = locData.characters || []
        chars.forEach((char: any, ci: number) => {
          const angle = (ci / Math.max(chars.length, 1)) * 2 * Math.PI - Math.PI / 2
          const dotR = (node.r || 8) + 9
          const color = CHAR_COLORS[ci % CHAR_COLORS.length]
          const dx = (node.x || 0) + dotR * Math.cos(angle)
          const dy = (node.y || 0) + dotR * Math.sin(angle)
          g.append('circle')
            .attr('cx', dx).attr('cy', dy).attr('r', 4.5)
            .attr('fill', color).attr('stroke', '#18181b').attr('stroke-width', 1)
            .attr('cursor', 'pointer').attr('class', 'char-dot')
            .on('click', () => setSelected(node))
          g.append('text')
            .attr('x', dx).attr('y', dy + 1.5).attr('text-anchor', 'middle')
            .attr('font-size', 7).attr('fill', '#fff').attr('font-weight', 700)
            .attr('pointer-events', 'none').attr('class', 'char-dot-label')
            .text(char.name?.[0] || '?')
          charDotData.push({ node, angle, dotR, color, charName: char.name })
        })
      })
    }

    simulation.on('tick', () => {
      link.attr('d', edgePath)
      linkLabel.each(function(d) { const m = edgeMid(d); d3.select(this).attr('x', m.x).attr('y', m.y) })
      node.attr('cx', d => d.x).attr('cy', d => d.y)
      label.attr('x', d => d.x).attr('y', d => d.y)
      // Update character dots positions
      g.selectAll('.char-dot').each(function(d, i) {
        const info = charDotData[i]
        if (!info) return
        const dx = (info.node.x || 0) + info.dotR * Math.cos(info.angle)
        const dy = (info.node.y || 0) + info.dotR * Math.sin(info.angle)
        d3.select(this).attr('cx', dx).attr('cy', dy)
      })
      g.selectAll('.char-dot-label').each(function(d, i) {
        const info = charDotData[i]
        if (!info) return
        const dx = (info.node.x || 0) + info.dotR * Math.cos(info.angle)
        const dy = (info.node.y || 0) + info.dotR * Math.sin(info.angle)
        d3.select(this).attr('x', dx).attr('y', dy + 1.5)
      })
    })
  }

  if (loading) return <LoadingState text="加载地图..." />

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/40 backdrop-blur-sm shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="map" size={16} /> 地点图</h3>
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
              <span className="w-3 h-0.5" style={{ background: s.color }}></span>
              {type}
            </span>
          ))}
        </div>
      </div>

      {/* 4D identity banner */}
      <div className="px-6 py-2 bg-gradient-to-r from-emerald-950/30 to-green-950/20 border-b border-emerald-900/30">
        <div className="flex items-center gap-3 text-[10px]">
          <span className="text-emerald-400 font-medium flex items-center gap-1">
            <Icon name="map-pin" size={12} /> 空间维度
          </span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-500">知识库 4D 图谱的空间侧面——拖拽节点 · 滚轮缩放 · 点击查看详情</span>
        </div>
      </div>

      <div className="flex-1 flex">
        <div ref={containerRef} className="flex-1 relative overflow-hidden bg-zinc-950/60">
          <svg ref={svgRef} className="w-full h-full" />
        </div>

        {selected && (
          <div className="w-56 border-l border-zinc-800 bg-zinc-900/60 backdrop-blur-sm p-4 shrink-0 overflow-y-auto">
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
      {/* Time-aware character count badge */}
      {timeMap && Object.keys(timeMap.characters_at_locations || {}).length > 0 && (
        <div className="px-4 py-1.5 border-t border-zinc-800 bg-zinc-900/40 backdrop-blur-sm shrink-0">
          <span className="text-[10px] text-blue-400 flex items-center gap-1">
            <Icon name="clock" size={10} /> T={selectedTimeOrder} ·
            {Object.values(timeMap.characters_at_locations as Record<string, any>).reduce((acc: number, loc: any) => acc + (loc.characters?.length || 0), 0)} 个角色分布于
            {Object.keys(timeMap.characters_at_locations).length} 个地点（色点标记于地图上）
          </span>
        </div>
      )}
    </div>
  )
}
