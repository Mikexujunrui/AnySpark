// SettingsModal — V4 适配版设置
// 模型（/api/models 注册表 + 激活）/ 档位（/api/agency）/ 记忆（/api/manual）
import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import Modal from './ui/Modal'
import Toggle from './ui/Toggle'

interface ModelItem { id: string; name: string; base_url?: string; model?: string; context_window?: number; is_active?: boolean }
interface AgencyLevel { id: string; name: string; description: string; temperature: number; order: number; is_default?: boolean }
interface ManualEntry { id: string; content: string; category?: string; locked?: boolean; activity?: string }

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
    { key: 'memory', label: '记忆系统', icon: 'brain' },
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
              <div className="space-y-2">
                <p className="text-xs text-zinc-500 mb-3">模型注册表（V4 多模型：1M 上下文 deepseek-v4 系列）</p>
                {models.length === 0 && <p className="text-sm text-zinc-600">暂无模型</p>}
                {models.map(m => (
                  <div key={m.id} className="flex items-center gap-3 px-3 py-2.5 bg-zinc-900/50 rounded-lg border border-zinc-800">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-zinc-200 truncate">{m.name}</span>
                        {m.is_active && <span className="text-[10px] px-1.5 py-0.5 bg-emerald-900/40 text-emerald-400 rounded">激活</span>}
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{m.model}{m.context_window ? ` · ${Math.round(m.context_window / 10000) / 100}M 上下文` : ''}</div>
                    </div>
                    {!m.is_active && (
                      <button onClick={() => activateModel(m.id)} className="text-xs px-2.5 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded shrink-0">
                        激活
                      </button>
                    )}
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
