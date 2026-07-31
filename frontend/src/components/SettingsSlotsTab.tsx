// SettingsSlotsTab — model-slot assignment tab for SettingsModal (extracted
// to slim the parent modal).
import Icon from './ui/Icon'

interface ProviderLike {
  id: string
  name: string
  models?: string[]
}

interface SlotLike {
  provider_id?: string
  model?: string
}

interface Props {
  providers: ProviderLike[]
  slotPro: SlotLike | undefined
  slotFlash: SlotLike | undefined
  currentMode: string
  customMap: Record<string, string>
  taskLabels: Record<string, string>
  onSaveSlot: (slotName: 'pro' | 'flash', providerId: string, model: string) => void
}

export default function SettingsSlotsTab({
  providers,
  slotPro,
  slotFlash,
  currentMode,
  customMap,
  taskLabels,
  onSaveSlot,
}: Props) {
  return (
    <div className="space-y-4">
      {(['pro', 'flash'] as const).map(slotName => {
        const slot = slotName === 'pro' ? slotPro : slotFlash
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
                    onSaveSlot(slotName, pid, model)
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
                  onChange={e => onSaveSlot(slotName, slot?.provider_id || '', e.target.value)}
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
          {Object.entries(taskLabels).map(([key, label]) => {
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
  )
}
