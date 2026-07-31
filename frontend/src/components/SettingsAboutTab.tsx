// SettingsAboutTab — About / Update tab for SettingsModal (extracted to slim
// the parent modal).
import Icon from './ui/Icon'
import Toggle from './ui/Toggle'

export interface UpdateStatusLike {
  current_version: string
  update_check_enabled: boolean
}

export interface UpdateResultLike {
  has_update?: boolean
  current_version?: string
  latest_version?: string | null
  published_at?: string | null
  release_notes?: string | null
  release_url?: string | null
  message?: string
}

interface Props {
  updateStatus: UpdateStatusLike | null
  updateResult: UpdateResultLike | null
  checking: boolean
  onToggleUpdateCheck: (v: boolean) => void
  onCheckUpdate: () => void
}

export default function SettingsAboutTab({
  updateStatus,
  updateResult,
  checking,
  onToggleUpdateCheck,
  onCheckUpdate,
}: Props) {
  return (
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
          onChange={(v) => onToggleUpdateCheck(v)}
        />
      </div>

      {/* Check button + result */}
      <div className="border border-zinc-800 rounded-xl p-4 space-y-3">
        <button
          onClick={onCheckUpdate}
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
  )
}
