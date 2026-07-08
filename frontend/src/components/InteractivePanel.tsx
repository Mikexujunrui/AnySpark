/**
 * [DEPRECATED] InteractivePanel — 1.0时代的互动故事面板。
 *
 * @deprecated 2.0 使用 SimulationPanel 替代（features/simulation/SimulationPanel.tsx）。
 * PanelHost 已切换为导入 SimulationPanel。此文件保留供参考但不再被引用。
 */
import { useState, useCallback, useEffect } from 'react'
import { showToast } from './ui/toast-utils'
import StoryStage from '../features/interactive/StoryStage'
import Icon from './ui/Icon'

export default function InteractivePanel({ bookId }) {
  const [branchId, setBranchId] = useState(null)
  const [narrative, setNarrative] = useState('')
  const [choices, setChoices] = useState([])
  const [loading, setLoading] = useState(false)
  const [branches, setBranches] = useState([])
  const [constraintWarnings, setConstraintWarnings] = useState<{ constraint_id: string; description: string; severity: string }[]>([])

  // Check constraints on mount and refresh
  const checkConstraints = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/narrative/constraints/check`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
      if (res.ok) {
        const data = await res.json()
        setConstraintWarnings(data.violations || [])
      }
    } catch { /* silent */ }
  }, [bookId])

  useEffect(() => { checkConstraints() }, [checkConstraints])

  const startStory = useCallback(async () => {
    setLoading(true)
    setNarrative('')
    setChoices([])
    try {
      const res = await fetch(`/api/books/${bookId}/interactive/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.branch) {
        setBranchId(data.branch.id)
        setNarrative(data.narrative || '')
        setChoices(data.choices || [])
        loadBranches()
      } else {
        showToast('启动故事失败', 'error')
      }
    } catch (e) {
      console.error('Interactive start error:', e)
      showToast('启动故事失败: ' + (e.message || '请检查后端日志'), 'error')
    }
    setLoading(false)
  }, [bookId])

  const makeChoice = useCallback(async (choice) => {
    if (!branchId) return
    setLoading(true)
    setChoices([])
    try {
      const body: any = {
        branch_id: branchId,
        free_input: choice.custom ? choice.text : undefined,
      }
      if (!choice.custom) {
        body.choice_id = choice.id
      }
      const res = await fetch(`/api/books/${bookId}/interactive/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (data.narrative) {
        setNarrative(prev => prev + '\n\n' + data.narrative)
        setChoices(data.choices || [])
      } else {
        showToast('生成叙事失败', 'error')
      }
    } catch (e) {
      console.error('Interactive turn error:', e)
      showToast('请求失败: ' + (e.message || '网络错误'), 'error')
    }
    setLoading(false)
  }, [bookId, branchId])

  const createBranch = useCallback(async (parentBranchId) => {
    const name = prompt('新分支名称：')
    if (!name) return
    try {
      const res = await fetch(`/api/books/${bookId}/interactive/branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, parent_branch_id: parentBranchId }),
      })
      const data = await res.json()
      if (data.branch) {
        showToast(`分支 "${name}" 已创建`, 'success')
        setBranchId(data.branch.id)
        loadBranches()
      }
    } catch (e) {
      showToast('创建分支失败', 'error')
    }
  }, [bookId])

  async function loadBranches() {
    try {
      const res = await fetch(`/api/books/${bookId}/interactive/branches`)
      const data = await res.json()
      setBranches(data.branches || [])
    } catch (e) { /* silent */ }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Constraint violation warnings */}
      {constraintWarnings.length > 0 && (
        <div className="shrink-0 bg-red-950/60 border-b border-red-800/60 px-4 py-2">
          <div className="flex items-start gap-2">
            <Icon name="alert-triangle" size={14} className="text-red-400 mt-0.5 shrink-0" />
            <div className="text-[10px] text-red-300">
              <span className="font-medium">叙事约束警告：</span>
              {constraintWarnings.map(v => (
                <span key={v.constraint_id} className="ml-1">
                  {v.description}（{v.severity === 'hard' ? '硬约束' : '软约束'}）
                </span>
              ))}
              <button onClick={checkConstraints} className="ml-2 text-red-400 hover:text-red-200 underline">刷新</button>
            </div>
          </div>
        </div>
      )}
      <StoryStage
        _bookId={bookId}
        branchId={branchId}
        narrative={narrative}
        choices={choices}
        loading={loading}
        onChoice={makeChoice}
        onBranch={createBranch}
        onNewStory={startStory}
      />
    </div>
  )
}
