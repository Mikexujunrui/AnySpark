// FullGraphView — 知识图谱可视化（S153 重写：d3-force 布局 + 全图/聚焦子图双模式）
//
// 数据：
//   - 全图：GET /api/graph/entities + /api/graph/relations（按 book_id）
//   - 聚焦子图：GET /api/graph/network?entity_id=&depth=&book_id=（ego-network，S153 新增）
// 能力：
//   - d3-force 力导向布局（替代 S75 手写 150 迭代版）：link/charge/collide/center
//   - 缩放（按钮+滚轮）/ 平移 / 拖拽节点固定（重置清空）
//   - 搜索（名称/别名/类型/描述）+ 类型点击过滤（图例 chips）
//   - 图例（类型色板+计数）、节点类型图标、边方向箭头、关系标签（hover/选中/开关）
//   - hover 高亮 1 度邻居；选中实体详情卡片 + "聚焦此实体" → 子视图
//   - 聚焦子视图：中心锚定画布中心 + 1/2 度逐步展开；点邻居换中心；返回全图
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon'
import { fetchGraphNetwork } from '../api/graph'
import type { GraphEntity, GraphRelation } from '../api/graph'

interface Pos { x: number; y: number }
interface SimNode extends d3.SimulationNodeDatum {
  id: string
  name: string
  entity_type: string
  weight: number
}
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string
  rel_type: string
}

const TYPE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  '角色': { fill: 'rgba(59,130,246,0.25)', stroke: '#3b82f6', text: '#93c5fd' },
  '物件': { fill: 'rgba(245,158,11,0.2)', stroke: '#f59e0b', text: '#fcd34d' },
  '地点': { fill: 'rgba(16,185,129,0.2)', stroke: '#10b981', text: '#6ee7b7' },
  '事件': { fill: 'rgba(239,68,68,0.2)', stroke: '#ef4444', text: '#fca5a5' },
  '设定': { fill: 'rgba(168,85,247,0.2)', stroke: '#a855f7', text: '#d8b4fe' },
  '组织': { fill: 'rgba(14,165,233,0.2)', stroke: '#0ea5e9', text: '#7dd3fc' },
}

const TYPE_ICONS: Record<string, string> = {
  '角色': 'user', '物件': 'star', '地点': 'map-pin', '事件': 'zap', '设定': 'lightbulb', '组织': 'building',
}

function typeStyle(t: string) {
  return TYPE_COLORS[t] || { fill: 'rgba(39,39,42,0.8)', stroke: '#71717a', text: '#a1a1aa' }
}

interface FocusState {
  centerId: string
  centerName: string
  depth: number
  entities: GraphEntity[]
  relations: GraphRelation[]
}

const NODE_W = 132
const NODE_H = 38

