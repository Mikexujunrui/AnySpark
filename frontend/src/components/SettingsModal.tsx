// SettingsModal — V4 适配版设置
// 模型（/api/models 注册表 + 激活）/ 档位（/api/agency）/ 记忆（/api/manual）
import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import Modal from './ui/Modal'
import Toggle from './ui/Toggle'

interface ModelItem { id: string; name: string; base_url?: string; model?: string; context_window?: number; is_active?: boolean; thinking?: string | null; temperature?: number | null }
interface AgencyLevel { id: string; name: string; description: string; temperature: number; order: number; is_default?: boolean }
interface ManualEntry { id: string; content: string; category?: string; locked?: boolean; activity?: string }

const THINKING_LEVELS = ['off', 'low', 'medium', 'high', 'xhigh', 'max'] as const

export default function SettingsModal({ onClose, onModeChanged, bookId }: { onClose: () => void; onModeChanged?: (mode: string) => void; bookId?: string }) {
  const [tab, setTab] = useState('models')
  const [models, setModels] = useState<ModelItem[]>([])
  const [activeModel, setActiveModel] = useState<string>('')
  const [agency, setAgency] = useState<AgencyLevel[]>([])
  const [currentAgency, setCurrentAgency] = useState<AgencyLevel | null>(null)
  const [manual, setManual] = useState<ManualEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  // 模型注册表单
  const [showAddModel, setShowAddModel] = useState(false)
  const [modelForm, setModelForm] = useState({ name: '', model: '', base_url: '', api_key: '', thinking: 'medium', max_tokens: 16384 })
  const [savingModel, setSavingModel] = useState(false)

  const showToast = useCallback((msg: string, _type?: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }, [])

  const loadModels = useCallback(async () => {
    try {
      const res = await fetch('/api/models')
      const data = await res.json()
      setModels(data.models || [])
      setActiveModel(data.active_id || '')
    } catch { setError('加载模型失败') }
  }, [])

  const loadAgency = useCallback(async () => {
    try {
      const res = await fetch('/api/agency')
      const data = await res.json()
      setAgency(data.levels || [])
      setCurrentAgency(data.current || null)
    } catch { /* 静默 */ }
  }, [])

  const loadManual = useCallback(async () => {
    try {
      const res = await fetch('/api/manual')
      const data = await res.json()
      setManual(Array.isArray(data) ? data : [])
    } catch { /* 静默 */ }
  }, [])

  useEffect(() => {
    async function init() {
      setLoading(true)
      await Promise.all([loadModels(), loadAgency(), loadManual()])
      setLoading(false)
    }
    init()
  }, [loadModels, loadAgency, loadManual])

  async function activateModel(id: string) {
    try {
      await fetch(`/api/models/${encodeURIComponent(id)}/activate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      setActiveModel(id)
      showToast('模型已激活')
      onModeChanged?.(id)
    } catch { showToast('激活失败', 'error') }
  }

  // 注册/更新模型（POST /api/models，含思考强度）
  async function registerModel() {
    if (!modelForm.name.trim() || !modelForm.model.trim()) {
      showToast('模型名与模型标识必填', 'error')
      return
    }
    setSavingModel(true)
    try {
      const res = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: modelForm.name.trim(),
          model: modelForm.model.trim(),
          base_url: modelForm.base_url.trim() || undefined,
          api_key: modelForm.api_key.trim() || undefined,
          thinking: modelForm.thinking,
          max_tokens: modelForm.max_tokens || undefined,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      showToast('模型已注册')
      setModelForm({ name: '', model: '', base_url: '', api_key: '', thinking: 'medium', max_tokens: 16384 })
      setShowAddModel(false)
      await loadModels()
    } catch (e) {
      showToast(e instanceof Error ? e.message : '注册失败', 'error')
    }
    setSavingModel(false)
  }

  // 删除模型（DELETE /api/models/{id}；激活中的模型由后端决定是否允许）
  async function deleteModel(id: string, name: string) {
    if (!window.confirm(`删除模型「${name}」？此操作不可恢复。`)) return
    try {
      const res = await fetch(`/api/models/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      showToast('模型已删除')
      await loadModels()
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除失败', 'error')
    }
  }

  async function setAgencyLevel(levelId: string) {
    try {
      const res = await fetch('/api/agency', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level_id: levelId }) })
      const data = await res.json()
      setCurrentAgency(data || currentAgency)
      showToast('档位已切换')
    } catch { showToast('切换失败', 'error') }
  }

  async function toggleLock(id: string, locked: boolean) {
    try {
      await fetch(`/api/manual/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ locked: !locked }) })
      setManual(prev => prev.map(m => m.id === id ? { ...m, locked: !locked } : m))
    } catch { /* 静默 */ }
  }

  const tabs = [
    { key: 'models', label: '模型', icon: 'database' },
    { key: 'agency', label: '档位', icon: 'zap' },
    { key: 'about', label: '关于', icon: 'info' },
  ]

  return (
    <Modal open onClose={onClose} title="设置" size="lg">
      <div className="flex border-b border-zinc-800 px-5 shrink-0">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              tab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Icon name={t.icon} size={12} /> {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {error && <div className="mb-3 px-3 py-2 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded">{error}</div>}
        {loading ? (
          <div className="flex items-center justify-center py-10 text-zinc-500 text-sm gap-2">
            <div className="w-5 h-5 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
            加载中...
          </div>
        ) : (
          <>
            {/* ── Tab: 模型 ── */}
            {tab === 'models' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-zinc-500">模型注册表（注册/删除/思考强度）</p>
                  <button
                    onClick={() => setShowAddModel(!showAddModel)}
                    className="text-[11px] px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded"
                  >
                    {showAddModel ? '取消' : '+ 注册模型'}
                  </button>
                </div>

                {/* 注册表单 */}
                {showAddModel && (
                  <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800 space-y-2">
                    <input value={modelForm.name} onChange={e => setModelForm({ ...modelForm, name: e.target.value })} placeholder="显示名（如：DeepSeek Pro）" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600" />
                    <input value={modelForm.model} onChange={e => setModelForm({ ...modelForm, model: e.target.value })} placeholder="模型标识（如：deepseek-v4-pro）" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600" />
                    <input value={modelForm.base_url} onChange={e => setModelForm({ ...modelForm, base_url: e.target.value })} placeholder="API 端点（可选，默认 DashScope）" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600" />
                    <input value={modelForm.api_key} onChange={e => setModelForm({ ...modelForm, api_key: e.target.value })} placeholder="API Key（可选，默认环境变量）" type="password" className="w-full bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-sky-500 placeholder-zinc-600" />
                    <div className="flex items-center gap-2">
                      <select value={modelForm.thinking} onChange={e => setModelForm({ ...modelForm, thinking: e.target.value })} className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1.5 rounded border border-zinc-700">
                        {THINKING_LEVELS.map(t => <option key={t} value={t}>{t === 'off' ? 'off（不思考）' : t}</option>)}
                      </select>
                      <input value={modelForm.max_tokens} onChange={e => setModelForm({ ...modelForm, max_tokens: Number(e.target.value) || 0 })} placeholder="max_tokens" type="number" className="w-28 bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none" />
                      <button onClick={registerModel} disabled={savingModel} className="ml-auto text-[11px] px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded disabled:opacity-50">
                        {savingModel ? '注册中...' : '注册'}
                      </button>
                    </div>
                  </div>
                )}

                {models.length === 0 && <p className="text-sm text-zinc-600">暂无模型</p>}
                {models.map(m => (
                  <div key={m.id} className="flex items-center gap-3 px-3 py-2.5 bg-zinc-900/50 rounded-lg border border-zinc-800">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-zinc-200 truncate">{m.name}</span>
                        {m.is_active && <span className="text-[10px] px-1.5 py-0.5 bg-emerald-900/40 text-emerald-400 rounded">激活</span>}
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5 truncate">
                        {m.model}{m.context_window ? ` · ${Math.round(m.context_window / 10000) / 100}M 上下文` : ''}
                        {m.thinking ? ` · 思考:${m.thinking}` : ''}
                        {m.temperature != null ? ` · temp:${m.temperature}` : ''}
                      </div>
                    </div>
                    {!m.is_active && (
                      <button onClick={() => activateModel(m.id)} className="text-xs px-2.5 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded shrink-0">
                        激活
                      </button>
                    )}
                    <button onClick={() => deleteModel(m.id, m.name)} className="text-zinc-600 hover:text-red-400 p-1 rounded shrink-0" title="删除模型">
                      <Icon name="trash" size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* ── Tab: 档位 ── */}
            {tab === 'agency' && (
              <div className="space-y-2">
                <p className="text-xs text-zinc-500 mb-3">能动档位：AI 写作自由度（0=只听写 → 4=自主发挥）</p>
                {agency.length === 0 && <p className="text-sm text-zinc-600">暂无档位</p>}
                {agency.map(lv => (
                  <button
                    key={lv.id}
                    onClick={() => setAgencyLevel(lv.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors ${
                      currentAgency?.id === lv.id ? 'bg-sky-900/30 border-sky-700/60' : 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${currentAgency?.id === lv.id ? 'text-sky-300' : 'text-zinc-200'}`}>{lv.name}</span>
                      <span className="text-[10px] text-zinc-500">temp {lv.temperature}</span>
                    </div>
                    {lv.description && <p className="text-[11px] text-zinc-500 mt-0.5">{lv.description}</p>}
                  </button>
                ))}
              </div>
            )}

            {/* ── Tab: 记忆系统（心智）── */}
            {tab === 'memory' && (
              <div className="space-y-2">
                <p className="text-xs text-zinc-500 mb-3">心智条目：AI 对你的写作偏好的记忆（用户主权，可锁定）</p>
                {manual.length === 0 && <p className="text-sm text-zinc-600">暂无心智条目</p>}
                {manual.map(entry => (
                  <div key={entry.id} className="px-3 py-2.5 bg-zinc-900/50 rounded-lg border border-zinc-800">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm text-zinc-200 flex-1">{entry.content}</p>
                      <button onClick={() => toggleLock(entry.id, !!entry.locked)} className={`shrink-0 text-[11px] px-2 py-0.5 rounded ${entry.locked ? 'bg-yellow-900/40 text-yellow-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
                        {entry.locked ? '已锁定' : '锁定'}
                      </button>
                    </div>
                    <div className="text-[10px] text-zinc-600 mt-1 flex gap-2">
                      <span>{entry.category || 'style'}</span>
                      {entry.activity && <span>活跃度: {entry.activity}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── Tab: 关于 ── */}
            {tab === 'about' && (
              <div className="space-y-3">
                <div className="px-3 py-3 bg-zinc-900/50 rounded-lg border border-zinc-800">
                  <p className="text-sm text-zinc-200 font-medium">AnySpark v4</p>
                  <p className="text-[11px] text-zinc-500 mt-1">小说特化版 AI 写作工作台——旧壳配新芯（feat/shell-port）</p>
                  <p className="text-[11px] text-zinc-600 mt-2">
                    能力：心智模型（偏好记忆）/ 知识图谱 / 特化工具 / 多项目 / 互动推演 / 评审团
                  </p>
                </div>
                <div className="px-3 py-3 bg-zinc-900/50 rounded-lg border border-zinc-800">
                  <p className="text-sm text-zinc-200 font-medium">快捷键</p>
                  <div className="text-[11px] text-zinc-500 mt-1 space-y-0.5">
                    <p>Ctrl+1..N — 切换面板</p>
                    <p>Ctrl+K — 命令面板</p>
                    <p>Ctrl+. — 会话管理</p>
                    <p>分屏时右键 tab — 设为次面板</p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {toast && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg shadow-lg">
          {toast}
        </div>
      )}
    </Modal>
  )
}
