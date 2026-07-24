import { useEffect, useRef } from 'react'
import Icon from './ui/Icon'
import { useRefreshKey, useSelectedTimeOrder, useMaxTimeOrder, useTimelineEvents, setTimeOrder, setTimelineMeta } from '../store'

interface Props {
  bookId: string
}

export default function TimeAxis({ bookId }: Props) {
  const refreshKey = useRefreshKey()
  const selectedTimeOrder = useSelectedTimeOrder()
  const maxTimeOrder = useMaxTimeOrder()
  const timelineEvents = useTimelineEvents()
  const loadedRef = useRef(false)

  useEffect(() => {
    loadTimelineMeta()
  }, [bookId, refreshKey])

  async function loadTimelineMeta() {
    try {
      const res = await fetch(`/api/books/${bookId}/timeline-data`)
      const data = await res.json()
      const events = (data.events || []).map((e: any) => ({
        timeOrder: e.order ?? e.timeOrder ?? 0,
        label: e.label || '',
        chapterRef: e.chapter_ref || e.chapterRef || '',
      }))
      setTimelineMeta(events)
      if (!loadedRef.current && events.length > 0) {
        setTimeOrder(events[0].timeOrder)
        loadedRef.current = true
      }
    } catch (e) {
      console.error('Failed to load timeline meta:', e)
    }
  }

  if (maxTimeOrder <= 0) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 bg-zinc-900/60">
        <span className="text-[10px] text-zinc-600 shrink-0 font-medium flex items-center gap-1"><Icon name="clock" size={12} /> 时间轴</span>
        <span className="text-[10px] text-zinc-600 flex-1">暂无时间线数据 — 在对话中说"生成时间线"来创建</span>
      </div>
    )
  }

  function handleSliderChange(e: React.ChangeEvent<HTMLInputElement>) {
    setTimeOrder(Number(e.target.value))
  }

  // Find the closest event to the current position
  const currentEvent = timelineEvents.find(e => e.timeOrder === selectedTimeOrder)
    || timelineEvents.reduce((prev, curr) =>
      Math.abs(curr.timeOrder - selectedTimeOrder) < Math.abs(prev.timeOrder - selectedTimeOrder) ? curr : prev
    , timelineEvents[0])

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 bg-zinc-900/60">
      <span className="text-[10px] text-zinc-500 shrink-0 font-medium flex items-center gap-1"><Icon name="clock" size={12} /> 时间轴</span>
      <input
        type="range"
        min={0}
        max={maxTimeOrder}
        value={selectedTimeOrder}
        onChange={handleSliderChange}
        className="flex-1 h-1.5 bg-zinc-700 rounded-full appearance-none cursor-pointer
          accent-blue-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5
          [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full
          [&::-webkit-slider-thumb]:bg-blue-500 [&::-webkit-slider-thumb]:shadow-md"
      />
      <span className="text-[10px] text-zinc-400 shrink-0 min-w-[60px] text-right">
        {currentEvent?.chapterRef || `#${selectedTimeOrder}`}
      </span>
      <span className="text-[10px] text-zinc-500 shrink-0 max-w-[120px] truncate" title={currentEvent?.label}>
        {currentEvent?.label || ''}
      </span>
    </div>
  )
}