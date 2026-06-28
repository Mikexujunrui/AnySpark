import { useState, useMemo } from 'react'
import Modal from './ui/Modal.jsx'
import Icon from './ui/Icon.jsx'
import Toggle from './ui/Toggle.jsx'
import { api } from '../api'

// Subset of backend INTENT_PATTERNS (autopilot.py:82-120) for edit-like detection.
// When the instruction matches these, we suggest routing to BookTransformPanel instead.
const EDIT_KEYWORDS = [
  '替换', '换成', '统一改为', '全部改成', '全书替换', '改名为', '统一称呼',
  '文风', '风格改', '统一风格', '调整文风', '古风', '白话', '文言', 'restyle',
  '批量改', '改这几章', '修改这几章', '改得更', '精修第', '重写第',
]
const EDIT_REGEXES = [
  /把.*章.*改/, /对.*章.*修改/, /全书.*改成/, /全书.*文风/, /全书.*风格/,
  /改成.*风格/, /第.*章.*改/, /让.*更/, /在.*加入/, /每章.*加入/,
]

function looksLikeEdit(instruction) {
  const text = instruction || ''
  if (!text.trim()) return false
  if (EDIT_KEYWORDS.some(kw => text.includes(kw))) return true
  if (EDIT_REGEXES.some(re => re.test(text))) return true
  return false
}

const inputCls = 'w-full bg-zinc-800/80 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent/40 focus:outline-none transition-colors'

function Field({ label, icon, children, hint }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-1.5">
        {icon && <Icon name={icon} size={12} />}
        {label}
        {hint && <span className="text-zinc-600 font-normal">{hint}</span>}
      </label>
      {children}
    </div>
  )
}

