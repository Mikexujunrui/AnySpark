import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import Icon from './ui/Icon'
import { useResizeObserver } from '../hooks/useResizeObserver'

interface GraphNode {
  id: string
  title: string
  index: number
}
interface GraphLink {
  source: string
  target: string
  type: string
  shared_count: number
  shared_entities?: string[]
}
interface DependencyData {
  book_id: string
  nodes: GraphNode[]
  edges: any[]
  total_nodes: number
  total_edges: number
  d3_format: {
    nodes: GraphNode[]
    links: GraphLink[]
  }
}

export default function ChapterDependencyGraph({ bookId }: { bookId: string }) {
  const [data, setData] = useState<DependencyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [impactChapter, setImpactChapter] = useState('')
  const [impactResult, setImpactResult] = useState<any>(null)
  const [impactLoading, setImpactLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const dims = useResizeObserver(containerRef)

  useEffect(() => { loadData() }, [bookId])
  useEffect(() => { renderGraph() }, [data, dims])

  async function loadData() {
    setLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/chapter-dependencies`)
      if (res.ok) setData(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function runImpact() {
    if (!impactChapter.trim()) return
    setImpactLoading(true)
    try {
      const res = await fetch(`/api/books/${bookId}/chapter-dependencies/impact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: 'chapter', source_id: impactChapter.trim(), change_description: '修改' }),
      })
      if (res.ok) setImpactResult(await res.json())
    } catch (e) { console.error(e) }
    setImpactLoading(false)
  }

  function renderGraph() {
    if (!svgRef.current || !data?.d3_format) return
    const { w, h } = dims
    if (w < 200 || h < 200) return

    const nodes = data.d3_format.nodes.map(n => ({ ...n }))
    const links = data.d3_format.links.map(l => ({
      source: nodes.find(n => n.id === l.source)!,
      target: nodes.find(n => n.id === l.target)!,
      type: l.type,
      shared_count: l.shared_count,
    }))

    if (nodes.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('width', w).attr('height', h)

    const g = svg.append('g')

    // Zoom support
    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.3, 3]).on('zoom', (event) => {
      g.attr('transform', event.transform.toString())
    })
    svg.call(zoom)

    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links as any).id((d: any) => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(w / 2, h / 2))

    // Links
    const link = g.selectAll('.link').data(links).enter().append('line')
      .attr('class', 'link')
      .attr('stroke', '#3f3f46').attr('stroke-width', 1.5).attr('opacity', 0.6)

    // Nodes
    const node = g.selectAll('.node').data(nodes).enter().append('g').attr('class', 'node')
      .call(d3.drag<any, any>()
        .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null }))

    node.append('circle')
      .attr('r', 14).attr('fill', 'var(--color-zinc-800)').attr('stroke', '#0ea5e9').attr('stroke-width', 2)

    node.append('text')
      .text(d => `${(d as any).index}`)
      .attr('text-anchor', 'middle').attr('dy', '0.35em')
      .attr('fill', 'var(--color-zinc-200)').attr('font-size', 10).attr('font-weight', 'bold')

    // Tooltip
    const tooltip = d3.select(containerRef.current!).selectAll('.dep-tip').data([0]).join('div')
      .attr('class', 'dep-tip')
      .style('position', 'absolute').style('background', 'var(--color-zinc-900)')
      .style('border', '1px solid var(--color-zinc-700)').style('border-radius', '8px')
      .style('padding', '6px 8px').style('font-size', '11px')
      .style('color', 'var(--color-zinc-300)').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 30)

    node.on('mouseover', function(event: any, d: any) {
      d3.select(this).select('circle').attr('r', 18).attr('fill', 'var(--color-accent-soft)')
      tooltip.style('opacity', 1)
        .html(`<div style="font-weight:600">第${d.index}章: ${d.title}</div>`)
        .style('left', `${event.offsetX + 12}px`)
        .style('top', `${event.offsetY - 8}px`)
    }).on('mouseout', function() {
      d3.select(this).select('circle').attr('r', 14).attr('fill', 'var(--color-zinc-800)')
      tooltip.style('opacity', 0)
    })

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x).attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x).attr('y2', (d: any) => d.target.y)
      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
    })
  }

  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="git-branch" size={16} className="text-sky-400" />
          <h3 className="text-sm font-semibold text-zinc-200">章节依赖图</h3>
        </div>
        <div className="flex items-center justify-center py-16 text-zinc-600 text-sm">
          <div className="w-5 h-5 border-2 border-zinc-700 border-t-sky-400 rounded-full animate-spin mr-2" /> 构建依赖图...
        </div>
      </div>
    )
  }

  if (!data || data.total_nodes === 0) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="git-branch" size={16} className="text-sky-400" />
          <h3 className="text-sm font-semibold text-zinc-200">章节依赖图</h3>
        </div>
        <div className="flex flex-col items-center gap-2 py-12 text-zinc-600">
          <Icon name="git-branch" size={28} />
          <p className="text-xs">暂无章节数据</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
          <Icon name="git-branch" size={14} /> 章节依赖图
        </h3>
        <span className="text-[10px] text-zinc-600">{data.total_nodes} 章 · {data.total_edges} 条依赖</span>
      </div>

      {/* Impact analysis */}
      <div className="flex items-center gap-2 mb-3">
        <input
          value={impactChapter}
          onChange={e => setImpactChapter(e.target.value)}
          placeholder="章节 ID 或序号"
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none w-40"
        />
        <button
          onClick={runImpact}
          disabled={impactLoading || !impactChapter.trim()}
          className="text-xs bg-sky-600/80 hover:bg-sky-500 disabled:opacity-40 text-white rounded-lg px-3 py-1.5 font-medium transition-colors"
        >
          {impactLoading ? '分析中...' : '影响传播'}
        </button>
        {impactResult && (
          <span className="text-[10px] text-amber-400">
            影响 {impactResult.total_affected} 章
          </span>
        )}
      </div>

      {/* Graph */}
      <div ref={containerRef} className="relative" style={{ height: 300 }}>
        <svg ref={svgRef} className="w-full h-full" />
      </div>

      {/* Impact results */}
      {impactResult?.affected_chapters?.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] text-zinc-500 mb-2">受影响章节（按依赖深度排序）</div>
          <div className="flex flex-wrap gap-1.5">
            {impactResult.affected_chapters.map((ch: any, i: number) => (
              <span
                key={i}
                className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  ch.depth === 1
                    ? 'bg-red-900/30 border-red-700/40 text-red-400'
                    : ch.depth === 2
                    ? 'bg-amber-900/30 border-amber-700/40 text-amber-400'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-400'
                }`}
              >
                第{ch.chapter_id}章 (深度{ch.depth})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
