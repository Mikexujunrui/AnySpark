import { useEffect, useRef, useState } from 'react'
import Icon from '../../../components/ui/Icon'
import type { SimChoice } from '../types'
import { useSimRunState } from '../stores/simulation-store'

interface StoryStageProps {
  loading: boolean
  onNewSim: () => void
  onCreateBranch: () => void
  onChoice: (choice: SimChoice | { text: string; description?: string }) => void
  onCustomAction: (action: string) => void
  onRegenerate: () => void
}

export default function StoryStage({
  loading, onNewSim, onCreateBranch,
  onChoice, onCustomAction, onRegenerate,
}: StoryStageProps) {
  const { streaming, narrative, choices, choicePrompt, statusText } = useSimRunState()
  const narrativeEndRef = useRef<HTMLDivElement>(null)
  const narrativeContainerRef = useRef<HTMLDivElement>(null)
  const [customInput, setCustomInput] = useState('')
  const [actionExpanded, setActionExpanded] = useState(true)

  // Auto-scroll on new narrative chunks
  useEffect(() => {
    narrativeEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [narrative])

  const handleSubmitCustom = () => {
    const text = customInput.trim()
    if (!text) return
    onCustomAction(text)
    setCustomInput('')
  }

  const hasContent = Boolean(narrative) || streaming || loading
  const hasActions = choices.length > 0

  return (
    <div className="h-full flex flex-col bg-zinc-950 relative">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-2.5 border-b border-zinc-800 bg-zinc-950/50 shrink-0">
        <div className="flex items-center gap-2">
          <Icon name="compass" size={14} className="text-purple-400" />
          <span className="text-xs font-semibold text-zinc-300">推演</span>
        </div>
        {statusText && (
          <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
            <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" />
            {statusText}
          </div>
        )}
        <div className="flex-1" />
        {narrative && !loading && (
          <button onClick={onRegenerate}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded-lg hover:bg-zinc-800 transition-colors flex items-center gap-1"
            title="重新生成本回合">
            <Icon name="refresh" size={11} /> 重试
          </button>
        )}
        {narrative && !loading && (
          <button onClick={onCreateBranch}
            className="text-[10px] text-purple-500 hover:text-purple-300 px-2 py-1 rounded-lg hover:bg-purple-900/30 transition-colors flex items-center gap-1"
            title="从此创建分支">
            <Icon name="git-branch" size={11} /> 分支
          </button>
        )}
        <button onClick={onNewSim}
          className="text-[10px] text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded-lg hover:bg-zinc-800 transition-colors flex items-center gap-1">
          <Icon name="plus" size={11} /> 新推演
        </button>
      </div>

      {/* Narrative Area — full height, padded bottom for floating panel */}
      <div
        ref={narrativeContainerRef}
        className="flex-1 overflow-y-auto"
      >
        <div className="px-6 py-6 max-w-2xl mx-auto" style={{ paddingBottom: hasActions ? '13rem' : '3rem' }}>
          {!hasContent ? (
            <EmptyState />
          ) : (
            <div className="space-y-4">
              {narrative.split('\n').filter(Boolean).map((para, i) => (
                <p key={i} className="text-zinc-300 text-sm leading-relaxed font-serif">
                  {para}
                </p>
              ))}

              {streaming && (
                <div className="flex items-center gap-2 text-zinc-500 text-xs py-2">
                  <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" />
                  <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                  <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
                </div>
              )}

              <div ref={narrativeEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Floating Action Panel */}
      {hasActions && !streaming && (
        <div className="absolute bottom-0 left-0 right-0 z-10">
          <div className="bg-zinc-950/95 backdrop-blur-md border-t border-zinc-800/80 rounded-t-2xl shadow-[0_-8px_30px_rgba(0,0,0,0.5)]">
            {/* Toggle header */}
            <button
              onClick={() => setActionExpanded(!actionExpanded)}
              className="w-full flex items-center justify-between px-5 py-2 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <Icon name={actionExpanded ? 'chevron-down' : 'chevron-up'} size={10} />
                {actionExpanded ? '收起操作面板' : '显示操作面板'}
              </span>
              {choicePrompt && <span className="text-zinc-600 truncate ml-2">{choicePrompt}</span>}
            </button>

            {actionExpanded && (
              <div className="max-h-64 overflow-y-auto">
                {/* Choices */}
                {choices.length > 0 && (
                  <div className="px-5 pb-3">
                    <div className="space-y-1.5">
                      {choices.map((choice, i) => (
                        <button
                          key={choice.id || i}
                          onClick={() => onChoice(choice)}
                          className="w-full text-left px-3.5 py-2.5 rounded-xl border border-zinc-700/60 bg-zinc-800/40 hover:bg-zinc-700/60 hover:border-zinc-600 transition-all group"
                        >
                          <div className="flex items-start gap-2.5">
                            <span className="text-[10px] text-purple-500 bg-purple-900/30 px-1.5 py-0.5 rounded shrink-0 mt-0.5 font-mono">
                              {i + 1}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-xs text-zinc-200 group-hover:text-zinc-100">{choice.text}</p>
                              {choice.description && (
                                <p className="text-[9px] text-zinc-500 mt-0.5">{choice.description}</p>
                              )}
                            </div>
                            <Icon name="chevron-right" size={12} className="text-zinc-600 group-hover:text-zinc-400 mt-1 shrink-0" />
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Custom Input */}
                {narrative && (
                  <div className="px-5 pb-3 pt-1">
                    <div className="flex gap-2">
                      <input
                        value={customInput}
                        onChange={e => setCustomInput(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault()
                            handleSubmitCustom()
                          }
                        }}
                        placeholder="自定义行动..."
                        className="flex-1 bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500/50"
                      />
                      <button
                        onClick={handleSubmitCustom}
                        disabled={!customInput.trim()}
                        className="px-3 py-2 rounded-lg bg-purple-900/40 text-purple-300 border border-purple-800/50 hover:bg-purple-800/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <Icon name="send" size={12} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-zinc-600 gap-3">
      <Icon name="compass" size={32} className="text-zinc-700" />
      <p className="text-sm">配置参数后开始推演</p>
      <p className="text-xs text-zinc-700">AI将基于设定生成叙事，你来做选择</p>
    </div>
  )
}