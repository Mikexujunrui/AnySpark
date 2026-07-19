import { useState } from 'react'
import Icon from '../../../components/ui/Icon'
import type { BranchSummary } from '../types'

interface BranchTimelineProps {
  branches: BranchSummary[]
  currentBranchId: string
  onSwitchBranch: (branchId: string) => void
  onCreateBranch: (title: string) => void
  onDeleteBranch: (branchId: string) => void
  onBackToSim: () => void
}

/** 分支时间线面板 — 可视化推演分支树。 */
export default function BranchTimeline({
  branches, currentBranchId,
  onSwitchBranch, onCreateBranch, onDeleteBranch,
  onBackToSim,
}: BranchTimelineProps) {
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  const handleCreate = () => {
    const title = newTitle.trim()
    if (!title) return
    onCreateBranch(title)
    setNewTitle('')
    setShowCreate(false)
  }

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 shrink-0">
        <button
          onClick={onBackToSim}
          className="text-zinc-500 hover:text-zinc-300 transition-colors"
          title="返回推演"
        >
          <Icon name="arrow-left" size={14} />
        </button>
        <span className="text-xs font-semibold text-zinc-400">分支时间线</span>
        <div className="flex-1" />
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="text-[10px] text-purple-500 hover:text-purple-300 px-2 py-1 rounded-lg hover:bg-purple-900/30 transition-colors flex items-center gap-1"
        >
          <Icon name="git-branch" size={10} /> 新建分支
        </button>
      </div>

      {/* Create branch input */}
      {showCreate && (
        <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/40">
          <div className="flex gap-2">
            <input
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate() }}
              placeholder="分支名称..."
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-purple-500/50"
              autoFocus
            />
            <button
              onClick={handleCreate}
              disabled={!newTitle.trim()}
              className="text-[10px] px-2.5 py-1.5 rounded-lg bg-purple-900/40 text-purple-300 border border-purple-800/50 hover:bg-purple-800/40 transition-colors disabled:opacity-30"
            >
              创建
            </button>
          </div>
        </div>
      )}

      {/* Branch list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {branches.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600 gap-2">
            <Icon name="git-branch" size={20} className="text-zinc-700" />
            <p className="text-xs">暂无分支</p>
          </div>
        ) : (
          branches.map(branch => {
            const isCurrent = branch.id === currentBranchId
            return (
              <div
                key={branch.id}
                className={`flex items-center gap-2 p-2.5 rounded-lg border transition-all ${
                  isCurrent
                    ? 'border-purple-500/50 bg-purple-900/20 ring-1 ring-purple-500/30'
                    : 'border-zinc-800 bg-zinc-900/30 hover:border-zinc-700'
                }`}
              >
                <Icon
                  name={branch.is_main ? 'anchor' : 'git-branch'}
                  size={12}
                  className={isCurrent ? 'text-purple-400' : 'text-zinc-500'}
                />
                <div className="flex-1 min-w-0">
                  <p className={`text-xs truncate ${isCurrent ? 'text-purple-300' : 'text-zinc-400'}`}>
                    {branch.title}
                  </p>
                  {branch.parent_event_id && (
                    <p className="text-[9px] text-zinc-600 truncate">
                      源自: {branch.parent_event_id.slice(0, 12)}...
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {!isCurrent && (
                    <button
                      onClick={() => onSwitchBranch(branch.id)}
                      className="text-[9px] text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded hover:bg-zinc-800 transition-colors"
                      title="切换到此分支"
                    >
                      切换
                    </button>
                  )}
                  {!branch.is_main && (
                    <button
                      onClick={() => onDeleteBranch(branch.id)}
                      className="text-zinc-600 hover:text-red-400 transition-colors p-0.5"
                      title="删除分支"
                    >
                      <Icon name="trash-2" size={10} />
                    </button>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
