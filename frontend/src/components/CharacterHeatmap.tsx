import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { api } from '../api'
import { useResizeObserver } from '../hooks/useResizeObserver'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'

function relativeTime(iso) {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (isNaN(t)) return '—'
  const diff = Date.now() - t
  const s = Math.floor(diff / 1000)
  if (s < 60) return '刚刚'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d} 天前`
  const mo = Math.floor(d / 30)
  return `${mo} 个月前`
}

export default function CharacterHeatmap({ bookId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const containerRef = useRef(null)
  const svgRef = useRef(null)
  const dims = useResizeObserver(containerRef)

  useEffect(() => { load() }, [bookId])
  useEffect(() => { if (data?.matrix) render() }, [data, dims])

  async function load() {
    setLoading(true)
    try {
      const res: any = await api.getCharacterMentions(bookId)
      setData(res)
      if (!res.matrix) {
        // cache miss → auto-compute
        await refresh()
      } else {
        setLoading(false)
      }
    } catch (e) {
      console.error(e)
      showToast('加载戏份数据失败', 'error')
      setLoading(false)
    }
  }

  async function refresh() {
    setRefreshing(true)
    try {
      const res = await api.refreshCharacterMentions(bookId)
      setData(res)
    } catch (e) {
      console.error(e)
      showToast('计算戏份失败', 'error')
    }
    setRefreshing(false)
    setLoading(false)
  }

  function render() {
    if (!containerRef.current) return
    const matrix = data.matrix || []
    const chaptersCount = data.chaptersCount || 0
    const { w } = dims
    if (w < 200) return

    // Clear container
    d3.select(containerRef.current).selectAll('*').remove()

    if (matrix.length === 0 || chaptersCount === 0) {
      d3.select(containerRef.current).append('div')
        .style('padding', '40px').style('text-align', 'center')
        .style('color', '#52525b').style('font-size', '13px')
        .text('暂无角色或章节数据')
      return
    }

    // Layout
    const labelWidth = Math.min(140, Math.max(80, w * 0.18))
    const margin = { top: 35, right: 20, bottom: 40, left: labelWidth + 10 }
    const cellSize = Math.max(18, Math.min(28, (w - margin.left - margin.right) / chaptersCount))
    const innerW = cellSize * chaptersCount
    const rowH = Math.max(20, Math.min(28, cellSize * 0.95))
    const innerH = rowH * matrix.length
    const svgH = margin.top + innerH + margin.bottom

    const maxCount = d3.max(matrix, row => d3.max(row.chapters, c => c.count)) || 1
    const colorScale = d3.scaleSequential()
      .domain([0, maxCount])
      .interpolator(t => d3.interpolate('#0c1929', '#38bdf8')(Math.pow(t, 0.5)))

    // Scroll container with SVG
    const scrollWrap = d3.select(containerRef.current).append('div')
      .style('overflow-x', 'auto').style('max-width', `${w}px`).style('position', 'relative')
    const scrollSvg = scrollWrap.append('svg')
      .attr('class', 'heatmap-svg')
      .attr('width', Math.max(w, margin.left + innerW + margin.right))
      .attr('height', svgH)
    const sg = scrollSvg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    // Y axis (character labels)
    sg.selectAll('.row-label').data(matrix).join('text')
      .attr('class', 'row-label')
      .attr('x', -8).attr('y', (_, i) => i * rowH + rowH / 2)
      .attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
      .attr('fill', '#a1a1aa').attr('font-size', 11)
      .text(d => d.charName.length > 8 ? d.charName.slice(0, 8) + '…' : d.charName)

    // X axis (chapter indices)
    const showEvery = Math.max(1, Math.ceil(chaptersCount / 25))
    for (let i = 0; i < chaptersCount; i += showEvery) {
      sg.append('text')
        .attr('x', i * cellSize + cellSize / 2).attr('y', -8)
        .attr('text-anchor', 'middle').attr('fill', '#71717a').attr('font-size', 10)
        .text(`#${i + 1}`)
    }

    // Tooltip
    const tooltip = d3.select(containerRef.current).append('div')
      .style('position', 'absolute').style('background', '#18181b')
      .style('border', '1px solid #3f3f46').style('border-radius', '8px')
      .style('padding', '6px 10px').style('font-size', '11px')
      .style('color', '#d4d4d8').style('pointer-events', 'none')
      .style('opacity', 0).style('z-index', 30)
      .style('box-shadow', '0 4px 12px rgb(0 0 0 / 0.4)')

    // Cells
    matrix.forEach((row, ri) => {
      const chapMap = new Map(row.chapters.map(c => [c.idx, c.count]))
      for (let ci = 0; ci < chaptersCount; ci++) {
        const idx = ci + 1
        const count = chapMap.get(idx) || 0
        const rect = sg.append('rect')
          .attr('x', ci * cellSize + 1).attr('y', ri * rowH + 1)
          .attr('width', cellSize - 2).attr('height', rowH - 2)
          .attr('rx', 3).attr('fill', colorScale(count))
        if ((count as number) > 0) {
          rect.attr('stroke', '#38bdf8').attr('stroke-width', 1.5).attr('stroke-opacity', 0.0)
            .on('mouseover', function(event) {
              d3.select(this).attr('stroke-opacity', 1)
              tooltip.style('opacity', 1)
                .html(`<div style="font-weight:600;color:#e4e4e7">${row.charName}</div>`
                    + `<div style="margin-top:2px">第${idx}章 · <span style="color:#38bdf8">${count}</span> 次提及</div>`)
                .style('left', `${event.offsetX + 12}px`)
                .style('top', `${event.offsetY - 10}px`)
            })
            .on('mouseleave', function() {
              d3.select(this).attr('stroke-opacity', 0)
              tooltip.style('opacity', 0)
            })
        }
      }
    })
  }

  const matrix = data?.matrix || []
  const totalMentions = matrix.reduce((acc, r) => acc + (r.totalMentions || 0), 0)
  const topChar = matrix[0]

  if (loading) return <LoadingState text="加载戏份数据..." />

  return (
    <div className="h-full flex flex-col bg-zinc-950/30">
      <div className="px-6 py-3 border-b border-zinc-800 flex items-center justify-between shrink-0">
        <div className="flex gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5"><Icon name="users" size={12} className="text-sky-400" /> <b className="text-zinc-300">{matrix.length}</b> 角色</span>
          <span className="flex items-center gap-1.5"><Icon name="message-circle" size={12} className="text-emerald-400" /> <b className="text-zinc-300">{totalMentions.toLocaleString()}</b> 总提及</span>
          {topChar && (
            <span className="flex items-center gap-1.5">
              <Icon name="award" size={12} className="text-amber-400" /> 提及最多 <b className="text-zinc-300">{topChar.charName}</b>
              <span className="text-zinc-600">({topChar.totalMentions})</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data?.lastUpdatedAt && (
            <span className="text-[10px] text-zinc-600">
              上次计算: {relativeTime(data.lastUpdatedAt)}
            </span>
          )}
          <button
            onClick={refresh}
            disabled={refreshing}
            className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <Icon name="refresh" size={12} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? '计算中...' : '刷新'}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 px-6 py-2 border-b border-zinc-800/60 shrink-0">
        <span className="text-[10px] text-zinc-500">少</span>
        <div className="flex gap-0.5">
          {[0.05, 0.2, 0.4, 0.65, 0.9].map((t, i) => (
            <div key={i} className="w-5 h-3 rounded-sm"
              style={{
                background: d3.interpolate('#0c1929', '#38bdf8')(t)
              }} />
          ))}
        </div>
        <span className="text-[10px] text-zinc-500">多</span>
        <span className="text-[10px] text-zinc-600 ml-auto">颜色深 = 提及次数多 · 悬停查看详情</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div ref={containerRef} className="relative min-h-[200px]" />
      </div>
    </div>
  )
}
