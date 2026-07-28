import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import Modal from './ui/Modal'

const STEP_ICONS = {
  extract: 'search', write: 'pen-tool', validate: 'search', edit: 'edit',
  plan: 'globe', review: 'clipboard-list',
}
const STEP_COLORS = {
  pending: 'border-zinc-700 bg-zinc-800/30 text-zinc-500',
  running: 'border-blue-700 bg-blue-950/30 text-blue-400',
  completed: 'border-emerald-700 bg-emerald-950/30 text-emerald-400',
  failed: 'border-red-700 bg-red-950/30 text-red-400',
}

export default function WorkflowView({ bookId }: { bookId: string }) {
  const [workflow, setWorkflow] = useState<Record<string, any> | null>(null)
  const [workflows, setWorkflows] = useState<Record<string, any>[]>([])
  const [intent, setIntent] = useState('')
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [activeWfId, setActiveWfId] = useState<string | null>(null)
  const [showList, setShowList] = useState(true)
  const [showBrowse, setShowBrowse] = useState(false)
  const [globalWfs, setGlobalWfs] = useState<Record<string, any>[]>([])
  const [execParams, setExecParams] = useState<{ ref_chapters: string[]; instruction: string }>({ ref_chapters: [], instruction: '' })
  const [refBookChapters, setRefBookChapters] = useState<Record<string, any>[]>([])
  const [showParams, setShowParams] = useState(false)
  const [deleteWfId, setDeleteWfId] = useState<string | null>(null)

  const loadWorkflows = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/workflows`)
      const data = await res.json()
      setWorkflows(Array.isArray(data) ? data : [])
    } catch (e) { console.error(e) }
  }, [bookId])

  useEffect(() => { loadWorkflows() }, [loadWorkflows])

  async function handleGenerate() {
    if (!intent.trim()) return
    setLoading(true)
    setStatusMsg('正在分析需求，生成工作流...')
    try {
      const res = await fetch(`/api/books/${bookId}/workflow/generate`, {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ intent: intent.trim() }),
      })
      const wf = await res.json()
      setWorkflow(wf)
      setActiveWfId(wf.id)
      setShowList(false)
      setStatusMsg(`已生成工作流: ${wf.name} (${(wf.steps?.length || 0)} 步)`)
      loadWorkflows()
    } catch (e) {
      setStatusMsg('生成失败: ' + e.message)
    }
    setLoading(false)
  }

  function handleLoad(wf: Record<string, any>) {
    setWorkflow(wf)
    setActiveWfId(wf.id)
    setShowList(false)
  }

  async function handleDelete(wfId: string, e: React.MouseEvent) {
    e.stopPropagation()
    setDeleteWfId(wfId)
  }

  async function confirmDelete() {
    await fetch(`/api/books/${bookId}/workflows/${deleteWfId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    loadWorkflows()
    if (activeWfId === deleteWfId) reset()
    setDeleteWfId(null)
  }

  async function handleBrowse() {
    try {
      const res = await fetch('/api/workflows')
      const data = await res.json()
      setGlobalWfs(Array.isArray(data) ? data : [])
      setShowBrowse(true)
    } catch (e) { console.error(e) }
  }

  async function handleSubscribe(wfId) {
    await fetch(`/api/books/${bookId}/workflow-subs`, {
      method: 'POST',
      headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_id: wfId }),
    })
    loadWorkflows()
  }

  async function handleUnsubscribe(wfId: string, e: React.MouseEvent) {
    e.stopPropagation()
    await fetch(`/api/books/${bookId}/workflow-subs/${wfId}`, { method: 'DELETE', headers: { "X-Confirm-Delete": "true" } })
    loadWorkflows()
  }

  // Load reference book chapters for params UI
  useEffect(() => {
    async function loadRefChapters() {
      try {
        const res = await fetch(`/api/books/${bookId}/references`)
        const data = await res.json()
        const refIds = data.reference_book_ids || []
        if (refIds.length === 0) return
        // Load chapters from first reference book
        const chRes = await fetch(`/api/books/${refIds[0]}/chapters`)
        const chapters = await chRes.json()
        setRefBookChapters(Array.isArray(chapters) ? chapters : [])
      } catch (e) { /* no ref books */ }
    }
    if (bookId) loadRefChapters()
  }, [bookId])

  async function handleRun() {
    if (!activeWfId) return
    setLoading(true)
    setStatusMsg('正在执行工作流...')

    // Reset all step statuses
    setWorkflow(prev => ({
      ...prev,
      steps: prev.steps.map(s => ({ ...s, _status: 'pending', _result: null }))
    }))

    // Build params: only include non-empty fields
    const params: Record<string, any> = {}
    if (execParams.ref_chapters?.length) params.ref_chapters = execParams.ref_chapters
    if (execParams.instruction?.trim()) params.instruction = execParams.instruction.trim()

    try {
      const res = await fetch(`/api/books/${bookId}/workflow/${activeWfId}/execute`, {
        method: 'POST',
        headers: { "X-Confirm-Delete": "true",  'Content-Type': 'application/json' },
        body: JSON.stringify({ params }),
      })

      if (!res.ok) {
        setStatusMsg('执行失败: HTTP ' + res.status)
        setLoading(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events (separated by \n\n)
        const events = buffer.split('\n\n')
        buffer = events.pop()  // keep incomplete part

        for (const evt of events) {
          const eventMatch = evt.match(/event:\s*(\S+)/)
          const dataMatch = evt.match(/data:\s*(.*)/s)
          if (!eventMatch || !dataMatch) continue

          const eventType = eventMatch[1]
          try {
            const eventData = JSON.parse(dataMatch[1])

            setWorkflow(prev => {
              const steps = [...prev.steps]
              if (eventType === 'step_start') {
                const idx = eventData.index ?? steps.findIndex(s => s._status === 'pending')
                if (idx >= 0 && idx < steps.length) {
                  steps[idx] = { ...steps[idx], _status: 'running' }
                }
              } else if (eventType === 'step_done') {
                const idx = steps.findIndex(s => s.label === eventData.step && s._status === 'running')
                if (idx >= 0) steps[idx] = { ...steps[idx], _status: 'completed', _result: eventData.result }
              } else if (eventType === 'step_error') {
                const idx = steps.findIndex(s => s.label === eventData.step && s._status === 'running')
                if (idx >= 0) steps[idx] = { ...steps[idx], _status: 'failed', _result: eventData.error }
              }
              return { ...prev, steps }
            })

            if (eventType === 'done') {
              setStatusMsg('工作流执行完毕')
            } else if (eventType === 'error') {
              setStatusMsg('执行错误: ' + (eventData.message || '未知'))
            }
          } catch (parseErr) {
            // skip malformed event
          }
        }
      }
    } catch (e) {
      setStatusMsg('执行失败: ' + e.message)
    }
    setLoading(false)
  }

  function reset() {
    setWorkflow(null)
    setIntent('')
    setStatusMsg('')
    setActiveWfId(null)
    setShowList(true)
  }

  const shortcuts = [
    { label: '写完第5章', intent: '我想写第5章，要求严格遵循设定，写完自动校验一致性' },
    { label: '导入并精修', intent: '帮我导入一段草稿文本，提取所有设定，然后根据设定规划下一章的剧情方向' },
    { label: '日常写作', intent: '我要写今天的正文，先回顾一下当前的伏笔状态，然后写新内容，写完帮我润色' },
  ]

  const templates = [
    { name: '写完+提取+校验', desc: '写一章 → 提取新设定 → 校验一致性', intent: '写第X章，写完后提取本章新增的设定和角色，最后校验与知识库的一致性' },
    { name: '导入+全套处理', desc: '导入文档 → 分章 → 提取全部设定 → 生成大纲', intent: '导入上传的文档，自动拆分章节，提取全部角色和设定，最后根据内容生成全书大纲' },
    { name: '批量润色', desc: '列出全部章节 → 逐章润色提升文笔', intent: '列出所有章节，逐章对内容进行文学润色，提升文笔质量' },
  ]

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50 shrink-0 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-1.5"><Icon name="settings" size={16} /> 工作流</h3>
        <div className="flex gap-2">
          {showList && (
            <button onClick={handleBrowse}
              className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-3 py-1 rounded-lg transition-colors">
              浏览全局
            </button>
          )}
          {showList && (
            <button onClick={() => setShowList(false)}
              className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-3 py-1 rounded-lg transition-colors">
              + 新建
            </button>
          )}
          {!showList && workflows.length > 0 && (
            <button onClick={() => { reset(); setShowList(true) }}
              className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">
              <Icon name="clipboard-list" size={12} className="inline" /> 已订阅 ({workflows.length})
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {/* Saved Workflows List */}
        {showList && workflows.length > 0 && (
          <div className="max-w-xl mx-auto space-y-2">
            <p className="text-xs text-zinc-500 mb-3">已保存的工作流 ({workflows.length})</p>
            {workflows.map(wf => (
              <div key={wf.id}
                onClick={() => handleLoad(wf)}
                className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 hover:border-zinc-600 cursor-pointer group transition-colors">
                <Icon name="settings" size={18} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 font-medium truncate">{wf.name}</p>
                  <p className="text-[10px] text-zinc-500">
                    {wf.steps?.length || 0} 步 · {wf.createdAt?.slice(0, 16).replace('T', ' ')}
                  </p>
                </div>
                <button onClick={(e) => handleDelete(wf.id, e)}
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 text-xs transition-all">
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Empty + Generate */}
        {showList && workflows.length === 0 ? (
          <div className="max-w-xl mx-auto space-y-6">
            <p className="text-sm text-zinc-400">
              用自然语言描述你的写作需求，AI 会自动规划多步骤工作流：
            </p>

            {/* Default templates */}
            <div>
              <p className="text-xs text-zinc-500 mb-2">快捷模板（点击即生成并保存）：</p>
              <div className="space-y-2">
                {templates.map(t => (
                  <button key={t.name}
                    onClick={() => { setIntent(t.intent); handleGenerate(); }}
                    disabled={loading}
                    className="w-full text-left bg-zinc-800/40 border border-zinc-800 rounded-xl px-4 py-3 hover:border-zinc-600 transition-colors disabled:opacity-40">
                    <p className="text-sm font-medium text-zinc-200">{t.name}</p>
                    <p className="text-xs text-zinc-500 mt-0.5">{t.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <textarea
                value={intent}
                onChange={e => setIntent(e.target.value)}
                placeholder="例如：我想写第5章，要严格遵循已有设定，写完帮我校验有没有bug"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-200 resize-none h-24 focus:outline-none focus:border-zinc-500"
                disabled={loading}
                onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleGenerate() }}
              />
              <button
                onClick={handleGenerate}
                disabled={loading || !intent.trim()}
                className="w-full bg-zinc-200 text-zinc-900 rounded-xl py-2.5 text-sm font-medium hover:bg-white transition-colors disabled:opacity-40"
              >
                {loading ? '生成中...' : <span className="flex items-center justify-center gap-1"><Icon name="zap" size={14} /> 生成工作流</span>}
              </button>
            </div>
            <div>
              <p className="text-xs text-zinc-600 mb-2">快速模板：</p>
              <div className="grid grid-cols-3 gap-2">
                {shortcuts.map(s => (
                  <button
                    key={s.label}
                    onClick={() => setIntent(s.intent)}
                    className="text-left bg-zinc-800/40 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition-colors"
                  >
                    <p className="font-medium text-zinc-300">{s.label}</p>
                    <p className="text-zinc-600 mt-0.5 truncate">{s.intent.slice(0, 40)}...</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : showList && workflows.length > 0 ? (
          /* Quick generate section at bottom of list */
          <div className="max-w-xl mx-auto mt-6 pt-6 border-t border-zinc-800">
            <textarea
              value={intent}
              onChange={e => setIntent(e.target.value)}
              placeholder="新建工作流：描述你的需求..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-200 resize-none h-20 focus:outline-none focus:border-zinc-500"
              disabled={loading}
              onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleGenerate() }}
            />
            <button
              onClick={handleGenerate}
              disabled={loading || !intent.trim()}
              className="w-full mt-2 bg-zinc-200 text-zinc-900 rounded-xl py-2.5 text-sm font-medium hover:bg-white transition-colors disabled:opacity-40"
            >
              {loading ? '生成中...' : '⚡ 生成工作流'}
            </button>
          </div>
        ) : null}

        {/* Workflow Detail */}
        {!showList && workflow && (
          <div className="max-w-xl mx-auto space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-semibold text-zinc-200">{workflow.name}</h4>
                <p className="text-xs text-zinc-500">{workflow?.steps?.length || 0} 个步骤</p>
              </div>
              <button onClick={reset}
                className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">↩ 返回列表</button>
            </div>

            {statusMsg && (
              <div className="text-xs bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-400">
                {statusMsg}
              </div>
            )}

            {/* Step pipeline */}
            <div className="space-y-2">
              {workflow.steps.map((step, i) => {
                const status = step._status || 'pending'
                return (
                  <div key={step.id || i}>
                    <div className={`flex items-center gap-3 border rounded-xl px-4 py-3 transition-colors ${STEP_COLORS[status]}`}>
                      <Icon name={STEP_ICONS[step.type] || 'list'} size={18} />
                      <div className="flex-1">
                        <p className="text-sm font-medium">{step.label}</p>
                        <p className="text-[10px] opacity-60">
                          {step.type}
                          {step.config?.instruction && `: ${step.config.instruction.slice(0, 30)}...`}
                        </p>
                      </div>
                      <span className={`text-xs font-medium ${
                        status === 'completed' ? 'text-emerald-400' :
                        status === 'running' ? 'text-blue-400 animate-pulse' :
                        status === 'failed' ? 'text-red-400' : 'text-zinc-600'
                      }`}>
                        {status === 'completed' ? '✓' : status === 'running' ? '⋯' : status === 'failed' ? '✗' : '○'}
                      </span>
                    </div>
                    {workflow?.steps?.length > 0 && i < workflow.steps.length - 1 && (
                      <div className="flex justify-center py-1">
                        <div className={`w-0.5 h-4 ${step._status === 'completed' ? 'bg-emerald-700' : 'bg-zinc-800'}`} />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Execution params panel */}
            <div className="border border-zinc-800 rounded-xl overflow-hidden">
              <button onClick={() => setShowParams(!showParams)}
                className="w-full flex items-center justify-between px-4 py-2 bg-zinc-800/30 text-xs text-zinc-400 hover:text-zinc-200 transition-colors">
                <span className="flex items-center gap-1"><Icon name="settings" size={12} /> 执行参数 {showParams ? '▾' : '▸'}</span>
                {(execParams.ref_chapters?.length > 0 || execParams.instruction?.trim()) && (
                  <span className="text-emerald-500">● 已设置</span>
                )}
              </button>
              {showParams && (
                <div className="p-4 space-y-3 bg-zinc-900/50">
                  {/* ref_chapters selector */}
                  {refBookChapters.length > 0 && (
                    <div>
                      <label className="text-xs text-zinc-500 mb-1 block">参考书章节（注入原文到写作上下文）</label>
                      <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                        {refBookChapters.map((ch, i) => {
                          const ref = `#${i + 1}`
                          const selected = execParams.ref_chapters?.includes(ref)
                          return (
                            <button key={ch.id}
                              onClick={() => {
                                setExecParams(prev => ({
                                  ...prev,
                                  ref_chapters: selected
                                    ? (prev.ref_chapters || []).filter(r => r !== ref)
                                    : [...(prev.ref_chapters || []), ref]
                                }))
                              }}
                              className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
                                selected
                                  ? 'border-emerald-600 bg-emerald-950/40 text-emerald-300'
                                  : 'border-zinc-700 bg-zinc-800/50 text-zinc-500 hover:text-zinc-300'
                              }`}>
                              {ref} {ch.title?.slice(0, 12) || ''}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                  {/* instruction override */}
                  <div>
                    <label className="text-xs text-zinc-500 mb-1 block">覆盖写作指令（可选）</label>
                    <textarea
                      value={execParams.instruction}
                      onChange={e => setExecParams(prev => ({ ...prev, instruction: e.target.value }))}
                      placeholder="留空则使用工作流步骤自带的指令..."
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 resize-none h-16 focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleRun}
              disabled={loading}
              className="w-full bg-emerald-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-emerald-500 transition-colors disabled:opacity-40"
            >
              {loading ? '执行中...' : '▶ 执行工作流'}
            </button>
          </div>
        )}
      </div>

      {showBrowse && (
        <Modal open onClose={() => setShowBrowse(false)} title="全局工作流池" size="lg">
          <div className="p-6">
            <h2 className="text-lg font-bold text-zinc-200 mb-4">全局工作流池</h2>
            {globalWfs.length === 0 ? (
              <p className="text-zinc-500 text-sm">全局池为空，创建第一个工作流吧</p>
            ) : (
              <div className="space-y-2">
                {globalWfs.map(wf => (
                  <div key={wf.id} className="bg-zinc-800 rounded-lg p-3 flex items-center justify-between">
                    <div className="flex-1 min-w-0 mr-3">
                      <p className="text-sm text-zinc-200 font-medium truncate">{wf.name}</p>
                      <p className="text-[10px] text-zinc-500">{wf.steps?.length || 0} 步</p>
                    </div>
                    <button onClick={() => handleSubscribe(wf.id)}
                      className="text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-200 px-3 py-1 rounded-lg transition-colors shrink-0">
                      订阅
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowBrowse(false)}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-400 px-4 py-2 rounded-lg text-sm">关闭</button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteWfId}
        title="删除工作流"
        message="确定删除此工作流？此操作不可撤销。"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setDeleteWfId(null)}
      />
    </div>
  )
}
