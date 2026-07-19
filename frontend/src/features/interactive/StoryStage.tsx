import { useEffect, useRef } from 'react'
import Icon from '../../components/ui/Icon'

export default function StoryStage({ _bookId, branchId, narrative, choices, onChoice, onBranch, onNewStory, loading }) {
  const narrativeEndRef = useRef(null)

  useEffect(() => {
    narrativeEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [narrative])

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-zinc-800 bg-zinc-950/50 shrink-0">
        <div className="flex items-center gap-2">
          <Icon name="message-circle" size={16} className="text-purple-400" />
          <span className="text-sm font-semibold text-zinc-300">互动故事</span>
        </div>
        <div className="flex-1" />
        <button
          onClick={onNewStory}
          className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition-colors flex items-center gap-1"
        >
          <Icon name="plus" size={12} /> 新故事
        </button>
        {branchId && (
          <button
            onClick={() => onBranch(branchId)}
            className="text-xs text-purple-500 hover:text-purple-300 px-3 py-1.5 rounded-lg hover:bg-purple-900/30 transition-colors flex items-center gap-1"
          >
            <Icon name="git-branch" size={12} /> 创建分支
          </button>
        )}
      </div>

      {/* Narrative Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {!narrative && !loading ? (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600 gap-3">
            <Icon name="message-circle" size={32} className="text-zinc-700" />
            <p className="text-sm">选择一个章节，开始互动故事试演</p>
            <p className="text-xs text-zinc-700">AI将基于设定生成叙事，你来做选择</p>
            <button
              onClick={onNewStory}
              className="mt-2 text-sm bg-purple-900/40 text-purple-300 border border-purple-800/50 rounded-lg px-4 py-2 hover:bg-purple-800/40 transition-colors"
            >
              开始互动故事
            </button>
          </div>
        ) : (
          <>
            {narrative.split('\n\n').map((para, i) => (
              para.trim() ? (
                <p key={i} className="text-zinc-300 text-sm leading-relaxed font-[serif] max-w-2xl mx-auto">
                  {para}
                </p>
              ) : null
            ))}

            {loading && (
              <div className="flex items-center gap-2 justify-center text-zinc-500 text-xs py-4">
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
              </div>
            )}

            <div ref={narrativeEndRef} />
          </>
        )}
      </div>

      {/* Choices */}
      {choices && choices.length > 0 && !loading && (
        <div className="border-t border-zinc-800 bg-zinc-900/80 px-6 py-4 shrink-0">
          <div className="text-[10px] text-zinc-600 mb-2 font-semibold">你的选择：</div>
          <div className="grid grid-cols-1 gap-2 max-w-2xl mx-auto">
            {choices.map((choice, i) => (
              <button
                key={i}
                onClick={() => onChoice(choice)}
                className="w-full text-left px-4 py-3 rounded-lg border border-zinc-700 bg-zinc-800/50 hover:bg-zinc-700 hover:border-zinc-600 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <span className="text-[10px] text-purple-500 bg-purple-900/30 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200 group-hover:text-zinc-100 font-medium">
                      {choice.text || choice}
                    </p>
                    {choice.description && (
                      <p className="text-[10px] text-zinc-500 mt-0.5">{choice.description}</p>
                    )}
                  </div>
                  <Icon name="chevron-right" size={14} className="text-zinc-600 group-hover:text-zinc-400 mt-1 shrink-0" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Free Input (for custom actions) */}
      {narrative && !loading && (
        <div className="border-t border-zinc-800 px-6 py-3 shrink-0">
          <div className="flex gap-2 max-w-2xl mx-auto">
            <input
              type="text"
              placeholder="或输入自定义行动..."
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
              onKeyDown={(e) => {
                const target = e.target as HTMLInputElement
                if (e.key === 'Enter' && target.value.trim()) {
                  onChoice({ text: target.value, description: '', custom: true })
                  target.value = ''
                }
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
