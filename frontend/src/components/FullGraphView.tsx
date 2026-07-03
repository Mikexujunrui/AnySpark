import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import * as d3 from 'd3'
import { useResizeObserver } from '../hooks/useResizeObserver'
import { useRefreshKey, useSelectedTimeOrder, setTimeOrder } from '../store'
import Icon from './ui/Icon'

const NODE_STYLES: Record<string, { color: string; glow: string; r: number; label: string }> = {
  character:     { color: '#a78bfa', glow: '#7c3aed', r: 8, label: '角色' },
  location:      { color: '#34d399', glow: '#059669', r: 6, label: '地点' },
  item:          { color: '#fbbf24', glow: '#d97706', r: 4, label: '物品' },
  skill:         { color: '#a3e635', glow: '#65a30d', r: 5, label: '技能/功法' },
  organization:  { color: '#60a5fa', glow: '#2563eb', r: 5, label: '组织' },
  race:          { color: '#d8b4fe', glow: '#9333ea', r: 4, label: '种族' },
  concept:       { color: '#fde047', glow: '#ca8a04', r: 4, label: '概念' },
  event:         { color: '#f87171', glow: '#dc2626', r: 4, label: '事件' },
  timeline:      { color: '#22d3ee', glow: '#0891b2', r: 8, label: '时间线' },
  foreshadow:    { color: '#fb7185', glow: '#e11d48', r: 4, label: '伏笔' },
  snapshot:      { color: '#a1a1aa', glow: '#52525b', r: 3, label: '阶段' },
  unknown:       { color: '#71717a', glow: '#3f3f46', r: 4, label: '未知' },
}

const EDGE_STYLES: Record<string, { color: string; opacity: number; width: number }> = {
  KNOWS:           { color: '#a78bfa', opacity: 0.2, width: 1 },
  ALLY:            { color: '#34d399', opacity: 0.25, width: 1.2 },
  FAMILY:          { color: '#fbbf24', opacity: 0.25, width: 1.2 },
  ANTAGONIST:      { color: '#f87171', opacity: 0.3, width: 1.2 },
  ROMANTIC:        { color: '#f472b6', opacity: 0.25, width: 1.2 },
  LOVES:           { color: '#f9a8d4', opacity: 0.2, width: 1 },
  MENTOR_OF:       { color: '#c4b5fd', opacity: 0.25, width: 1.2 },
  MASTER_OF:       { color: '#a78bfa', opacity: 0.2, width: 1 },
  KILLED:          { color: '#ef4444', opacity: 0.35, width: 1.5 },
  SAVED:           { color: '#34d399', opacity: 0.25, width: 1.2 },
  BELONGS_TO:      { color: '#818cf8', opacity: 0.12, width: 0.8 },
  LOCATED_AT:      { color: '#34d399', opacity: 0.12, width: 0.8 },
  OWNS:            { color: '#fbbf24', opacity: 0.12, width: 0.8 },
  CAUSES:          { color: '#fb923c', opacity: 0.2, width: 1 },
  BEFORE:          { color: '#22d3ee', opacity: 0.15, width: 0.8 },
  AFTER:           { color: '#22d3ee', opacity: 0.15, width: 0.8 },
  FORESHADOWS:     { color: '#fb7185', opacity: 0.2, width: 0.8 },
  RESOLVES:        { color: '#34d399', opacity: 0.2, width: 0.8 },
  PARTICIPATES_IN: { color: '#c084fc', opacity: 0.15, width: 0.8 },
  TIMELINE_INVOLVES: { color: '#22d3ee', opacity: 0.1, width: 0.6 },
  FORESHADOW_INVOLVES: { color: '#fb7185', opacity: 0.1, width: 0.6 },
  HAS_PHASE:       { color: '#52525b', opacity: 0.06, width: 0.5 },
  default:         { color: '#52525b', opacity: 0.12, width: 0.8 },
}

interface GraphData {
  nodes: { id: string; name: string; type: string; data?: any }[]
  edges: { from: string; to: string; type: string }[]
  stats: { node_count: number; edge_count: number }
}

