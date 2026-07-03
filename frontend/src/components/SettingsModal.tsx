import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import Modal from './ui/Modal'
import Toggle from './ui/Toggle'

const MODE_INFO = {
  quality: { label: 'Quality', desc: '所有任务使用 Pro 模型，最高质量输出', icon: 'star', color: 'amber' },
  split:   { label: 'Split',   desc: '创意任务用 Pro，其他用 Flash', icon: 'layers', color: 'blue' },
  flash:   { label: 'Flash',   desc: '所有任务使用 Flash 模型，省钱快速', icon: 'zap', color: 'emerald' },
  custom:  { label: 'Custom',  desc: '按任务类型自定义分配 Pro/Flash', icon: 'settings', color: 'purple' },
}

const TASK_LABELS = {
  writing: '写作', planning: '规划', extraction: '提取',
  editing: '编辑', general: '通用', research: '调研',
}

const PROVIDER_TYPE_LABELS = {
  openai: 'OpenAI 兼容',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
}

export default function SettingsModal({ onClose, onModeChanged, bookId }: { onClose: () => void; onModeChanged?: (mode: string) => void; bookId?: string }) {
  const [tab, setTab] = useState('providers')
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  // Update check
  const [updateStatus, setUpdateStatus] = useState<{ current_version: string; update_check_enabled: boolean } | null>(null)
  const [updateResult, setUpdateResult] = useState<any>(null)
  const [checking, setChecking] = useState(false)

  // Provider form
  const [editingProvider, setEditingProvider] = useState(null)
  const [providerForm, setProviderForm] = useState({
    id: '', name: '', type: 'openai', api_key: '', base_url: '', models: '',
  })
  const [testing, setTesting] = useState(null)

  // Custom map
  const [customMap, setCustomMap] = useState({})

  // Book override state
  const [bookOverrides, setBookOverrides] = useState(null)
  const [bookOverrideForm, setBookOverrideForm] = useState({
    mode: '', slot_pro_provider_id: '', slot_pro_model: '',
    slot_flash_provider_id: '', slot_flash_model: '',
  })

  const showToast = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }, [])

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings')
      const data = await res.json()
      setSettings(data)
      setCustomMap(data.custom_map || {})
      setLoading(false)
    } catch (e) {
      setError('加载设置失败')
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSettings() }, [fetchSettings])

  // Load book overrides when bookId changes
  useEffect(() => {
    if (bookId) {
      fetch(`/api/books/${bookId}/settings`)
        .then(r => r.json())
        .then(data => {
          if (data.overrides) {
            setBookOverrides(data.overrides)
            setBookOverrideForm(data.overrides)
          } else {
            setBookOverrides(null)
            setBookOverrideForm({ mode: '', slot_pro_provider_id: '', slot_pro_model: '', slot_flash_provider_id: '', slot_flash_model: '' })
          }
        })
        .catch(() => {})
    }
  }, [bookId])

  // ── Update check ──
  useEffect(() => {
    fetch('/api/update/status')
      .then(r => r.json())
      .then(data => setUpdateStatus(data))
      .catch(() => {})
  }, [])

  async function doCheckUpdate() {
    setChecking(true)
    setUpdateResult(null)
    try {
      const res = await fetch('/api/update/check')
      const data = await res.json()
      setUpdateResult(data)
    } catch (e) {
      showToast('检查更新失败')
    }
    setChecking(false)
  }

  async function doToggleUpdateCheck(enabled: boolean) {
    try {
      const res = await fetch('/api/update/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      const data = await res.json()
      setUpdateStatus(prev => prev ? { ...prev, update_check_enabled: data.update_check_enabled } : prev)
      showToast(data.update_check_enabled ? '已开启更新检测' : '已关闭更新检测')
    } catch (e) {
      showToast('切换失败')
    }
  }

  // ── Provider CRUD ──

  function openAddProvider() {
    setEditingProvider(null)
    setProviderForm({ id: '', name: '', type: 'openai', api_key: '', base_url: '', models: '' })
  }

  function openEditProvider(p) {
    setEditingProvider(p.id)
    setProviderForm({
      id: p.id, name: p.name, type: p.type,
      api_key: p.api_key || '', base_url: p.base_url || '',
      models: (p.models || []).join(', '),
    })
  }

  async function saveProvider() {
    setSaving(true)
    try {
      const body = {
        ...providerForm,
        models: providerForm.models.split(',').map(s => s.trim()).filter(Boolean),
      }
      const res = await fetch('/api/settings/providers', {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '保存失败')
      }
      const data = await res.json()
      setSettings(data)
      setEditingProvider(null)
      showToast('Provider 已保存')
    } catch (e) {
      showToast(e.message)
    }
    setSaving(false)
  }

  async function deleteProvider(id) {
    if (!confirm(`确定删除此 Provider？`)) return
    try {
      const res = await fetch(`/api/settings/providers/${id}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
      const data = await res.json()
      setSettings(data)
      showToast('已删除')
    } catch (e) {
      showToast('删除失败')
    }
  }

  async function testProvider(id) {
    setTesting(id)
    try {
      const res = await fetch('/api/settings/test', {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: id }),
      })
      const data = await res.json()
      if (data.success) {
        showToast(`连接成功 (${data.latency_ms}ms): ${data.reply}`)
      } else {
        showToast(`连接失败: ${data.error}`)
      }
    } catch (e) {
      showToast('测试请求失败')
    }
    setTesting(null)
  }

  // ── Book overrides ──

  async function saveBookOverrides() {
    setSaving(true)
    try {
      const res = await fetch(`/api/books/${bookId}/settings`, {
        method: 'PUT',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify(bookOverrideForm),
      })
      if (!res.ok) throw new Error('保存失败')
      const data = await res.json()
      setBookOverrides(data.overrides)
      setSettings(prev => prev ? { ...prev, mode: data.overrides?.mode || prev.mode } : prev)
      onModeChanged?.(data.overrides?.mode || settings?.mode)
      showToast('书籍覆盖已保存')
    } catch (e) {
      showToast(e.message || '保存失败')
    }
    setSaving(false)
  }

  async function resetBookOverrides() {
    setSaving(true)
    try {
      const res = await fetch(`/api/books/${bookId}/settings`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
      if (!res.ok) throw new Error('重置失败')
      setBookOverrides(null)
      setBookOverrideForm({ mode: '', slot_pro_provider_id: '', slot_pro_model: '', slot_flash_provider_id: '', slot_flash_model: '' })
      showToast('已重置为全局设置')
    } catch (e) {
      showToast('重置失败')
    }
    setSaving(false)
  }

  // ── Slots ──

  async function saveSlot(slot, providerId, model) {
    const body: Record<string, any> = {}
    if (slot === 'pro') {
      body.slot_pro_provider_id = providerId
      body.slot_pro_model = model
    } else {
      body.slot_flash_provider_id = providerId
      body.slot_flash_model = model
    }
    try {
      const res = await fetch('/api/settings/slots', {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setSettings(data)
      showToast('槽位已更新')
    } catch (e) {
      showToast('更新失败')
    }
  }

  // ── Mode ──

  async function switchMode(mode) {
    try {
      const body = { mode }
      if (mode === 'custom') (body as any).custom_map = customMap
      const res = await fetch('/api/settings/mode', {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setSettings(data)
      onModeChanged?.(mode)
      showToast(`已切换到 ${MODE_INFO[mode]?.label || mode} 模式`)
    } catch (e) {
      showToast('切换失败')
    }
  }

  async function saveCustomMap() {
    try {
      const res = await fetch('/api/settings/mode', {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'custom', custom_map: customMap }),
      })
      const data = await res.json()
      setSettings(data)
      showToast('自定义分配已保存')
    } catch (e) {
      showToast('保存失败')
    }
  }

  if (loading) {
    return (
      <Modal open onClose={onClose} title="API 设置" size="md">
        <div className="p-8 text-zinc-400 text-sm">
          <Icon name="loader" size={16} className="animate-spin mr-2 inline" />
          加载中...
        </div>
      </Modal>
    )
  }

  const providers = settings?.providers || []
  const currentMode = settings?.mode || 'split'

  return (
    <Modal open onClose={onClose} title="API 设置" size="lg" panelClassName="max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
          <h2 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <Icon name="settings" size={16} /> API 设置
          </h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800" aria-label="关闭">
            <Icon name="x" size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-800 px-5 shrink-0">
          {[
            { key: 'providers', label: 'Provider', icon: 'globe' },
            { key: 'slots', label: '模型分配', icon: 'layers' },
            { key: 'mode', label: '模式', icon: 'zap' },
            ...(bookId ? [{ key: 'book', label: '书籍覆盖', icon: 'book-open' }] : []),
            { key: 'about', label: '关于', icon: 'info' },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <Icon name={t.icon} size={12} /> {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* ── Tab: Providers ── */}
          {tab === 'providers' && (
            <div className="space-y-4">
              {/* Provider list */}
              {providers.map(p => (
                <div key={p.id} className="border border-zinc-800 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Icon name="database" size={14} className="text-zinc-500" />
                      <span className="text-xs font-semibold text-zinc-300">{p.name}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                        {PROVIDER_TYPE_LABELS[p.type] || p.type}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button onClick={() => testProvider(p.id)} disabled={testing === p.id}
                        className="text-[10px] text-zinc-500 hover:text-emerald-400 px-1.5 py-0.5 rounded hover:bg-zinc-800 disabled:opacity-50">
                        {testing === p.id ? '测试中...' : '测试连接'}
                      </button>
                      <button onClick={() => openEditProvider(p)}
                        className="text-zinc-500 hover:text-blue-400 p-1 rounded hover:bg-zinc-800">
                        <Icon name="edit" size={12} />
                      </button>
                      <button onClick={() => deleteProvider(p.id)}
                        className="text-zinc-500 hover:text-red-400 p-1 rounded hover:bg-zinc-800">
                        <Icon name="trash" size={12} />
                      </button>
                    </div>
                  </div>
                  <div className="text-[10px] text-zinc-600 space-y-0.5">
                    <div>ID: {p.id}</div>
                    {p.base_url && <div>URL: {p.base_url}</div>}
                    <div>Key: {p.api_key || '(未设置)'}</div>
                    <div>Models: {(p.models || []).join(', ')}</div>
                  </div>
                </div>
              ))}

              {/* Add/Edit form */}
              {editingProvider !== null || editingProvider === null ? null : null}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-zinc-300">
                    {editingProvider !== null ? `编辑: ${editingProvider}` : '添加 Provider'}
                  </span>
                  {editingProvider !== null && (
                    <button onClick={() => setEditingProvider(null)} className="text-zinc-500 hover:text-zinc-300 text-[10px]">
                      取消
                    </button>
                  )}
                </div>
                <div className="space-y-2.5">
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <label className="text-[10px] text-zinc-500 block mb-1">ID (唯一标识)</label>
                      <input value={providerForm.id} onChange={e => setProviderForm(f => ({ ...f, id: e.target.value }))}
                        disabled={editingProvider !== null}
                        placeholder="deepseek-main"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600 disabled:opacity-50" />
                    </div>
                    <div className="flex-1">
                      <label className="text-[10px] text-zinc-500 block mb-1">名称</label>
                      <input value={providerForm.name} onChange={e => setProviderForm(f => ({ ...f, name: e.target.value }))}
                        placeholder="DeepSeek 主力"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600" />
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500 block mb-1">类型</label>
                    <select value={providerForm.type} onChange={e => setProviderForm(f => ({ ...f, type: e.target.value }))}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600">
                      {Object.entries(PROVIDER_TYPE_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500 block mb-1">API Key</label>
                    <input value={providerForm.api_key} onChange={e => setProviderForm(f => ({ ...f, api_key: e.target.value }))}
                      type="password" placeholder="sk-..."
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600" />
                  </div>
                  {providerForm.type === 'openai' && (
                    <div>
                      <label className="text-[10px] text-zinc-500 block mb-1">Base URL</label>
                      <input value={providerForm.base_url} onChange={e => setProviderForm(f => ({ ...f, base_url: e.target.value }))}
                        placeholder="https://api.deepseek.com"
                        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600" />
                    </div>
                  )}
                  <div>
                    <label className="text-[10px] text-zinc-500 block mb-1">Models (逗号分隔)</label>
                    <input value={providerForm.models} onChange={e => setProviderForm(f => ({ ...f, models: e.target.value }))}
                      placeholder="deepseek-v4-pro, deepseek-v4-flash"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600" />
                  </div>
                  <button onClick={saveProvider} disabled={saving || !providerForm.id || !providerForm.name}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-xs py-2 rounded-lg font-medium transition-colors">
                    {saving ? '保存中...' : '保存 Provider'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Tab: Slots ── */}
          {tab === 'slots' && (
            <div className="space-y-4">
              {(['pro', 'flash']).map(slotName => {
                const slot = slotName === 'pro' ? settings.slot_pro : settings.slot_flash
                const slotProvider = providers.find(p => p.id === slot?.provider_id)
                return (
                  <div key={slotName} className="border border-zinc-800 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Icon name={slotName === 'pro' ? 'star' : 'zap'} size={14}
                        className={slotName === 'pro' ? 'text-amber-400' : 'text-emerald-400'} />
                      <span className="text-xs font-semibold text-zinc-300">
                        {slotName === 'pro' ? 'Pro 槽位 (高质量)' : 'Flash 槽位 (快速)'}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <div className="flex-1">
                        <label className="text-[10px] text-zinc-500 block mb-1">Provider</label>
                        <select
                          value={slot?.provider_id || ''}
                          onChange={e => {
                            const pid = e.target.value
                            const prov = providers.find(p => p.id === pid)
                            const model = prov?.models?.[0] || ''
                            saveSlot(slotName, pid, model)
                          }}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
                        >
                          <option value="">-- 选择 --</option>
                          {providers.map(p => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex-1">
                        <label className="text-[10px] text-zinc-500 block mb-1">Model</label>
                        <select
                          value={slot?.model || ''}
                          onChange={e => saveSlot(slotName, slot?.provider_id || '', e.target.value)}
                          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 outline-none focus:border-blue-600"
                        >
                          <option value="">-- 选择 --</option>
                          {(slotProvider?.models || []).map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Preview */}
              <div className="border border-zinc-800 rounded-xl p-4">
                <div className="text-xs font-semibold text-zinc-300 mb-2">任务分配预览</div>
                <div className="grid grid-cols-2 gap-1.5">
                  {Object.entries(TASK_LABELS).map(([key, label]) => {
                    const usePro = (currentMode === 'quality') ||
                      (currentMode === 'split' && ['writing', 'editing'].includes(key)) ||
                      (currentMode === 'custom' && customMap[key] === 'pro')
                    const isFlash = currentMode === 'flash' || (!usePro && currentMode !== 'quality')
                    return (
                      <div key={key} className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-[10px] ${
                        usePro && !isFlash ? 'bg-amber-950/30 text-amber-400 border border-amber-800/30' : 'bg-emerald-950/30 text-emerald-400 border border-emerald-800/30'
                      }`}>
                        <span>{label}</span>
                        <span className="font-medium">{usePro && !isFlash ? 'Pro' : 'Flash'}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ── Tab: Mode ── */}
          {tab === 'mode' && (
            <div className="space-y-3">
              {Object.entries(MODE_INFO).map(([mode, info]) => (
                <button
                  key={mode}
                  onClick={() => switchMode(mode)}
                  className={`w-full text-left border rounded-xl p-4 transition-all ${
                    currentMode === mode
                      ? `border-${info.color}-700 bg-${info.color}-950/30`
                      : 'border-zinc-800 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Icon name={info.icon} size={14} className={currentMode === mode ? `text-${info.color}-400` : 'text-zinc-500'} />
                    <span className={`text-xs font-semibold ${currentMode === mode ? `text-${info.color}-400` : 'text-zinc-400'}`}>
                      {info.label}
                    </span>
                    {currentMode === mode && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded bg-${info.color}-900/50 text-${info.color}-400 ml-auto`}>
                        当前
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-zinc-500">{info.desc}</div>
                </button>
              ))}

              {/* Custom map */}
              {currentMode === 'custom' && (
                <div className="border border-zinc-800 rounded-xl p-4 space-y-2">
                  <div className="text-xs font-semibold text-zinc-300 mb-2">自定义任务分配</div>
                  {Object.entries(TASK_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400">{label}</span>
                      <div className="flex gap-1">
                        {['pro', 'flash'].map(slot => (
                          <button
                            key={slot}
                            onClick={() => setCustomMap(m => ({ ...m, [key]: slot }))}
                            className={`text-[10px] px-2 py-1 rounded transition-colors ${
                              (customMap[key] || 'flash') === slot
                                ? slot === 'pro' ? 'bg-amber-900/50 text-amber-400' : 'bg-emerald-900/50 text-emerald-400'
                                : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
                            }`}
                          >
                            {slot === 'pro' ? 'Pro' : 'Flash'}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  <button onClick={saveCustomMap}
                    className="mt-2 w-full bg-blue-600 hover:bg-blue-500 text-white text-xs py-2 rounded-lg font-medium transition-colors">
                    保存自定义分配
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Tab: Book Overrides ── */}
          {tab === 'book' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-zinc-300">当前书籍的 API 覆盖</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">覆盖只影响当前书籍，不影响其他书籍的全局设置</div>
                </div>
                {bookOverrides && (
                  <button
                    onClick={resetBookOverrides}
                    disabled={saving}
                    className="text-[10px] text-amber-500 hover:text-amber-400 px-2 py-1 rounded hover:bg-amber-950/30 transition-colors"
                  >
                    重置为全局
                  </button>
                )}
              </div>

              {/* Mode override */}
              <div className="border border-zinc-800 rounded-xl p-3">
                <div className="text-[10px] text-zinc-500 mb-2">LLM 模式覆盖</div>
                <div className="flex gap-1.5 flex-wrap">
                  {['', ...Object.keys(MODE_INFO)].map(m => (
                    <button
                      key={m}
                      onClick={() => setBookOverrideForm(f => ({ ...f, mode: m }))}
                      className={`text-[10px] px-2.5 py-1 rounded transition-colors ${
                        bookOverrideForm.mode === m
                          ? 'bg-blue-900/50 text-blue-400 border border-blue-700/50'
                          : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300 border border-transparent'
                      }`}
                    >
                      {m || '全局默认'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Global reference */}
              <div className="border border-zinc-800 rounded-xl p-3 bg-zinc-950/50">
                <div className="text-[10px] text-zinc-600 mb-2">全局设置参考</div>
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  <div>
                    <span className="text-zinc-500">模式: </span>
                    <span className="text-zinc-400">{settings?.mode || '-'}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Pro 槽位: </span>
                    <span className="text-zinc-400">{settings?.slot_pro?.model || '-'}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500">Flash 槽位: </span>
                    <span className="text-zinc-400">{settings?.slot_flash?.model || '-'}</span>
                  </div>
                </div>
              </div>

              {bookOverrides && (
                <div className="border border-purple-800/40 rounded-xl p-3 bg-purple-950/20">
                  <div className="text-[10px] text-purple-400 mb-1">已保存的覆盖</div>
                  <pre className="text-[10px] text-purple-300/70 whitespace-pre-wrap">{JSON.stringify(bookOverrides, null, 2)}</pre>
                </div>
              )}

              <button
                onClick={saveBookOverrides}
                disabled={saving}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-xs py-2 rounded-lg font-medium transition-colors"
              >
                {saving ? '保存中...' : '保存书籍覆盖'}
              </button>
            </div>
          )}

          {/* ── Tab: About / Update ── */}
          {tab === 'about' && (
            <div className="space-y-4">
              {/* Current version */}
              <div className="border border-zinc-800 rounded-xl p-4">
                <div className="text-[10px] text-zinc-500 mb-2">当前版本</div>
                <div className="flex items-center gap-2">
                  <Icon name="info" size={16} className="text-blue-400" />
                  <span className="text-lg font-mono text-zinc-200">
                    v{updateStatus?.current_version || '...'}
                  </span>
                </div>
              </div>

              {/* Toggle */}
              <div className="border border-zinc-800 rounded-xl p-4 flex items-center justify-between">
                <div className="pr-3">
                  <div className="text-xs text-zinc-300">自动检测更新</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">开启后可检查 GitHub 上的最新发布版本</div>
                </div>
                <Toggle
                  checked={updateStatus?.update_check_enabled ?? true}
                  onChange={(v) => doToggleUpdateCheck(v)}
                />
              </div>

              {/* Check button + result */}
              <div className="border border-zinc-800 rounded-xl p-4 space-y-3">
                <button
                  onClick={doCheckUpdate}
                  disabled={checking || !updateStatus?.update_check_enabled}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-xs py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-1.5"
                >
                  <Icon name="refresh" size={12} className={checking ? 'animate-spin' : ''} />
                  {checking ? '检查中...' : '检查更新'}
                </button>

                {updateResult && (
                  <div className="rounded-lg border border-zinc-800 p-3 bg-zinc-950/50">
                    {updateResult.has_update ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Icon name="alert-circle" size={14} className="text-amber-400" />
                          <span className="text-xs text-amber-400">发现新版本</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-zinc-500">当前: v{updateResult.current_version}</span>
                          <Icon name="chevron-right" size={10} className="text-zinc-600" />
                          <span className="text-emerald-400 font-medium">最新: {updateResult.latest_version}</span>
                        </div>
                        {updateResult.published_at && (
                          <div className="text-[10px] text-zinc-500">
                            发布于 {new Date(updateResult.published_at).toLocaleDateString('zh-CN')}
                          </div>
                        )}
                        {updateResult.release_notes && (
                          <div className="mt-2 max-h-40 overflow-y-auto rounded bg-zinc-900 p-2">
                            <pre className="text-[10px] text-zinc-400 whitespace-pre-wrap font-mono">
                              {updateResult.release_notes.slice(0, 500)}
                              {updateResult.release_notes.length > 500 ? '...' : ''}
                            </pre>
                          </div>
                        )}
                        <a
                          href={updateResult.release_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300"
                        >
                          <Icon name="download" size={11} />
                          前往下载
                        </a>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Icon name="check-circle" size={14} className="text-emerald-400" />
                        <span className="text-xs text-zinc-400">
                          {updateResult.latest_version
                            ? `已是最新版本 (v${updateResult.current_version})`
                            : updateResult.message || '尚无正式发布版本'}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="text-[10px] text-zinc-600 text-center">
                更新检测通过 GitHub Releases 公开 API 获取，仅检查不自动安装
              </div>
            </div>
          )}
        </div>

        {/* Toast */}
        {toast && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-zinc-800 text-zinc-300 text-xs px-4 py-2 rounded-lg shadow-lg border border-zinc-700">
            {toast}
          </div>
        )}
    </Modal>
  )
}
