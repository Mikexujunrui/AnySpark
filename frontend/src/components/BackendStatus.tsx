import { useState, useEffect, useRef } from 'react'

type Status = 'connecting' | 'online' | 'offline'

export default function BackendStatus() {
  const [status, setStatus] = useState<Status>('connecting')
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    async function check() {
      if (!mountedRef.current) return
      setStatus('connecting')
      try {
        const controller = new AbortController()
        const id = setTimeout(() => controller.abort(), 5000)
        const res = await fetch('/api/health', {
          signal: controller.signal,
        })
        clearTimeout(id)
        if (res.ok && mountedRef.current) {
          setStatus('online')
        } else if (mountedRef.current) {
          setStatus('offline')
        }
      } catch {
        if (mountedRef.current) setStatus('offline')
      }
    }

    check()
    const timer = setInterval(check, 15_000)

    return () => {
      mountedRef.current = false
      clearInterval(timer)
    }
  }, [])

  const dotColor = {
    connecting: 'bg-amber-400',
    online: 'bg-emerald-400',
    offline: 'bg-red-500',
  }[status]

  const label = {
    connecting: '连接中',
    online: '已连接',
    offline: '未连接',
  }[status]

  const dotPulse = status === 'connecting' ? 'animate-pulse' : ''

  return (
    <div
      className="fixed top-3 right-3 z-50 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-zinc-900/80 backdrop-blur border border-zinc-800 shadow-lg select-none"
      title={status === 'online' ? '后端运行正常' : status === 'connecting' ? '正在连接后端...' : '后端未响应'}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} ${dotPulse}`} />
      <span className="text-zinc-400">{label}</span>
    </div>
  )
}