export default function FullGraphView({ bookId }: { bookId: string }) {
  const refreshKey = useRefreshKey()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dimensions = useResizeObserver(containerRef)
  const simRef = useRef<d3.Simulation<any, any> | null>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<any>(null)
  // Search & Filter
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<string[]>([])
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<string[]>([])
  // Global time state from store (replaces local selectedTimelineOrder)
  const selectedTimeOrder = useSelectedTimeOrder()
  // Show/hide snapshot nodes in the graph (default: hidden)
  const [showSnapshots, setShowSnapshots] = useState(false)
  // Edge label toggle (default: hidden)
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)
  // Relationship creation mode
  const [createRelMode, setCreateRelMode] = useState(false)
  const [relSourceNode, setRelSourceNode] = useState<any>(null)
  const [showRelModal, setShowRelModal] = useState(false)
  const [relTargetNode, setRelTargetNode] = useState<any>(null)
  const [relType, setRelType] = useState('KNOWS')

  useEffect(() => { loadData() }, [bookId, refreshKey])

  // Always load full graph — time filtering is now visual, not data-level
  async function loadData() {
    try {
      const res = await fetch(`/api/books/${bookId}/graph/full`)
      if (res.ok) {
        const graphData = await res.json()
        setData(graphData)
      }
    } catch (e) { console.error('Full graph fetch failed:', e) }
    setLoading(false)
  }

  const typeCounts = useMemo(() => {
    if (!data) return []
    const c: Record<string, number> = {}
    ;(data.nodes || []).forEach(n => { c[n.type] = (c[n.type] || 0) + 1 })
    return Object.entries(c).sort((a, b) => b[1] - a[1])
  }, [data])

  // Extract unique edge types
  const edgeTypes = useMemo(() => {
    if (!data) return []
    const types = new Set((data.edges || []).map(e => e.type))
    return Array.from(types).sort()
  }, [data])

  // Filter nodes and edges based on search, type filters, and time filter
  const filteredData = useMemo(() => {
    if (!data) return null
    let nodes = data.nodes || []
    let edges = data.edges || []

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      nodes = nodes.filter(n => 
        n.name.toLowerCase().includes(q) || 
        n.type.toLowerCase().includes(q)
      )
    }

    // Type filter
    if (typeFilter.length > 0) {
      nodes = nodes.filter(n => typeFilter.includes(n.type))
    }

    // Edge type filter
    if (edgeTypeFilter.length > 0) {
      edges = edges.filter(e => edgeTypeFilter.includes(e.type))
    }

    // Snapshot toggle: hide snapshots by default
    if (!showSnapshots) {
      nodes = nodes.filter(n => n.type !== 'snapshot')
    }

    // Only keep edges where both source and target are in filtered nodes
    const nodeIds = new Set(nodes.map(n => n.id))
    edges = edges.filter(e => nodeIds.has(e.from) && nodeIds.has(e.to))

    return { nodes, edges, stats: { node_count: nodes.length, edge_count: edges.length } }
  }, [data, searchQuery, typeFilter, edgeTypeFilter, showSnapshots])

  useEffect(() => {
    if (!filteredData || !dimensions || dimensions.w < 50) return
    renderGraph()
    return () => { if (simRef.current) simRef.current.stop() }
  }, [filteredData, dimensions, selectedTimeOrder, showEdgeLabels])

  function renderGraph() {
    if (!filteredData || !svgRef.current) return
    if (simRef.current) simRef.current.stop()
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    const { w, h } = dimensions
    svg.attr('width', w).attr('height', h)

    const g = svg.append('g')
    const zoom = d3.zoom().scaleExtent([0.1, 8]).on('zoom', e => g.attr('transform', e.transform))
    svg.call(zoom)

    const nodes: any[] = (filteredData.nodes || []).map(n => ({ ...n }))
    const links: any[] = (filteredData.edges || []).map(e => ({ source: e.from, target: e.to, type: e.type }))
    if (nodes.length === 0) return

    const cx = w / 2, cy = h / 2

    // ── Type-based radial partition: each type gets a sector ──
    const sectorRadius = Math.min(w, h) * 0.22
    const typeList = Object.keys(NODE_STYLES)
    const typeTargets: Record<string, {x: number, y: number, angle: number}> = {}
    typeList.forEach((type, i) => {
      const angle = (i / typeList.length) * 2 * Math.PI - Math.PI / 2
      typeTargets[type] = {
        x: cx + sectorRadius * Math.cos(angle),
        y: cy + sectorRadius * Math.sin(angle),
        angle,
      }
    })

    // Initial position by type sector
    nodes.forEach(n => {
      const target = typeTargets[n.type] || typeTargets.unknown
      const jitter = 0.35
      n.x = target.x + (Math.random() - 0.5) * sectorRadius * jitter
      n.y = target.y + (Math.random() - 0.5) * sectorRadius * jitter
    })

    // ── Importance: degree-based grading ──
    const degreeMap: Record<string, number> = {}
    links.forEach(l => {
      const sid = typeof l.source === 'string' ? l.source : (l.source as any).id
      const tid = typeof l.target === 'string' ? l.target : (l.target as any).id
      if (sid) degreeMap[sid] = (degreeMap[sid] || 0) + 1
      if (tid) degreeMap[tid] = (degreeMap[tid] || 0) + 1
    })
    const maxDegree = Math.max(...Object.values(degreeMap), 1)

    // ── Draw faint sector labels ──
    typeList.forEach(type => {
      if (!nodes.some(n => n.type === type)) return
      const target = typeTargets[type]
      const s = NODE_STYLES[type]
      if (!s) return
      g.append('text')
        .attr('x', cx + (sectorRadius + 35) * Math.cos(target.angle))
        .attr('y', cy + (sectorRadius + 35) * Math.sin(target.angle))
        .attr('text-anchor', 'middle').attr('font-size', 11)
        .attr('fill', s.color).attr('opacity', 0.2)
        .attr('font-weight', 600).attr('pointer-events', 'none')
        .text(s.label)
    })

    const n = nodes.length
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(d => {
        const t = (d as any).type
        return t.includes('INVOLVES') || t === 'HAS_PHASE' ? 25 : 60
      }).strength(0.05))
      .force('charge', d3.forceManyBody().strength(-400).distanceMax(Math.max(w, h)))
      .force('x', d3.forceX((d: any) => (typeTargets[d.type] || typeTargets.unknown).x).strength(0.08))
      .force('y', d3.forceY((d: any) => (typeTargets[d.type] || typeTargets.unknown).y).strength(0.08))
      .force('collision', d3.forceCollide().radius((d: any) => (NODE_STYLES[d.type]?.r || 4) + 12).strength(0.7))
      .velocityDecay(0.4)
    simRef.current = sim

    // ── Multi-edge detection: group links by (source, target) pair ──
    const pairKey = (a: string, b: string) => a < b ? `${a}|${b}` : `${b}|${a}`
    const pairCounts: Record<string, number> = {}
    links.forEach(l => {
      const key = pairKey((l as any).source.id || l.source, (l as any).target.id || l.target)
      pairCounts[key] = (pairCounts[key] || 0) + 1
    })
    const pairIndex: Record<string, number> = {}

    // Edges grouped by type
    const edgeGroups: Record<string, any[]> = {}
    links.forEach(l => {
      const t = (l as any).type in EDGE_STYLES ? (l as any).type : 'default'
      ;(edgeGroups[t] ||= []).push(l)
    })

    function edgePath(d: any) {
      const sid = (d.source as any).id || d.source
      const tid = (d.target as any).id || d.target
      const sx = (d.source as any).x || d.source.x, sy = (d.source as any).y || d.source.y
      const tx = (d.target as any).x || d.target.x, ty = (d.target as any).y || d.target.y

      // Self-loop: render as circular arc
      if (sid === tid) {
        const key = pairKey(sid, tid)
        pairIndex[key] = (pairIndex[key] || 0) + 1
        const idx = pairIndex[key] - 1
        const r = 20 + idx * 8
        const angle = ((idx * 60) % 360) * (Math.PI / 180)
        const cx = sx + r * Math.cos(angle)
        const cy = sy - r * Math.sin(angle)
        return `M${sx},${sy} A${r},${r} 0 1,1 ${cx},${cy}`
      }

      // Multi-edge: quadratic Bezier with varying curvature
      const key = pairKey(sid, tid)
      const total = pairCounts[key] || 1
      pairIndex[key] = (pairIndex[key] || 0) + 1
      const idx = pairIndex[key] - 1
      const mx = (sx + tx) / 2
      const my = (sy + ty) / 2
      const dx = tx - sx
      const dy = ty - sy
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (total <= 1) {
        // Single edge: gentle arc
        const dr = dist * 2.5
        return `M${sx},${sy} A${dr},${dr} 0 0,1 ${tx},${ty}`
      }

      // Multiple edges: offset the control point perpendicular to the line
      const offset = (idx - (total - 1) / 2) * 20
      const nx = -dy / (dist || 1)
      const ny = dx / (dist || 1)
      const cpx = mx + nx * offset
      const cpy = my + ny * offset
      return `M${sx},${sy} Q${cpx},${cpy} ${tx},${ty}`
    }

    // Reset pairIndex before each type group
    Object.entries(edgeGroups).forEach(([type, groupLinks]) => {
      const s = EDGE_STYLES[type] || EDGE_STYLES.default
      // Reset pair index for this group
      Object.keys(pairIndex).forEach(k => delete pairIndex[k])
      const edgeG = g.append('g')
      edgeG.selectAll('path').data(groupLinks).join('path')
        .attr('stroke', s.color).attr('stroke-width', s.width)
        .attr('stroke-opacity', s.opacity).attr('fill', 'none')
        .attr('d', edgePath)
        .attr('marker-end', (d: any) => {
          const sid = (d.source as any).id || d.source
          const tid = (d.target as any).id || d.target
          return sid === tid ? '' : 'url(#arrowhead)'
        })
      // Edge labels (conditional)
      if (showEdgeLabels) {
        edgeG.selectAll('text').data(groupLinks).join('text')
          .text((d: any) => (d as any).type.replace(/_/g, ' '))
          .attr('font-size', 7).attr('fill', '#71717a')
          .attr('text-anchor', 'middle').attr('dy', -3)
          .attr('pointer-events', 'none')
          .attr('x', (d: any) => {
            const sx = (d.source as any).x || d.source.x
            const tx = (d.target as any).x || d.target.x
            return (sx + tx) / 2
          })
          .attr('y', (d: any) => {
            const sy = (d.source as any).y || d.source.y
            const ty = (d.target as any).y || d.target.y
            return (sy + ty) / 2
          })
      }
    })

    // Nodes with glow
    const nodeG = g.append('g').selectAll('g').data(nodes).join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
        .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))
      .on('click', (e, d) => { 
        e.stopPropagation()
        // Relationship creation mode
        if (createRelMode) {
          if (!relSourceNode) {
            setRelSourceNode(d)
          } else if (relSourceNode.id !== d.id) {
            setRelTargetNode(d)
            setShowRelModal(true)
          }
        } else if (d.type === 'timeline') {
          // Timeline node clicked: sync to global time axis
          const to = d.data?.time_order
          if (to !== undefined && to !== null) {
            setTimeOrder(to)
          }
        } else {
          setSelectedNode(d)
        }
      })

    nodeG.each(function(d: any) {
      const s = NODE_STYLES[d.type] || NODE_STYLES.unknown
      const el = d3.select(this)

      // ── Importance grading: scale radius & opacity by degree ──
      const deg = degreeMap[d.id] || 0
      const importance = deg / maxDegree  // 0 to 1
      const scaledR = s.r * (0.6 + importance * 0.4)  // 60%–100% of base radius

      // Time-aware visual filtering: dim timeline nodes after selectedTimeOrder
      let nodeOpacity = isFinite(importance) ? 0.35 + importance * 0.65 : 0.5
      let isCurrentTime = false
      if (d.type === 'timeline' && selectedTimeOrder > 0) {
        const nodeTimeOrder = d.data?.time_order || 0
        if (nodeTimeOrder > selectedTimeOrder) {
          nodeOpacity = 0.15  // Future events: dimmed
        } else if (nodeTimeOrder === selectedTimeOrder) {
          isCurrentTime = true  // Current time point: highlighted
        }
      }
      el.attr('opacity', nodeOpacity)

      // Main node (scaled by importance)
      el.append('circle').attr('r', scaledR).attr('fill', s.color)
        .attr('stroke', isCurrentTime ? '#22d3ee' : '#18181b')
        .attr('stroke-width', isCurrentTime ? 3 : (d.type === 'character' ? 2 : 1))
      // Highlight ring for current time node
      if (isCurrentTime) {
        el.append('circle').attr('r', scaledR + 5).attr('fill', 'none')
          .attr('stroke', '#22d3ee').attr('stroke-width', 1.5).attr('opacity', 0.6)
          .attr('stroke-dasharray', '3 3')
      }
      // Label: show for important nodes (importance > 0.1 or base r >= 5)
      if (scaledR >= 4.5 || importance > 0.1) {
        const labelOpacity = 0.4 + importance * 0.6
        el.append('text').text(d.name?.length > 8 ? d.name.slice(0,7)+'…' : d.name)
          .attr('font-size', scaledR >= 7 ? 10 : 8).attr('font-weight', importance > 0.3 ? 600 : 400)
          .attr('fill', d.type === 'character' ? '#e4e4e7' : '#a1a1aa')
          .attr('opacity', labelOpacity)
          .attr('text-anchor', 'middle').attr('dy', -(scaledR + 6))
          .attr('pointer-events', 'none')
      }
    })

    sim.on('tick', () => {
      Object.entries(edgeGroups).forEach(([type, groupLinks]) => {
        g.selectAll('path').attr('d', edgePath)
      })
      nodeG.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
    })
  }

  const nodeCount = filteredData?.stats?.node_count || 0
  const edgeCount = filteredData?.stats?.edge_count || 0
  const totalNodes = data?.stats?.node_count || 0
  const totalEdges = data?.stats?.edge_count || 0

  // Export functions
  const exportJSON = useCallback(() => {
    if (!filteredData) return
    const blob = new Blob([JSON.stringify(filteredData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `graph-${bookId}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [filteredData, bookId])

  const exportPNG = useCallback(() => {
    if (!svgRef.current) return
    const svgData = new XMLSerializer().serializeToString(svgRef.current)
    const canvas = document.createElement('canvas')
    canvas.width = 1920
    canvas.height = 1080
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const img = new Image()
    img.onload = () => {
      ctx.fillStyle = '#09090b'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0)
      canvas.toBlob(blob => {
        if (!blob) return
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `graph-${bookId}-${Date.now()}.png`
        a.click()
        URL.revokeObjectURL(url)
      })
    }
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)))
  }, [bookId])

  // Create relationship
  const handleCreateRelation = async () => {
    if (!relSourceNode || !relTargetNode) return
    try {
      const res = await fetch(`/api/books/${bookId}/knowledge/relation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_id: relSourceNode.id,
          to_id: relTargetNode.id,
          rel_type: relType,
        }),
      })
      if (res.ok) {
        setShowRelModal(false)
        setRelSourceNode(null)
        setRelTargetNode(null)
        setRelType('KNOWS')
        loadData() // Refresh graph
      }
    } catch (e) {
      console.error('Failed to create relation:', e)
    }
  }

  if (loading) return <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">加载全书图谱中...</div>
  if (!data || totalNodes === 0) return <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">图谱为空 — 请先添加角色、地点等实体</div>

  return (
    <div className="flex-1 w-full flex flex-col overflow-hidden min-h-0">
      {/* Toolbar — all controls in one row, no floating overlaps */}
      <div className="shrink-0 flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-900/40 backdrop-blur-sm flex-wrap">
        {/* Search */}
        <div className="flex items-center gap-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
          <Icon name="search" size={12} />
          <input
            type="text"
            placeholder="搜索节点..."
            className="bg-transparent text-xs text-zinc-300 w-28 outline-none placeholder:text-zinc-600"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Type filter */}
        <div className="flex items-center gap-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
          <Icon name="filter" size={12} />
          {Object.entries(NODE_STYLES).map(([type, s]) => (
            <button
              key={type}
              onClick={() => {
                setTypeFilter(prev => 
                  prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
                )
              }}
              className={`w-3 h-3 rounded-full transition-opacity ${typeFilter.length === 0 || typeFilter.includes(type) ? '' : 'opacity-30'}`}
              style={{ background: s.color }}
              title={`${s.label} (${typeCounts.find(([t]) => t === type)?.[1] || 0})`}
            />
          ))}
        </div>

        {/* Edge type filter */}
        {edgeTypes.length > 0 && (
          <div className="flex items-center gap-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 max-w-60 overflow-x-auto">
            <Icon name="git-branch" size={12} />
            {edgeTypes.slice(0, 6).map(type => (
              <button
                key={type}
                onClick={() => {
                  setEdgeTypeFilter(prev => 
                    prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
                  )
                }}
                className={`text-[9px] px-1 py-0.5 rounded border whitespace-nowrap transition-opacity ${
                  edgeTypeFilter.length === 0 || edgeTypeFilter.includes(type)
                    ? 'border-zinc-600 text-zinc-400'
                    : 'border-zinc-800 text-zinc-700 opacity-40'
                }`}
              >
                {type.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        )}

        {/* Create relation mode */}
        <button
          onClick={() => {
            setCreateRelMode(!createRelMode)
            setRelSourceNode(null)
          }}
          className={`text-[10px] px-2 py-1 rounded border flex items-center gap-1 ${
            createRelMode
              ? 'bg-green-600/20 border-green-600 text-green-400'
              : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}
        >
          <Icon name="link" size={12} />
          {createRelMode ? (relSourceNode ? '选目标...' : '选源...') : '建关系'}
        </button>

        {/* Edge label toggle */}
        <button
          onClick={() => setShowEdgeLabels(!showEdgeLabels)}
          className={`text-[10px] px-2 py-1 rounded border flex items-center gap-1 ${
            showEdgeLabels
              ? 'bg-zinc-700/50 border-zinc-600 text-zinc-300'
              : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}
          title="显示/隐藏边标签"
        >
          <Icon name="tag" size={12} />
          标签
        </button>

        {/* Snapshot toggle */}
        <button
          onClick={() => setShowSnapshots(!showSnapshots)}
          className={`text-[10px] px-2 py-1 rounded border flex items-center gap-1 ${
            showSnapshots
              ? 'bg-zinc-700/50 border-zinc-600 text-zinc-300'
              : 'bg-zinc-800 border-zinc-700 text-zinc-500'
          }`}
          title="显示/隐藏角色阶段快照"
        >
          <Icon name="layers" size={12} />
          阶段
        </button>

        {/* Stats + Export — pushed to the right, no overlap with legend */}
        <div className="ml-auto flex items-center gap-2 shrink-0">
          <span className="text-[10px] text-zinc-500 whitespace-nowrap">
            {nodeCount} / {totalNodes} 节点 · {edgeCount} / {totalEdges} 边
          </span>
          {selectedTimeOrder > 0 && (
            <span className="text-[10px] text-cyan-400 bg-cyan-950/40 border border-cyan-800/50 px-1.5 py-0.5 rounded whitespace-nowrap">
              T={selectedTimeOrder}
            </span>
          )}
          <div className="flex items-center gap-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1">
            <button onClick={exportJSON} className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-0.5" title="导出JSON">
              <Icon name="download" size={12} /> JSON
            </button>
            <button onClick={exportPNG} className="text-[10px] text-zinc-500 hover:text-zinc-300 flex items-center gap-0.5" title="导出PNG">
              <Icon name="image" size={12} /> PNG
            </button>
          </div>
        </div>
      </div>

      {/* Main area: graph + right sidebar */}
      <div className="flex-1 flex min-h-0">
        {/* Graph canvas */}
        <div ref={containerRef} className="flex-1 relative bg-zinc-950 min-h-0">
          <svg ref={svgRef} className="w-full h-full" />
        </div>

        {/* Right sidebar: legend + node detail (no floating, no overlap) */}
        <div className="w-48 shrink-0 border-l border-zinc-800 bg-zinc-900/30 backdrop-blur-sm overflow-y-auto flex flex-col">
          {/* Legend */}
          <div className="p-2 border-b border-zinc-800">
            <div className="text-[10px] text-zinc-500 mb-1.5 flex items-center gap-1">
              <Icon name="list" size={10} /> 图例
            </div>
            {typeCounts.map(([type, count]) => {
              const s = NODE_STYLES[type]
              if (!s) return null
              return (
                <div key={type} className="flex items-center gap-1.5 text-[9px] py-0.5">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
                  <span className="text-zinc-500">{s.label}</span>
                  <span className="text-zinc-300 ml-auto">{count}</span>
                </div>
              )
            })}
          </div>

          {/* Selected node detail */}
          {selectedNode && !showRelModal && (
            <div className="p-3 border-b border-zinc-800">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-zinc-200 truncate">{selectedNode.name}</h4>
                <button onClick={() => setSelectedNode(null)} className="text-zinc-600 hover:text-zinc-300 text-xs shrink-0 ml-1">
                  <Icon name="x" size={12} />
                </button>
              </div>
              <p className="text-[10px] text-zinc-500 mb-1">类型: <span className="text-zinc-300">{NODE_STYLES[selectedNode.type]?.label || selectedNode.type}</span></p>
              {selectedNode.data && Object.entries(selectedNode.data).slice(0, 4).map(([k, v]: [string, any]) => (
                <p key={k} className="text-[10px] text-zinc-500 truncate">{k}: <span className="text-zinc-300">{typeof v === 'string' ? v.slice(0,30) : String(v).slice(0,30)}</span></p>
              ))}
            </div>
          )}

          {/* Time filter status */}
          {selectedTimeOrder > 0 && (
            <div className="p-2 border-b border-zinc-800">
              <div className="text-[10px] text-cyan-400 flex items-center gap-1 mb-1">
                <Icon name="clock" size={10} /> 时间过滤已启用
              </div>
              <p className="text-[9px] text-zinc-600">T={selectedTimeOrder} 之后的<br/>时间线节点已暗淡</p>
            </div>
          )}
        </div>
      </div>

      {/* Bottom hint bar */}
      <div className="shrink-0 px-4 py-1.5 border-t border-zinc-800 text-[10px] text-zinc-600 flex items-center justify-between">
        <span>拖拽节点 · 滚轮缩放 · 点击时间线节点同步时间轴 · 发光节点按类型着色</span>
        {createRelMode && <span className="text-green-400 animate-pulse">关系创建模式: {relSourceNode ? `已选"${relSourceNode.name}" → 点击目标节点` : '点击源节点'}</span>}
      </div>

      {/* Create relation modal — fixed to cover full screen */}
      {showRelModal && relSourceNode && relTargetNode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-4 w-72">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-zinc-200">创建关系</h4>
              <button onClick={() => { setShowRelModal(false); setRelSourceNode(null); setRelTargetNode(null) }} className="text-zinc-600 hover:text-zinc-300"><Icon name="x" size={14} /></button>
            </div>
            <div className="space-y-2 mb-4">
              <div className="flex items-center gap-2 text-xs">
                <span className="px-2 py-0.5 rounded bg-purple-600/20 text-purple-400">{relSourceNode.name}</span>
                <span className="text-zinc-600">→</span>
                <span className="px-2 py-0.5 rounded bg-zinc-700 text-zinc-300">{relTargetNode.name}</span>
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">关系类型</label>
                <select
                  value={relType}
                  onChange={e => setRelType(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 outline-none focus:border-blue-500"
                >
                  <option value="KNOWS">KNOWS 认识</option>
                  <option value="ALLY">ALLY 盟友</option>
                  <option value="FAMILY">FAMILY 家人</option>
                  <option value="ROMANTIC">ROMANTIC 恋人</option>
                  <option value="LOVES">LOVES 暗恋</option>
                  <option value="ANTAGONIST">ANTAGONIST 敌对</option>
                  <option value="MENTOR_OF">MENTOR_OF 师徒</option>
                  <option value="MASTER_OF">MASTER_OF 掌控</option>
                  <option value="KILLED">KILLED 杀害</option>
                  <option value="SAVED">SAVED 拯救</option>
                  <option value="OWNS">OWNS 拥有</option>
                  <option value="BELONGS_TO">BELONGS_TO 属于</option>
                  <option value="LOCATED_AT">LOCATED_AT 位于</option>
                  <option value="CAUSES">CAUSES 导致</option>
                  <option value="BEFORE">BEFORE 之前</option>
                  <option value="AFTER">AFTER 之后</option>
                  <option value="FORESHADOWS">FORESHADOWS 伏笔</option>
                  <option value="RESOLVES">RESOLVES 解决</option>
                  <option value="PARTICIPATES_IN">PARTICIPATES_IN 参与</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => { setShowRelModal(false); setRelSourceNode(null); setRelTargetNode(null) }}
                className="flex-1 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-400 hover:text-zinc-300"
              >
                取消
              </button>
              <button
                onClick={handleCreateRelation}
                className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white"
              >
                确认创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}