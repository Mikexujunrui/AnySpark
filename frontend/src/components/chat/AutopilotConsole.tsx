import { useState, useEffect, useRef } from 'react'
import { api } from '../../api'
import Icon from '../ui/Icon'

const STEP_STATUS_COLORS = {
  pending: 'text-zinc-600',
  running: 'text-blue-400',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  skipped: 'text-zinc-500',
}

function StepStatusIcon({ status }) {
  const cls = STEP_STATUS_COLORS[status] || 'text-zinc-600'
  if (status === 'running') return <Icon name="loader" size={12} className={`${cls} animate-spin`} />
  if (status === 'completed') return <Icon name="check-circle" size={12} className={cls} />
  if (status === 'failed') return <Icon name="x" size={12} className={cls} strokeWidth={3} />
  if (status === 'skipped') return <Icon name="chevron-right" size={12} className={cls} />
  return <Icon name="circle" size={12} className={cls} />
}

export default function AutopilotConsole({ state, taskId, bookId, sessionId: _sessionId, onPause, onResume, onCancel, onSkip, onClose }) {
  const [detail, setDetail] = useState(null)
  const [expandedStep, setExpandedStep] = useState(null)
  const logsRef = useRef(null)

  useEffect(() => {
    if (!taskId) return
    api.getTask(bookId, taskId).then(setDetail).catch(() => {})
    const interval = setInterval(() => {
      api.getTask(bookId, taskId).then(setDetail).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [bookId, taskId])

  useEffect(() => {
    logsRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [detail?.progress])

  const progress = detail?.progress || {}
  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0
  const isRunning = state?.status === 'running'
  const isPaused = state?.status === 'paused'
  const isFailed = state?.status === 'failed'

  const statusColors = {
    running: '#2d5a27',
    paused: '#5a4a27',
    completed: '#2a4a5a',
    failed: '#5a2727',
    cancelled: '#333',
  }

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ color: '#e0e0e0' }}>
      {/* Header */}
      <div className="shrink-0 p-3 border-b border-zinc-800" style={{ background: '#1a1a2e' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-bold flex items-center gap-1.5">
            <Icon name="bot" size={14} className="text-purple-400" />
            Autopilot 控制台
          </span>
          {onClose && (
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-sm" style={{ background: 'none', border: 'none' }}>
              最小化
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs mb-2">
          <span style={{
            padding: '1px 8px', borderRadius: '10px', fontSize: '11px',
            background: statusColors[state?.status] || '#333',
          }}>
            {state?.status || 'pending'}
          </span>
          <span className="text-zinc-500">
            {state?.audit_mode && `审核: ${state.audit_mode}`}
          </span>
        </div>

        {/* Progress bar */}
        <div className="mb-1">
          <div className="flex justify-between text-xs text-zinc-500 mb-1">
            <span>{progress.completed}/{progress.total} 步骤</span>
            <span>{pct}%</span>
          </div>
          <div style={{ height: '6px', background: '#2a2a3e', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: `${pct}%`, background: '#4CAF50',
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
        {progress.current_label && (
          <div className="text-xs text-zinc-500 truncate">当前: {progress.current_label}</div>
        )}
      </div>

      {/* Step Timeline */}
      <div className="flex-1 overflow-y-auto p-3" style={{ background: '#0d0d1a' }}>
        {detail?.steps?.map((step, i) => {
          const isActive = i === detail.current_step_index
          const isExpanded = expandedStep === step.id
          const hasResult = step.result && Object.keys(step.result).length > 0

          return (
            <div key={step.id} className="mb-2">
              <div
                onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                className="flex items-center gap-2 p-2 rounded cursor-pointer text-xs"
                style={{
                  background: isActive ? '#2a2a3e' : 'transparent',
                  borderLeft: isActive ? '2px solid #4CAF50' : '2px solid transparent',
                }}
              >
                <StepStatusIcon status={step.status} />
                <span className="flex-1 truncate">{step.label}</span>
                <span className="text-zinc-600">{step.type}</span>
                {step.error && <span className="text-red-400 text-xs" title={step.error}>⚠️</span>}
                {hasResult && <span className="text-zinc-500">▾</span>}
              </div>

              {isExpanded && hasResult && (
                <div className="ml-6 p-2 rounded text-xs text-zinc-400" style={{ background: '#1a1a2e' }}>
                  {step.result.text && (
                    <div className="mb-1 max-h-32 overflow-y-auto whitespace-pre-wrap">
                      {step.result.text?.slice(0, 500)}
                    </div>
                  )}
                  {step.result.quality && (
                    <div className="flex gap-2 text-xs">
                      <span style={{ color: step.result.quality.passed ? '#4f4' : '#f44' }}>
                        评分: {step.result.quality.score?.toFixed(1)}
                      </span>
                      {step.result.quality.summary && (
                        <span className="text-zinc-500">{step.result.quality.summary?.slice(0, 100)}</span>
                      )}
                    </div>
                  )}
                  {step.result.metrics && (
                    <div className="text-zinc-600">
                      LLM调用: {step.result.metrics.llm_calls} | 工具: {step.result.metrics.tool_calls}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
        <div ref={logsRef} />
      </div>

      {/* Stats footer */}
      {detail?.metadata && (
        <div className="shrink-0 p-3 border-t border-zinc-800 text-xs text-zinc-500" style={{ background: '#1a1a2e' }}>
          <div className="flex justify-between">
            <span>Token: {((detail.metadata.tokens_used || 0) / 1000).toFixed(0)}k / {((detail.metadata.token_budget || 0) / 1000).toFixed(0)}k</span>
            <span>章节: {detail.metadata.chapters_completed || 0}/{detail.metadata.total_chapters || 0}</span>
            <span>Replan: {detail.metadata.replan_count || 0}/{detail.metadata.max_replans || 3}</span>
          </div>
        </div>
      )}

      {/* Control Bar */}
      <div className="shrink-0 p-3 border-t border-zinc-800 flex gap-2 flex-wrap" style={{ background: '#1a1a2e' }}>
        {isRunning && (
          <button onClick={onPause} style={btnStyle('#5a4a27')}>
            <Icon name="stop" size={11} className="mr-1" />暂停
          </button>
        )}
        {isPaused && (
          <button onClick={onResume} style={btnStyle('#2d5a27')}>
            <Icon name="play" size={11} className="mr-1" />恢复
          </button>
        )}
        {(isRunning || isPaused || state?.status === 'pending') && (
          <>
            <button onClick={onSkip} style={btnStyle('#2a4a5a')}>
              <Icon name="chevron-right" size={11} className="mr-1" />跳过
            </button>
            <button onClick={onCancel} style={btnStyle('#5a2727')}>
              <Icon name="x" size={11} className="mr-1" strokeWidth={3} />取消
            </button>
          </>
        )}
        {isFailed && (
          <button onClick={onResume} style={btnStyle('#2a4a5a')}>
            <Icon name="refresh" size={11} className="mr-1" />重试
          </button>
        )}
      </div>
    </div>
  )
}

const btnStyle = (bg) => ({
  background: bg, color: '#e0e0e0', border: 'none',
  borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', fontSize: '11px',
})