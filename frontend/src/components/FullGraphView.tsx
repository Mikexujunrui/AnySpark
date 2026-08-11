// FullGraphView — 知识图谱可视化（V4 重写版）
// 数据：/api/graph/entities + /api/graph/relations → SVG 力导向简化布局
// 能力：缩放平移 / 拖拽实体 / 点击查看详情 / 按类型着色
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import Icon from './ui/Icon'

interface Entity { id: string; name: string; entity_type?: string; description?: string; state?: string }
interface Relation { id: string; from_name: string; to_name: string; rel_type: string; description?: string }
interface Pos { x: number; y: number }

const TYPE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  '角色': { fill: 'rgba(59,130,246,0.25)', stroke: '#3b82f6', text: '#93c5fd' },
  '物件': { fill: 'rgba(245,158,11,0.2)', stroke: '#f59e0b', text: '#fcd34d' },
  '地点': { fill: 'rgba(16,185,129,0.2)', stroke: '#10b981', text: '#6ee7b7' },
  '事件': { fill: 'rgba(239,68,68,0.2)', stroke: '#ef4444', text: '#fca5a5' },
  '设定': { fill: 'rgba(168,85,247,0.2)', stroke: '#a855f7', text: '#d8b4fe' },
  '组织': { fill: 'rgba(14,165,233,0.2)', stroke: '#0ea5e9', text: '#7dd3fc' },
}

function typeStyle(t: string) {
  return TYPE_COLORS[t] || { fill: 'rgba(39,39,42,0.8)', stroke: '#71717a', text: '#a1a1aa' }
}

// 简化力导向：斥力 + 弹簧 + 中心引力，迭代收敛
function layout(entities: Entity[], relations: Relation[]): Record<string, Pos> {
  const pos: Record<string, Pos> = {}
  const vel: Record<string, Pos> = {}
  entities.forEach((e, i) => {
    const angle = (i / Math.max(1, entities.length)) * Math.PI * 2
    pos[e.id] = { x: Math.cos(angle) * 180 + 300, y: Math.sin(angle) * 180 + 200 }
    vel[e.id] = { x: 0, y: 0 }
  })
  const connected = new Set<string>()
  relations.forEach(r => { connected.add(r.from_name); connected.add(r.to_name) })

  for (let iter = 0; iter < 150; iter++) {
    // 斥力（所有对）
    for (let i = 0; i < entities.length; i++) {
      for (let j = i + 1; j < entities.length; j++) {
        const a = entities[i], b = entities[j]
        const dx = pos[a.id].x - pos[b.id].x
        const dy = pos[a.id].y - pos[b.id].y
        const d2 = Math.max(10, dx * dx + dy * dy)
        const force = 2400 / d2
        const d = Math.sqrt(d2)
        const fx = (dx / d) * force
        const fy = (dy / d) * force
        vel[a.id].x += fx; vel[a.id].y += fy
        vel[b.id].x -= fx; vel[b.id].y -= fy
      }
    }
    // 弹簧（关系相连的拉近）
    relations.forEach(r => {
      const a = entities.find(e => e.name === r.from_name)
      const b = entities.find(e => e.name === r.to_name)
      if (!a || !b || a.id === b.id) return
      const dx = pos[b.id].x - pos[a.id].x
      const dy = pos[b.id].y - pos[a.id].y
      const d = Math.max(1, Math.sqrt(dx * dx + dy * dy))
      const force = 0.02 * (d - 120)
      vel[a.id].x += (dx / d) * force; vel[a.id].y += (dy / d) * force
      vel[b.id].x -= (dx / d) * force; vel[b.id].y -= (dy / d) * force
    })
    // 中心引力（孤立节点拉向中心）
    entities.forEach(e => {
      if (!connected.has(e.name)) {
        vel[e.id].x += (300 - pos[e.id].x) * 0.01
        vel[e.id].y += (200 - pos[e.id].y) * 0.01
      }
    })
    // 积分 + 阻尼
    entities.forEach(e => {
      vel[e.id].x *= 0.85; vel[e.id].y *= 0.85
      pos[e.id].x += vel[e.id].x
      pos[e.id].y += vel[e.id].y
    })
  }
  return pos
}

