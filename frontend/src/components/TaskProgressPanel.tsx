import { useState, useEffect, useRef, useCallback } from 'react'
import Icon from './ui/Icon'
import { api, createTaskSSE } from '../api'

function StatusIcon({ status, size = 14 }: { status: string; size?: number }) {
  const map: Record<string, { name: string; className: string }> = {
    pending: { name: 'circle', className: 'text-zinc-600' },
    running: { name: 'loader', className: 'text-sky-400 animate-spin' },
    completed: { name: 'check-circle', className: 'text-emerald-400' },
    failed: { name: 'alert-circle', className: 'text-red-400' },
    paused: { name: 'pause', className: 'text-amber-400' },
    cancelled: { name: 'x', className: 'text-zinc-500' },
    skipped: { name: 'skip-forward', className: 'text-zinc-500' },
  }
  const icon = map[status]
  if (!icon) return <Icon name="circle" size={size} className="text-zinc-700" />
  return <Icon name={icon.name} size={size} className={icon.className} />
}

export default function TaskProgressPanel({ bookId, taskId, onClose }) {
  const [task, setTask] = useState(null)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const eventSourceRef = useRef(null)
  const logsEndRef = useRef(null)

  // Fetch task details
  const fetchTask = useCallback(async () => {
    try {
      const data = await api.getTask(bookId, taskId)
      setTask(data)
      setLoading(false)
    } catch (e) {
      setLogs(prev => [...prev, { type: 'error', text: `加载失败: ${e.message}` }])
      setLoading(false)
    }
  }, [bookId, taskId])

  useEffect(() => { fetchTask() }, [fetchTask])

  // SSE stream for real-time updates
  useEffect(() => {
    if (!taskId) return

    let cancelled = false

    const connectSSE = async () => {
      setStreaming(true)
      try {
        const response = await createTaskSSE(bookId, taskId)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              const eventType = line.slice(7).trim()
              // Next line should be data
              continue
            }
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                handleSSEEvent(eventType, data, line)
              } catch {
                // Plain text data (chunks)
                setLogs(prev => [...prev, { type: 'chunk', text: line.slice(6) }])
              }
            }
          }
        }
      } catch (e) {
        if (!cancelled) {
          setLogs(prev => [...prev, { type: 'error', text: `SSE连接断开: ${e.message}` }])
        }
      }
      setStreaming(false)
    }

    const eventType = ''
    const handleSSEEvent = (type, data, rawLine) => {
      switch (type) {
        case 'step_done':
          setLogs(prev => [...prev, {
            type: 'step_done',
            text: `${data.step_label || data.step_id} 完成`,
          }])
          fetchTask() // Refresh task state
          break
        case 'step_error':
          setLogs(prev => [...prev, {
            type: 'error',
            text: `${data.step_label || data.step_id} 失败: ${data.error}`,
          }])
          fetchTask()
          break
        case 'task_completed':
          setLogs(prev => [...prev, { type: 'success', text: '任务全部完成！' }])
          fetchTask()
          break
        case 'task_error':
          setLogs(prev => [...prev, { type: 'error', text: `任务失败: ${data.error}` }])
          fetchTask()
          break
        case 'notification':
          setLogs(prev => [...prev, { type: 'notify', text: data.message }])
          break
        case 'progress':
          setLogs(prev => [...prev, { type: 'progress', text: data.stage || '' }])
          break
        case 'chunk':
          // Raw text chunk from agent loop
          break
        case 'heartbeat':
          break
      }
    }

    connectSSE()
    return () => {
      cancelled = true
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [bookId, taskId, fetchTask])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Control handlers
  const handlePause = async () => {
    try { await api.pauseTask(bookId, taskId) } catch (e) { alert(e.message) }
  }
  const handleResume = async () => {
    try { await api.resumeTask(bookId, taskId) } catch (e) { alert(e.message) }
  }
  const handleCancel = async () => {
    if (!confirm('确认取消此任务？')) return
    try { await api.cancelTask(bookId, taskId) } catch (e) { alert(e.message) }
  }
  const handleRetry = async () => {
    try { await api.retryTask(bookId, taskId) } catch (e) { alert(e.message) }
  }

  const handleAuditMode = async (mode) => {
    try { await api.setAuditMode(bookId, taskId, mode) } catch (e) { alert(e.message) }
  }

  if (loading) {
    return (
      <div className="task-progress-panel">
        <div className="loading">加载中...</div>
      </div>
    )
  }

  if (!task) {
    return <div className="task-progress-panel"><div className="error">任务不存在</div></div>
  }

  const progress = task.progress || {}
  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0
  const isRunning = task.status === 'running'
  const isPaused = task.status === 'paused'
  const isFailed = task.status === 'failed'

  return (
    <div className="task-progress-panel" style={{
      padding: '16px', background: '#1a1a2e', borderRadius: '12px',
      color: '#e0e0e0', maxHeight: '80vh', overflow: 'auto',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>
          <StatusIcon status={task.status} /> {task.label}
        </h3>
        {onClose && <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '18px' }}><Icon name="x" size={16} /></button>}
      </div>

      {/* Status badge */}
      <div style={{ marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
        <span style={{
          padding: '2px 10px', borderRadius: '12px', fontSize: '12px',
          background: isRunning ? '#2d5a27' : isPaused ? '#5a4a27' : isFailed ? '#5a2727' : '#2a2a3e',
        }}>
          {task.status}
        </span>
        <span style={{ fontSize: '12px', color: '#888' }}>
          {task.audit_mode && `审核模式: ${task.audit_mode}`}
        </span>
        {task.metadata?.plan_summary && (
          <span style={{ fontSize: '11px', color: '#666' }}>{task.metadata.plan_summary}</span>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
          <span>进度 {progress.completed}/{progress.total} 步骤</span>
          <span>{pct}%</span>
        </div>
        <div style={{ height: '8px', background: '#2a2a3e', borderRadius: '4px', overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${pct}%`, background: '#4CAF50',
            transition: 'width 0.3s ease',
          }} />
        </div>
        {progress.current_label && (
          <div style={{ fontSize: '11px', color: '#888', marginTop: '4px' }}>
            当前: {progress.current_label}
          </div>
        )}
      </div>

      {/* Steps list */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '13px', fontWeight: 'bold', marginBottom: '8px' }}>步骤列表</div>
        {task.steps?.map((step, i) => (
          <div key={step.id} style={{
            padding: '6px 8px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '8px',
            background: i === task.current_step_index ? '#2a2a3e' : 'transparent',
            borderRadius: '4px', marginBottom: '2px',
          }}>
            <StatusIcon status={step.status} size={12} />
            <span style={{ flex: 1 }}>{step.label}</span>
            <span style={{ color: '#666', fontSize: '11px' }}>{step.type}</span>
            {step.error && <span style={{ color: '#f44', fontSize: '11px' }}>{step.error?.slice(0, 50)}</span>}
          </div>
        ))}
      </div>

      {/* Log output */}
      <div style={{
        background: '#0d0d1a', borderRadius: '8px', padding: '8px',
        maxHeight: '200px', overflow: 'auto', fontSize: '11px', fontFamily: 'monospace',
      }}>
        {logs.map((log, i) => (
          <div key={i} style={{
            color: log.type === 'error' ? '#f44' : log.type === 'success' ? '#4f4' :
                   log.type === 'notify' ? '#fa0' : log.type === 'progress' ? '#88f' : '#ccc',
            padding: '1px 0',
          }}>
            {log.text}
          </div>
        ))}
        <div ref={logsEndRef} />
        {logs.length === 0 && <div style={{ color: '#555' }}>等待日志输出...</div>}
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
        {isRunning && (
          <button onClick={handlePause} style={btnStyle('#5a4a27')}><Icon name="pause" size={12} className="inline mr-1" /> 暂停</button>
        )}
        {isPaused && (
          <button onClick={handleResume} style={btnStyle('#2d5a27')}><Icon name="play" size={12} className="inline mr-1" /> 恢复</button>
        )}
        {(isRunning || isPaused || task.status === 'pending') && (
          <button onClick={handleCancel} style={btnStyle('#5a2727')}><Icon name="x" size={12} className="inline mr-1" /> 取消</button>
        )}
        {isFailed && (
          <button onClick={handleRetry} style={btnStyle('#2a4a5a')}><Icon name="refresh" size={12} className="inline mr-1" /> 重试</button>
        )}

        {/* Audit mode selector */}
        <select
          value={task.audit_mode || 'soft'}
          onChange={(e) => handleAuditMode(e.target.value)}
          style={{
            background: '#2a2a3e', color: '#e0e0e0', border: '1px solid #444',
            borderRadius: '4px', padding: '4px 8px', fontSize: '12px',
          }}
        >
          <option value="hard">严格审核</option>
          <option value="soft">柔性审核</option>
          <option value="autonomous">全自动</option>
        </select>
      </div>
    </div>
  )
}

const btnStyle = (bg) => ({
  background: bg, color: '#e0e0e0', border: 'none',
  borderRadius: '6px', padding: '6px 14px', cursor: 'pointer', fontSize: '12px',
})
