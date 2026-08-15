import { useState, useEffect, useRef } from 'react'
import { setBackendStatus } from '../store'

type Status = 'connecting' | 'online' | 'degraded' | 'offline'

const DIAG_PREFIX = '[CONN-DIAG]'
const POLL_INTERVAL_MS = 15_000
const FAST_POLL_INTERVAL_MS = 5_000
const REQUEST_TIMEOUT_MS = 8_000
const DEGRADED_LATENCY_MS = 2_000  // >2s latency → degraded
const OFFLINE_FAIL_COUNT = 3

/**
 * Backend connection status indicator.
 *
 * Uses setTimeout-based polling (not setInterval) to avoid concurrent checks
 * when the network is slow — each check schedules the next one only after it
 * completes, preventing failCountRef from being incremented multiple times
 * for a single outage event.
 */
export default function BackendStatus() {
  const [status, setStatus] = useState<Status>('connecting')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [failReason, setFailReason] = useState<string | null>(null)
  const [updateInfo, setUpdateInfo] = useState<{ latest_version: string; release_url: string } | null>(null)
  const updateCheckedRef = useRef(false)
  const mountedRef = useRef(true)
  const failCountRef = useRef(0)
  const nextTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const checkRef = useRef<() => void>(() => {
    console.warn(`${DIAG_PREFIX} BackendStatus — check() called before init, ignoring`)
  })

  // S164：后端 online 后查一次 GitHub 最新 Release——有新版本显示提示条（只查一次，静默失败）
  async function checkUpdate() {
    if (updateCheckedRef.current) return
    updateCheckedRef.current = true
    try {
      const res = await fetch('/api/update/check')
      if (!res.ok) return
      const d = await res.json()
      if (d.has_update && d.latest_version && mountedRef.current) {
        setUpdateInfo({ latest_version: d.latest_version, release_url: d.release_url || '' })
      }
    } catch {
      /* 网络失败静默——不打扰用户 */
    }
  }

  // ── Helpers ──

  /** Schedule the next health check after `delayMs`. */
  function scheduleNext(delayMs: number) {
    if (nextTimerRef.current) clearTimeout(nextTimerRef.current)
    nextTimerRef.current = setTimeout(checkRef.current, delayMs)
  }

  /** Transition to a new status and sync to global store. */
  function transitionTo(
    newStatus: Status,
    latency: number | null,
    newFailCount: number,
    reason: string | null,
    nextDelay: number,
  ) {
    setStatus(newStatus)
    setLatencyMs(latency)
    setFailReason(reason)
    setBackendStatus({
      status: newStatus,
      latencyMs: latency,
      lastCheckAt: Date.now(),
      failCount: newFailCount,
      failReason: reason,
    })
    // S164：首次连上后端后查一次版本（只查一次；offline 不查）
    if (newStatus === 'online' || newStatus === 'degraded') {
      checkUpdate()
    }
    scheduleNext(nextDelay)
  }

  useEffect(() => {
    mountedRef.current = true

    async function check() {
      if (!mountedRef.current) return

      const startTime = performance.now()
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

      try {
        const res = await fetch('/api/health', { signal: controller.signal })
        clearTimeout(timeoutId)
        const elapsed = Math.round(performance.now() - startTime)

        if (res.ok && mountedRef.current) {
          failCountRef.current = 0
          const newStatus: Status = elapsed > DEGRADED_LATENCY_MS ? 'degraded' : 'online'
          const delay = newStatus === 'degraded' ? FAST_POLL_INTERVAL_MS : POLL_INTERVAL_MS
          console.log(
            `${DIAG_PREFIX} health-check — %s | %dms | next=%ds`,
            newStatus, elapsed, delay / 1000,
          )
          transitionTo(newStatus, elapsed, 0, null, delay)
          return
        }

        if (mountedRef.current) {
          failCountRef.current++
          const reason = `HTTP ${res.status}`
          console.warn(`${DIAG_PREFIX} health-check — 失败 %s | fail=%d/%d`, reason, failCountRef.current, OFFLINE_FAIL_COUNT)
          if (failCountRef.current >= OFFLINE_FAIL_COUNT) {
            transitionTo('offline', null, failCountRef.current, reason, FAST_POLL_INTERVAL_MS)
          } else {
            scheduleNext(FAST_POLL_INTERVAL_MS)
          }
        }
      } catch (e: unknown) {
        clearTimeout(timeoutId)
        if (!mountedRef.current) return

        failCountRef.current++
        const reason = classifyError(e)

        console.warn(
          `${DIAG_PREFIX} health-check — 异常 | %s | fail=%d/%d`,
          reason, failCountRef.current, OFFLINE_FAIL_COUNT,
        )

        if (failCountRef.current >= OFFLINE_FAIL_COUNT) {
          transitionTo('offline', null, failCountRef.current, reason, FAST_POLL_INTERVAL_MS)
        } else {
          scheduleNext(FAST_POLL_INTERVAL_MS)
        }
      }
    }

    checkRef.current = check
    // Start the first check immediately
    check()

    return () => {
      mountedRef.current = false
      if (nextTimerRef.current) {
        clearTimeout(nextTimerRef.current)
        nextTimerRef.current = null
      }
    }
  }, [])

  // ── Render ──

  const dotColor = {
    connecting: 'bg-amber-400',
    online: 'bg-emerald-400',
    degraded: 'bg-yellow-400',
    offline: 'bg-red-500',
  }[status]

  const dotPulse = (status === 'connecting' || status === 'degraded') ? 'animate-pulse' : ''

  const label = {
    connecting: '连接中',
    online: '已连接',
    degraded: '延迟高',
    offline: '未连接',
  }[status]

  const titleLines: string[] = []
  if (status === 'online') {
    titleLines.push(`后端运行正常 · ${latencyMs}ms`)
  } else if (status === 'degraded') {
    titleLines.push(`后端响应慢 · ${latencyMs}ms`)
    titleLines.push('可能原因：LLM 任务繁忙 / 网络拥塞')
  } else if (status === 'offline') {
    titleLines.push(`后端未响应 · 连续 ${failCountRef.current} 次失败`)
    if (failReason) titleLines.push(`原因: ${failReason}`)
    titleLines.push('可能原因：后端进程崩溃 / 网络断开')
  } else {
    titleLines.push('正在检测后端状态...')
  }

  return (
    <div
      className="fixed top-3 right-3 z-50 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium bg-zinc-900/80 backdrop-blur border border-zinc-800 shadow-lg select-none"
      title={titleLines.join('\n')}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} ${dotPulse}`} />
      <span className="text-zinc-400">{label}</span>
      {status === 'online' && latencyMs !== null && (
        <span className="text-zinc-500 text-[9px]">{latencyMs}ms</span>
      )}
      {status === 'degraded' && latencyMs !== null && (
        <span className="text-yellow-500 text-[9px]">{latencyMs}ms</span>
      )}
      {updateInfo && (
        <a
          href={updateInfo.release_url || 'https://github.com/Mikexujunrui/AnySpark/releases'}
          target="_blank"
          rel="noreferrer"
          className="ml-1.5 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 text-[9px] font-medium transition-colors"
          title={`发现新版本 ${updateInfo.latest_version}——点击前往 Release 下载`}
        >
          ↑ 新版 {updateInfo.latest_version.replace(/^v/i, '')}
        </a>
      )}
    </div>
  )
}

// ── Utilities ──

/** Classify a fetch error into a human-readable reason string. */
function classifyError(e: unknown): string {
  if (e instanceof DOMException && e.name === 'AbortError') return '请求超时'
  if (e instanceof TypeError && e.message === 'Failed to fetch') return '网络不可达'
  return e instanceof Error ? e.message : String(e)
}