export default function FullGraphView({ bookId }: { bookId: string }) {
  const [entities, setEntities] = useState<GraphEntity[]>([])
  const [relations, setRelations] = useState<GraphRelation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<FocusState | null>(null)
  const [focusLoading, setFocusLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set())
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)
  const [selected, setSelected] = useState<GraphEntity | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [hoveredRel, setHoveredRel] = useState<string | null>(null)
  const [zoom, setZoom] = useState(0.85)
  const [pan, setPan] = useState<Pos>({ x: 20, y: 20 })
  const [positions, setPositions] = useState<Record<string, Pos>>({})
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 900, h: 600 })
  const [resetKey, setResetKey] = useState(0)

  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const panRef = useRef<{ x0: number; y0: number; px: number; py: number } | null>(null)
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null)
  const simNodes = useRef<Map<string, SimNode>>(new Map())
  const fixedRef = useRef<Map<string, Pos>>(new Map())
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null)
  const posRef = useRef<Record<string, Pos>>({})

  // ── 全图加载 ──
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFocus(null)
    setSelected(null)
    setSearchQuery('')
    setTypeFilter(new Set())
    setPositions({})
    posRef.current = {}
    fixedRef.current = new Map()
    Promise.all([
      fetch(`/api/graph/entities?book_id=${bookId || 'main'}`).then(r => r.json()),
      fetch(`/api/graph/relations?book_id=${bookId || 'main'}`).then(r => r.json()),
    ]).then(([e, r]) => {
      if (cancelled) return
      setEntities(Array.isArray(e) ? e : [])
      setRelations(Array.isArray(r) ? r : [])
      setLoading(false)
    }).catch(() => {
      if (!cancelled) { setError('加载图谱失败'); setLoading(false) }
    })
    return () => { cancelled = true }
  }, [bookId])

  // ── 容器尺寸 ──
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect
      if (r.width > 50 && r.height > 50) setSize({ w: r.width, h: r.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ── 当前可视数据（全图过滤 or 聚焦子图）──
  const view = useMemo(() => {
    if (focus) return { entities: focus.entities, relations: focus.relations }
    let es = entities
    if (typeFilter.size > 0) es = es.filter(e => typeFilter.has(e.entity_type || ''))
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      es = es.filter(e =>
        (e.name || '').toLowerCase().includes(q) ||
        (e.aliases || []).some(a => a.toLowerCase().includes(q)) ||
        (e.entity_type || '').toLowerCase().includes(q) ||
        (e.description || '').toLowerCase().includes(q),
      )
    }
    const ids = new Set(es.map(e => e.id))
    const rs = relations.filter(r => ids.has(r.from_id) && ids.has(r.to_id))
    return { entities: es, relations: rs }
  }, [entities, relations, focus, typeFilter, searchQuery])

  // ── d3-force 布局（数据/尺寸/重置变化时重建；保留固定点与旧位置收敛）──
  useEffect(() => {
    simRef.current?.stop()
    simNodes.current = new Map()
    const prev = posRef.current
    const nodes: SimNode[] = view.entities.map(e => {
      const n: SimNode = { id: e.id, name: e.name, entity_type: e.entity_type || '', weight: e.weight || 0 }
      const fixed = fixedRef.current.get(e.id)
      if (fixed) { n.x = fixed.x; n.y = fixed.y; n.fx = fixed.x; n.fy = fixed.y }
      else if (prev[e.id]) { n.x = prev[e.id].x; n.y = prev[e.id].y }
      simNodes.current.set(e.id, n)
      return n
    })
    const ids = new Set(nodes.map(n => n.id))
    const links: SimLink[] = view.relations
      .filter(r => ids.has(r.from_id) && ids.has(r.to_id) && r.from_id !== r.to_id)
      .map(r => ({ id: r.id, rel_type: r.rel_type, source: r.from_id, target: r.to_id }))
    if (nodes.length === 0) { setPositions({}); return }

    const cx = size.w / 2, cy = size.h / 2
    // 聚焦模式：中心实体锚定画布中心
    if (focus) {
      const c = nodes.find(n => n.id === focus.centerId)
      if (c) { c.x = cx; c.y = cy; c.fx = cx; c.fy = cy }
    }

    const sim = d3.forceSimulation<SimNode>(nodes)
      .force('link', d3.forceLink<SimNode, SimLink>(links).id((n: SimNode) => n.id).distance(120).strength(0.5))
      .force('charge', d3.forceManyBody<SimNode>().strength(-420))
      .force('collide', d3.forceCollide<SimNode>(NODE_W / 2 + 14))
      .force('center', d3.forceCenter(cx, cy))
      .force('x', d3.forceX(cx).strength(0.04))
      .force('y', d3.forceY(cy).strength(0.04))
    sim.on('tick', () => {
      const p: Record<string, Pos> = {}
      nodes.forEach(n => { p[n.id] = { x: n.x ?? 0, y: n.y ?? 0 } })
      posRef.current = p
      setPositions(p)
    })
    simRef.current = sim
    return () => { sim.stop() }
  }, [view, size, focus, resetKey])

  // ── 坐标换算 ──
  const toSvgPoint = useCallback((clientX: number, clientY: number): Pos => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return { x: (clientX - rect.left - pan.x) / zoom, y: (clientY - rect.top - pan.y) / zoom }
  }, [pan, zoom])

  // ── 拖拽 / 平移 / 缩放 ──
  const onNodePointerDown = (e: React.PointerEvent, id: string) => {
    e.stopPropagation()
    const n = simNodes.current.get(id)
    if (!n) return
    n.fx = n.x; n.fy = n.y
    dragRef.current = { id, moved: false }
    simRef.current?.alphaTarget(0.3).restart()
  }
  const onNodePointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    const d = dragRef.current
    const n = simNodes.current.get(d.id)
    if (!n) return
    const pt = toSvgPoint(e.clientX, e.clientY)
    if (Math.abs(pt.x - (n.x ?? 0)) > 2 || Math.abs(pt.y - (n.y ?? 0)) > 2) d.moved = true
    n.fx = pt.x; n.fy = pt.y; n.x = pt.x; n.y = pt.y
    fixedRef.current.set(d.id, { x: pt.x, y: pt.y })
    setPositions(prev => ({ ...prev, [d.id]: { x: pt.x, y: pt.y } }))
  }
  const onNodePointerUp = () => {
    if (!dragRef.current) return
    const d = dragRef.current
    dragRef.current = null
    simRef.current?.alphaTarget(0)
    if (!d.moved) {
      const ent = view.entities.find(x => x.id === d.id)
      if (ent) setSelected(ent)
    }
  }
  const onCanvasPointerDown = (e: React.PointerEvent) => {
    panRef.current = { x0: e.clientX, y0: e.clientY, px: pan.x, py: pan.y }
  }
  const onCanvasPointerMove = (e: React.PointerEvent) => {
    if (!panRef.current) return
    const p = panRef.current
    setPan({ x: p.px + (e.clientX - p.x0), y: p.py + (e.clientY - p.y0) })
  }
  const onCanvasPointerUp = () => { panRef.current = null }
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.12 : 0.89
    setZoom(z => Math.min(2.5, Math.max(0.3, z * factor)))
  }

  // ── 聚焦子视图 ──
  const focusOn = useCallback(async (ent: GraphEntity, depth: number) => {
    setFocusLoading(true)
    try {
      const net = await fetchGraphNetwork(ent.id, depth, bookId)
      setFocus({ centerId: ent.id, centerName: ent.name, depth, entities: net.entities, relations: net.relations })
      setSelected(ent)
    } catch {
      // 网络失败保持现状（弱提示由 loading 状态承载）
    }
    setFocusLoading(false)
  }, [bookId])

  const exitFocus = useCallback(() => {
    setFocus(null)
    setSelected(null)
  }, [])

  // ── 高亮集合（hover / 选中）──
  const hoverNeighbors = useMemo(() => {
    if (!hovered) return null
    const s = new Set<string>()
    view.relations.forEach(r => {
      if (r.from_id === hovered) s.add(r.to_id)
      if (r.to_id === hovered) s.add(r.from_id)
    })
    s.add(hovered)
    return s
  }, [hovered, view])

  const selectedRelated = useMemo(() => {
    if (!selected) return null
    const s = new Set<string>()
    view.relations.forEach(r => {
      if (r.from_id === selected.id) s.add(r.to_id)
      if (r.to_id === selected.id) s.add(r.from_id)
    })
    s.add(selected.id)
    return s
  }, [selected, view])

  const selectedRels = selected
    ? view.relations.filter(r => r.from_id === selected.id || r.to_id === selected.id)
    : []

  // 聚焦模式下节点的深度（0=中心 1=一度 2=二度）
  const depthOf = useMemo(() => {
    if (!focus) return null
    const m = new Map<string, number>()
    focus.relations.forEach(r => {
      if (r.from_id === focus.centerId) m.set(r.to_id, 1)
      if (r.to_id === focus.centerId) m.set(r.from_id, 1)
    })
    focus.entities.forEach(e => { if (!m.has(e.id)) m.set(e.id, 2) })
    m.set(focus.centerId, 0)
    return m
  }, [focus])

  // ── 图例（类型统计）──
  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {}
    view.entities.forEach(e => { const t = e.entity_type || '未分类'; c[t] = (c[t] || 0) + 1 })
    return Object.entries(c).sort((a, b) => b[1] - a[1])
  }, [view])

  const toggleType = (t: string) => {
    setTypeFilter(prev => {
      const n = new Set(prev)
      if (n.has(t)) n.delete(t); else n.add(t)
      return n
    })
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-zinc-500 text-sm gap-2">
      <div className="w-5 h-5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
      加载知识图谱...
    </div>
  }
  if (error) return <div className="flex items-center justify-center h-full text-red-400 text-sm">{error}</div>
  if (entities.length === 0) {
    return <div className="flex items-center justify-center h-full text-zinc-600 text-sm">图谱为空——对话或写作时 AI 会自动抽取实体与关系</div>
  }

  const byName: Record<string, GraphEntity> = {}
  view.entities.forEach(e => { byName[e.name] = e })

  const dimBy = (e: GraphEntity): number => {
    if (hovered && hoverNeighbors && !hoverNeighbors.has(e.id)) return 0.18
    if (selected && selectedRelated && !selectedRelated.has(e.id)) return 0.15
    const d = depthOf?.get(e.id)
    if (d === 2) return 0.6
    if (d === 1) return 0.9
    return 1
  }

  return (
    <div className="h-full w-full flex flex-col relative">
      {/* ── 工具条 ── */}
      <div className="h-9 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-1.5 shrink-0 flex-wrap">
        <span className="text-[11px] text-zinc-500 mr-1">图谱视图</span>
        <span className="text-[11px] text-zinc-600">{view.entities.length} 实体 · {view.relations.length} 关系</span>

        {!focus && (
          <div className="flex items-center gap-1.5 ml-2">
            <div className="relative">
              <Icon name="search" size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索实体…"
                className="w-36 bg-zinc-800 border border-zinc-700 rounded pl-7 pr-2 py-0.5 text-[11px] text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
              />
            </div>
            {/* 类型过滤（图例 chips，点击切换） */}
            {typeCounts.map(([t, n]) => (
              <button
                key={t}
                onClick={() => toggleType(t)}
                title={`点击过滤 ${t}`}
                className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] border transition-colors ${typeFilter.has(t) ? 'border-zinc-500 text-zinc-200 bg-zinc-700/50' : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'}`}
              >
                <span className="w-2 h-2 rounded-full" style={{ background: typeStyle(t).stroke }} />
                {t} <span className="text-zinc-600">{n}</span>
              </button>
            ))}
            <button
              onClick={() => setShowEdgeLabels(v => !v)}
              title="显示/隐藏关系标签"
              className={`px-1.5 py-0.5 rounded text-[10px] border ${showEdgeLabels ? 'border-zinc-500 text-zinc-200 bg-zinc-700/50' : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'}`}
            >
              关系标签
            </button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-1 shrink-0">
          <button onClick={() => handleZoomFn(setZoom, 1.25)} className="w-6 h-6 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded text-sm" title="放大">+</button>
          <button onClick={() => handleZoomFn(setZoom, 0.8)} className="w-6 h-6 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded text-sm" title="缩小">−</button>
          <button
            onClick={() => { fixedRef.current = new Map(); posRef.current = {}; setPositions({}); setResetKey(k => k + 1); setZoom(0.85); setPan({ x: 20, y: 20 }) }}
            className="px-2 py-0.5 text-[10px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded" title="重置布局"
          >重置</button>
        </div>
      </div>

      {/* ── 聚焦模式横幅 ── */}
      {focus && (
        <div className="h-8 bg-blue-950/40 border-b border-blue-900/40 flex items-center px-3 gap-2 shrink-0">
          <Icon name="target" size={12} className="text-blue-400" />
          <span className="text-[11px] text-zinc-400">聚焦：</span>
          <span className="text-[12px] font-medium text-blue-300">{focus.centerName}</span>
          <div className="flex items-center gap-0.5 ml-1">
            <button
              onClick={() => focusOn(view.entities.find(e => e.id === focus.centerId)!, 1)}
              className={`px-1.5 py-0.5 rounded text-[10px] ${focus.depth === 1 ? 'bg-blue-600 text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
              title="只显示一度邻居"
            >1 度</button>
            <button
              onClick={() => focusOn(view.entities.find(e => e.id === focus.centerId)!, 2)}
              className={`px-1.5 py-0.5 rounded text-[10px] ${focus.depth >= 2 ? 'bg-blue-600 text-white' : 'text-zinc-400 hover:text-zinc-200'}`}
              title="展开到二度邻居"
            >2 度</button>
          </div>
          <span className="text-[10px] text-zinc-600 ml-1">{view.entities.length} 实体 · {view.relations.length} 关系</span>
          {focusLoading && <span className="text-[10px] text-blue-400 animate-pulse">展开中…</span>}
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={exitFocus}
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-zinc-300 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700"
            >
              <Icon name="arrow-left" size={10} /> 返回全图
            </button>
          </div>
        </div>
      )}

      {/* ── SVG 画布 ── */}
      <div ref={containerRef} className="flex-1 overflow-hidden relative">
        <svg
          ref={svgRef}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          onPointerDown={onCanvasPointerDown}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={onCanvasPointerUp}
          onWheel={onWheel}
        >
          <defs>
            <marker id="graph-arrow-dim" viewBox="0 0 10 10" refX={NODE_W / 2 + 4} refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0L10,5L0,10z" fill="#3f3f46" />
            </marker>
            <marker id="graph-arrow-hi" viewBox="0 0 10 10" refX={NODE_W / 2 + 4} refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0L10,5L0,10z" fill="#f59e0b" />
            </marker>
          </defs>
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* 连线 */}
            {view.relations.map(r => {
              const a = byName[r.from_name]
              const b = byName[r.to_name]
              if (!a || !b || a.id === b.id) return null
              const pa = positions[a.id] ?? { x: 0, y: 0 }
              const pb = positions[b.id] ?? { x: 0, y: 0 }
              const isSel = selected && (selected.id === r.from_id || selected.id === r.to_id)
              const isHover = hoveredRel === r.id
              const isHoverNode = hovered && (r.from_id === hovered || r.to_id === hovered)
              const hi = isSel || isHover || isHoverNode
              const stroke = hi ? '#f59e0b' : '#3f3f46'
              const opacity = selected && !isSel ? 0.12 : hovered && !isHoverNode ? 0.15 : 0.6
              const showLabel = showEdgeLabels || isSel || isHover
              return (
                <g key={r.id} onMouseEnter={() => setHoveredRel(r.id)} onMouseLeave={() => setHoveredRel(null)}>
                  <line
                    x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                    stroke={stroke} strokeWidth={hi ? 2 : 1.1} opacity={opacity}
                    markerEnd={`url(#${hi ? 'graph-arrow-hi' : 'graph-arrow-dim'})`}
                  />
                  {showLabel && (
                    <text
                      x={(pa.x + pb.x) / 2} y={(pa.y + pb.y) / 2 - 6}
                      textAnchor="middle" fontSize="9" fill={stroke} opacity={0.95}
                    >{r.rel_type}</text>
                  )}
                </g>
              )
            })}

            {/* 实体节点 */}
            {view.entities.map(e => {
              const p = positions[e.id] ?? { x: 0, y: 0 }
              const style = typeStyle(e.entity_type || '')
              const isSelected = selected?.id === e.id
              const isCenter = focus?.centerId === e.id
              const isHovered = hovered === e.id
              const opacity = dimBy(e)
              const stroke = isSelected ? '#f59e0b' : isCenter ? '#fbbf24' : style.stroke
              const strokeW = isSelected || isCenter ? 2.2 : 1.2
              return (
                <g
                  key={e.id}
                  transform={`translate(${p.x}, ${p.y})`}
                  opacity={opacity}
                  onPointerDown={ev => onNodePointerDown(ev, e.id)}
                  onPointerMove={onNodePointerMove}
                  onPointerUp={onNodePointerUp}
                  onMouseEnter={() => setHovered(e.id)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <rect
                    x={-NODE_W / 2} y={-NODE_H / 2} width={NODE_W} height={NODE_H} rx={9}
                    fill={style.fill} stroke={stroke} strokeWidth={strokeW}
                    filter={isHovered ? 'brightness(1.35)' : undefined}
                  />
                  <g transform={`translate(${-NODE_W / 2 + 10}, ${-8})`} color={style.text} pointerEvents="none">
                    <Icon name={TYPE_ICONS[e.entity_type || ''] || 'circle'} size={11} />
                  </g>                  <text
                    textAnchor="middle" y={-2} fontSize="11" fill={style.text} fontWeight={isSelected || isCenter ? 600 : 400}
                  >{e.name.length > 10 ? e.name.slice(0, 10) + '…' : e.name}</text>
                  <text textAnchor="middle" y={12} fontSize="8" fill="#71717a">{e.entity_type || ''}</text>
                </g>
              )
            })}
          </g>
        </svg>

        {/* 选中实体详情 */}
        {selected && (
          <div className="absolute top-3 right-3 w-72 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-4 z-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-zinc-200">{selected.name}</span>
              <button onClick={() => setSelected(null)} className="text-zinc-600 hover:text-zinc-300">
                <Icon name="x" size={14} />
              </button>
            </div>
            <div className="flex flex-wrap gap-1 mb-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">{selected.entity_type || '设定'}</span>
              {!focus ? (
                <button
                  onClick={() => focusOn(selected, 1)}
                  className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-blue-600/20 text-blue-300 border border-blue-800 hover:bg-blue-600/30"
                >
                  <Icon name="target" size={9} /> 聚焦此实体
                </button>
              ) : selected.id !== focus.centerId ? (
                <button
                  onClick={() => focusOn(selected, 1)}
                  className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-blue-600/20 text-blue-300 border border-blue-800 hover:bg-blue-600/30"
                >
                  <Icon name="target" size={9} /> 以此实体为中心
                </button>
              ) : null}
            </div>
            {selected.description && <p className="text-xs text-zinc-400 leading-relaxed mb-2">{selected.description}</p>}
            {selected.state && <p className="text-xs text-amber-400/80 leading-relaxed mb-2">{selected.state}</p>}
            {selectedRels.length > 0 && (
              <div className="border-t border-zinc-800 pt-2 mt-1 space-y-1">
                <p className="text-[10px] text-zinc-600 uppercase tracking-wide">关系</p>
                {selectedRels.map(r => (
                  <div key={r.id} className="text-[11px] text-zinc-400">
                    <span className="text-zinc-300">{r.from_name}</span>
                    <span className="text-sky-400 mx-1">—{r.rel_type}→</span>
                    <span className="text-zinc-300">{r.to_name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 拖拽提示 */}
        {!focus && typeCounts.length > 0 && (
          <div className="absolute bottom-2 left-3 text-[10px] text-zinc-700 pointer-events-none">
            拖拽节点固定 · 滚轮缩放 · 点实体看详情并聚焦
          </div>
        )}
      </div>
    </div>
  )
}

function handleZoomFn(setZoom: React.Dispatch<React.SetStateAction<number>>, factor: number) {
  setZoom(z => Math.min(2.5, Math.max(0.3, z * factor)))
}
