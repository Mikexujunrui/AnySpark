import { useState, useEffect } from 'react'
import Icon from './ui/Icon'
import { api } from '../api'

export default function SupervisorBadge({ bookId, onOpenTasks }) {
  const [status, setStatus] = useState(null)
  const [tasks, setTasks] = useState([])
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const sup = await api.getSupervisorStatus()
        setStatus(sup)
        if (bookId) {
          const t = await api.getTasks(bookId, 'running')
          setTasks(t)
        }
      } catch {
        // Ignore — supervisor may not be running
      }
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [bookId])

  const runningCount = tasks.length
  const supRunning = status?.running ?? false

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          background: runningCount > 0 ? '#2d5a27' : '#2a2a3e',
          color: '#e0e0e0', border: '1px solid #444',
          borderRadius: '16px', padding: '4px 12px',
          cursor: 'pointer', fontSize: '12px', display: 'flex',
          alignItems: 'center', gap: '6px',
        }}
      >
        <span style={{
          width: '8px', height: '8px', borderRadius: '50%',
          background: supRunning ? '#4f4' : '#f44',
          display: 'inline-block',
        }} />
        {runningCount > 0 ? `${runningCount} 任务运行中` : '后台空闲'}
      </button>

      {expanded && (
        <div style={{
          position: 'absolute', top: '100%', right: 0, marginTop: '4px',
          background: '#1a1a2e', border: '1px solid #333', borderRadius: '12px',
          padding: '12px', minWidth: '280px', zIndex: 100, boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 'bold' }}>后台任务</span>
            <button onClick={() => setExpanded(false)} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}><Icon name="x" size={14} /></button>
          </div>

          <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px' }}>
            监督进程: {supRunning ? '运行中' : '已停止'}
            {status && ` | 巡检间隔 ${status.check_interval}s`}
          </div>

          {runningCount === 0 ? (
            <div style={{ fontSize: '12px', color: '#666' }}>当前没有运行中的任务</div>
          ) : (
            tasks.map(t => (
              <div key={t.id} style={{
                padding: '6px 8px', background: '#0d0d1a', borderRadius: '6px',
                marginBottom: '4px', fontSize: '12px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t.label}</span>
                  <span style={{ color: '#888' }}>{t.status}</span>
                </div>
                {t.progress && (
                  <div style={{ fontSize: '11px', color: '#666', marginTop: '2px' }}>
                    {t.progress.completed}/{t.progress.total} 步骤
                  </div>
                )}
              </div>
            ))
          )}

          <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
            <button
              onClick={() => { onOpenTasks?.(); setExpanded(false) }}
              style={{
                background: '#2a4a5a', color: '#e0e0e0', border: 'none',
                borderRadius: '6px', padding: '4px 10px', cursor: 'pointer', fontSize: '11px',
                flex: 1,
              }}
            >
              查看所有任务
            </button>
            <button
              onClick={async () => {
                try { await api.triggerRecovery(); alert('恢复已触发') } catch (e) { alert(e.message) }
              }}
              style={{
                background: '#333', color: '#e0e0e0', border: 'none',
                borderRadius: '6px', padding: '4px 10px', cursor: 'pointer', fontSize: '11px',
              }}
            >
              恢复任务
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
