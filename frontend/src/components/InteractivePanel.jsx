import { useState, useCallback } from 'react'
import { showToast } from './ui/Toast.jsx'
import StoryStage from '../features/interactive/StoryStage.jsx'

export default function InteractivePanel({ bookId }) {
  const [branchId, setBranchId] = useState(null)
  const [narrative, setNarrative] = useState('')
  const [choices, setChoices] = useState([])
  const [loading, setLoading] = useState(false)
  const [branches, setBranches] = useState([])

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
      const body = {
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
    <div className="h-full">
      <StoryStage
        bookId={bookId}
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
