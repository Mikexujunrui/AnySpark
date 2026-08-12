import Icon from './ui/Icon'
import Toggle from './ui/Toggle'

interface Props {
  authorDnaEnabled: boolean
  bookId?: string
  projectType: string
  saving: boolean
  onToggleAuthorDna: (enabled: boolean) => void
  onProjectTypeChange: (projectType: 'original' | 'continuation') => void
}

export default function ExperimentalFeaturesPanel({
  authorDnaEnabled,
  bookId,
  projectType,
  saving,
  onToggleAuthorDna,
  onProjectTypeChange,
}: Props) {
  const continuation = projectType === 'continuation'
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-900/50 bg-amber-950/20 p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-amber-300">
          <Icon name="wrench" size={14} /> 实验性新功能
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
          这些能力仍在真实长篇语料中验证，默认关闭。开启不会修改既有章节；再次关闭只会停止入口和正文注入，已经生成的分析数据会保留。
        </p>
      </div>

      <div className="rounded-xl border border-zinc-800 p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
              <Icon name="microscope" size={14} className="text-violet-400" /> 作者 DNA 实验室
              <span className="rounded bg-violet-950 px-1.5 py-0.5 text-[9px] font-normal text-violet-300">实验性</span>
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-500">
              从原作者样本中建立有证据的六层写作规则，并为当前场景编译局部 Writer Package。分析会产生额外 API 调用，规则仍需人工确认。
            </p>
          </div>
          <Toggle checked={authorDnaEnabled} onChange={onToggleAuthorDna} />
        </div>
        {!authorDnaEnabled && (
          <p className="mt-3 rounded-lg bg-zinc-950 px-3 py-2 text-[10px] text-zinc-600">
            当前关闭：不会显示作者 DNA 标签，也不会向正文模型注入相关内容。
          </p>
        )}
      </div>

      {bookId && (
        <div className="rounded-xl border border-zinc-800 p-4">
          <div className="text-xs font-semibold text-zinc-300">当前项目用途</div>
          <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">
            作者 DNA 依赖已存在的原作及参考样本，只适用于续写。原创项目即使开启全局实验开关，也不会启用该能力。
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              disabled={saving}
              onClick={() => onProjectTypeChange('original')}
              className={`rounded-xl border p-3 text-left transition-colors ${
                !continuation
                  ? 'border-sky-700 bg-sky-950/30 text-sky-300'
                  : 'border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-xs font-medium">从零原创</div>
              <div className="mt-1 text-[9px] opacity-70">隐藏并停用作者 DNA</div>
            </button>
            <button
              disabled={saving}
              onClick={() => onProjectTypeChange('continuation')}
              className={`rounded-xl border p-3 text-left transition-colors ${
                continuation
                  ? 'border-violet-700 bg-violet-950/30 text-violet-300'
                  : 'border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-xs font-medium">原作续写</div>
              <div className="mt-1 text-[9px] opacity-70">允许使用作者样本与续写 Canon</div>
            </button>
          </div>
          {authorDnaEnabled && !continuation && (
            <p className="mt-3 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-400">
              全局实验开关已开启，但当前书仍是原创项目；切换为“原作续写”后才会出现作者 DNA 标签。
            </p>
          )}
          {authorDnaEnabled && continuation && (
            <p className="mt-3 rounded-lg border border-emerald-900/40 bg-emerald-950/20 px-3 py-2 text-[10px] text-emerald-400">
              当前项目已具备使用资格。关闭任意一道开关都会立即停止正文注入，但不会删除分析结果。
            </p>
          )}
        </div>
      )}
    </div>
  )
}