export default function FullGraphView({ bookId }: { bookId: string }) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [relations, setRelations] = useState<Relation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Entity | null>(null)
  const [zoom, setZoom] = useState(0.85)
  const [pan, setPan] = useState<Pos>({ x: 20, y: 20 })
  const [manualPos, setManualPos] = useState<Record<string, Pos>>({})
  const [hoveredRel, setHoveredRel] = useState<string | null>(null)

  const svgRef = useRef<SVGSVGElement>(null)
  const panRef = useRef<{ x0: number; y0: number; px: number; py: number } | null>(null)
  const dragRef = useRef<{ id: string; dx: number; dy: number; moved: boolean } | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
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

  // 力导向布局（仅初始，节点拖拽后覆盖）
  const baseLayout = useMemo(() => layout(entities, relations), [entities, relations])
  const finalPos = useCallback((id: string): Pos => manualPos[id] ?? baseLayout[id] ?? { x: 0, y: 0 }, [manualPos, baseLayout])

  const handleZoom = (factor: number) => setZoom(z => Math.min(2.5, Math.max(0.3, z * factor)))

  const onNodePointerDown = (e: React.PointerEvent, id: string) => {
    e.stopPropagation()
    const p = finalPos(id)
    dragRef.current = { id, dx: e.clientX - p.x * zoom, dy: e.clientY - p.y * zoom, moved: false }
  }
  const onNodePointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    const d = dragRef.current
    const nx = (e.clientX - d.dx) / zoom
    const ny = (e.clientY - d.dy) / zoom
    if (Math.abs(nx * zoom + d.dx - e.clientX) > 2 || Math.abs(ny * zoom + d.dy - e.clientY) > 2) d.moved = true
    setManualPos(prev => ({ ...prev, [d.id]: { x: nx, y: ny } }))
  }
  const onNodePointerUp = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    const d = dragRef.current
    dragRef.current = null
    if (!d.moved) {
      const ent = entities.find(x => x.id === d.id)
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

  const selectedRels = selected
    ? relations.filter(r => r.from_name === selected.name || r.to_name === selected.name)
    : []

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

  const byName: Record<string, Entity> = {}
  entities.forEach(e => { byName[e.name] = e })

  return (
    <div className="h-full flex flex-col relative">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-1.5 shrink-0">
        <span className="text-[11px] text-zinc-500 mr-1">图谱视图</span>
        <span className="text-[11px] text-zinc-600">{entities.length} 实体 · {relations.length} 关系</span>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => handleZoom(1.25)} className="w-6 h-6 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded text-sm" title="放大">+</button>
          <button onClick={() => handleZoom(0.8)} className="w-6 h-6 flex items-center justify-center text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 rounded text-sm" title="缩小">−</button>
          <button onClick={() => { setZoom(0.85); setPan({ x: 20, y: 20 }); setManualPos({}) }} className="px-2 py-0.5 text-[10px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded" title="重置布局">重置</button>
        </div>
      </div>

      {/* SVG 画布 */}
      <div className="flex-1 overflow-hidden relative">
        <svg
          ref={svgRef}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          onPointerDown={onCanvasPointerDown}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={onCanvasPointerUp}
        >
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* 连线 */}
            {relations.map((r, i) => {
              const a = byName[r.from_name]
              const b = byName[r.to_name]
              if (!a || !b) return null
              const pa = finalPos(a.id), pb = finalPos(b.id)
              const isSelected = selected && (selected.name === r.from_name || selected.name === r.to_name)
              const isHover = hoveredRel === r.id
              const stroke = isSelected ? '#f59e0b' : isHover ? '#93c5fd' : '#3f3f46'
              const opacity = selected && !isSelected ? 0.15 : 0.7
              return (
                <g key={r.id} onMouseEnter={() => setHoveredRel(r.id)} onMouseLeave={() => setHoveredRel(null)}>
                  <line x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} stroke={stroke} strokeWidth={isHover ? 2 : 1.2} opacity={opacity} />
                  {/* 关系标签（中点） */}
                  {(isSelected || isHover) && (
                    <text x={(pa.x + pb.x) / 2} y={(pa.y + pb.y) / 2 - 6} textAnchor="middle" fontSize="9" fill={stroke} opacity={0.9}>
                      {r.rel_type}
                    </text>
                  )}
                </g>
              )
            })}

            {/* 实体节点 */}
            {entities.map(e => {
              const p = finalPos(e.id)
              const style = typeStyle(e.entity_type || '')
              const isSelected = selected?.id === e.id
              const dimmed = selected && selected.id !== e.id && !selectedRels.some(r => r.from_name === e.name || r.to_name === e.name)
              return (
                <g key={e.id} transform={`translate(${p.x}, ${p.y})`} opacity={dimmed ? 0.25 : 1}
                  onPointerDown={(ev) => onNodePointerDown(ev, e.id)}
                  onPointerMove={onNodePointerMove}
                  onPointerUp={onNodePointerUp}
                  style={{ cursor: 'pointer' }}
                >
                  <rect x={-58} y={-18} width={116} height={36} rx={8} fill={style.fill} stroke={isSelected ? '#f59e0b' : style.stroke} strokeWidth={isSelected ? 2 : 1.2} />
                  <text textAnchor="middle" y={-1} fontSize="11" fill={style.text} fontWeight={isSelected ? 600 : 400}>
                    {e.name.length > 9 ? e.name.slice(0, 9) + '…' : e.name}
                  </text>
                  <text textAnchor="middle" y={12} fontSize="8" fill="#71717a">
                    {e.entity_type || ''}
                  </text>
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
      </div>
    </div>
  )
}