export default function AutopilotModal({ bookId, onClose, onTaskCreated, onOpenTransform }) {
  const [instruction, setInstruction] = useState('按大纲写完这本书')
  const [maxChapters, setMaxChapters] = useState(10)
  const [tokenBudget, setTokenBudget] = useState(500000)
  const [unlimitedBudget, setUnlimitedBudget] = useState(false)
  const [auditMode, setAuditMode] = useState('soft')
  const [qualityGate, setQualityGate] = useState('medium')
  const [autoReview, setAutoReview] = useState(true)
  const [autoExtract, setAutoExtract] = useState(true)
  const [confirmBeforeStart, setConfirmBeforeStart] = useState(true)
  const [pauseBetweenChapters, setPauseBetweenChapters] = useState(5)

  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isEditLike = useMemo(() => looksLikeEdit(instruction), [instruction])

  const getBudget = () => (unlimitedBudget ? -1 : tokenBudget)

  const buildPayload = (confirm) => ({
    instruction,
    max_chapters_per_run: maxChapters,
    token_budget: getBudget(),
    auto_review: autoReview,
    auto_extract: autoExtract,
    pause_between_chapters: pauseBetweenChapters,
    confirm_before_start: confirm,
    audit_mode: auditMode,
    quality_gate: qualityGate,
  })

  const handlePreview = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.startAutopilot(bookId, buildPayload(true))
      setPlan(result)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const handleConfirm = async () => {
    if (!plan?.task_id) return
    setLoading(true)
    try {
      await api.confirmAutopilot(bookId, plan.task_id)
      onTaskCreated?.(plan.task_id)
      onClose?.()
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const handleDirectStart = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.startAutopilot(bookId, buildPayload(false))
      onTaskCreated?.(result.task_id)
      onClose?.()
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  // Preview summary of the config that will be sent
  const configPreview = useMemo(() => {
    const parts = [
      `最多 ${maxChapters} 章`,
      unlimitedBudget ? 'Token 无上限' : `预算 ${(tokenBudget / 1000).toFixed(0)}K`,
      `审核 ${auditMode}`,
      `门控 ${qualityGate}`,
    ]
    if (autoReview) parts.push('自动评审')
    if (autoExtract) parts.push('自动提取')
    if (pauseBetweenChapters > 0) parts.push(`章间暂停 ${pauseBetweenChapters}s`)
    return parts.join(' · ')
  }, [maxChapters, tokenBudget, unlimitedBudget, auditMode, qualityGate, autoReview, autoExtract, pauseBetweenChapters])

  return (
    <Modal open={true} onClose={onClose} title="Autopilot 自主写作" size="lg">
      <div className="flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-purple-500/10 border border-purple-500 flex items-center justify-center">
              <Icon name="bot" size={18} className="text-purple-400" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-zinc-100">Autopilot 自主写作</h2>
              <p className="text-xs text-zinc-500 mt-0.5">写新章节 / 多步编排 · 后台执行断线继续</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg p-1.5 transition-colors shrink-0"
            aria-label="关闭"
          >
            <Icon name="x" size={18} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Edit-intent suggestion banner */}
          {isEditLike && onOpenTransform && (
            <div className="flex items-start gap-2.5 rounded-lg bg-amber-500/10 border border-amber-700/40 px-3 py-2.5">
              <Icon name="lightbulb" size={14} className="text-amber-400 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-amber-200/90 leading-relaxed">
                  此指令针对<b>已有章节的修改</b>。<b>全书变换</b>更快且支持预览（不实改），可能更合适。
                </p>
                <button
                  onClick={onOpenTransform}
                  className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-amber-300 hover:text-amber-200 underline underline-offset-2"
                >
                  <Icon name="layers" size={11} />
                  打开全书变换
                </button>
              </div>
            </div>
          )}

          {/* Instruction */}
          <Field label="写作指令" icon="message-circle">
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="例如：按大纲写完这本书 / 续写后5章"
              rows={2}
              className={`${inputCls} resize-none`}
            />
          </Field>

          {/* Resource control */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-2.5">
              <Icon name="hourglass" size={12} />
              资源控制
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="最多写几章" icon="calendar">
                <input
                  type="number"
                  value={maxChapters}
                  onChange={(e) => setMaxChapters(+e.target.value)}
                  className={inputCls}
                  min={1} max={50}
                />
              </Field>
              <Field label="Token 预算" icon="bar-chart">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={tokenBudget}
                    onChange={(e) => setTokenBudget(+e.target.value)}
                    disabled={unlimitedBudget}
                    className={`${inputCls} flex-1 disabled:opacity-30`}
                    min={100000} step={100000}
                  />
                  <button
                    type="button"
                    onClick={() => setUnlimitedBudget(v => !v)}
                    className={`shrink-0 rounded-lg px-2 py-2 text-[11px] font-medium border transition-colors ${
                      unlimitedBudget
                        ? 'bg-accent/15 text-accent border-accent/40'
                        : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:text-zinc-200'
                    }`}
                  >
                    无上限
                  </button>
                </div>
              </Field>
            </div>
          </div>

          {/* Quality control */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-2.5">
              <Icon name="shield" size={12} />
              质量控制
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="审核模式" icon="clipboard-list">
                <select
                  value={auditMode}
                  onChange={(e) => setAuditMode(e.target.value)}
                  className={inputCls}
                >
                  <option value="hard">严格 — 每章需确认</option>
                  <option value="soft">柔性 — 质量低时暂停</option>
                  <option value="autonomous">全自动 — 仅受预算限制</option>
                </select>
              </Field>
              <Field label="质量门控" icon="award">
                <select
                  value={qualityGate}
                  onChange={(e) => setQualityGate(e.target.value)}
                  className={inputCls}
                >
                  <option value="low">低 (≥5分)</option>
                  <option value="medium">中 (≥7分)</option>
                  <option value="high">高 (≥8.5分)</option>
                </select>
              </Field>
            </div>
          </div>

          {/* Toggles */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-2.5">
              <Icon name="settings" size={12} />
              自动化开关
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              <Toggle
                checked={autoReview}
                onChange={setAutoReview}
                label="自动评审"
                hint="每章写完打分检查"
              />
              <Toggle
                checked={autoExtract}
                onChange={setAutoExtract}
                label="自动提取知识"
                hint="人物/地点/伏笔入库"
              />
              <Toggle
                checked={confirmBeforeStart}
                onChange={setConfirmBeforeStart}
                label="启动前预览计划"
                hint="先看计划再执行"
              />
              <div className="flex items-center gap-2.5">
                <span className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-accent">
                  <span className="inline-block h-3.5 w-3.5 rounded-full bg-white shadow" style={{ transform: 'translateX(18px)' }} />
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-zinc-300">章间暂停</span>
                  <input
                    type="number"
                    value={pauseBetweenChapters}
                    onChange={(e) => setPauseBetweenChapters(Math.max(0, +e.target.value || 0))}
                    min={0} max={300}
                    className="w-14 bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-xs text-zinc-100 focus:border-accent focus:outline-none tabular-nums"
                  />
                  <span className="text-[11px] text-zinc-500">秒</span>
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-900/20 border border-red-800/50 px-3 py-2">
              <Icon name="alert-circle" size={14} className="text-red-400 mt-0.5 shrink-0" />
              <p className="text-xs text-red-300">{error}</p>
            </div>
          )}

          {/* Plan preview */}
          {plan && (
            <div className="rounded-lg bg-emerald-900/15 border border-emerald-700/40 px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-300 mb-2">
                <Icon name="check-circle" size={13} />
                执行计划预览 · 共 {plan.total_steps} 步
              </div>
              <p className="text-xs text-emerald-100/80 mb-2 leading-relaxed">{plan.plan_summary}</p>
              {plan.chapters?.length > 0 && (
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {plan.chapters.map((ch, i) => (
                    <div key={i} className="text-[11px] text-zinc-400 flex items-center gap-1.5">
                      <Icon name="file-text" size={10} className="text-zinc-600" />
                      第{ch.index}章 {ch.title}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer: config preview + actions */}
        <div className="shrink-0 border-t border-zinc-800 px-5 py-3 space-y-2.5 bg-zinc-900/50">
          <div className="rounded-lg bg-zinc-950/60 border border-zinc-800 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
              <Icon name="activity" size={11} />
              当前配置
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed font-mono break-all">{configPreview}</p>
          </div>

          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              className="px-3.5 py-2 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              取消
            </button>
            {plan ? (
              <button
                onClick={handleConfirm}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg transition-colors active:scale-95"
              >
                <Icon name="check" size={13} />
                {loading ? '...' : '确认启动'}
              </button>
            ) : (
              <>
                <button
                  onClick={handlePreview}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-zinc-100 rounded-lg transition-colors"
                >
                  <Icon name="search" size={13} />
                  {loading ? '...' : '预览计划'}
                </button>
                <button
                  onClick={handleDirectStart}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-accent hover:bg-accent-hover disabled:opacity-50 text-white rounded-lg transition-colors active:scale-95 shadow-sm"
                >
                  <Icon name="play" size={13} />
                  {loading ? '...' : '直接启动'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
