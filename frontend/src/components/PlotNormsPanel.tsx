import { useEffect, useState } from 'react'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'

interface PlotNorm {
  id: string
  name: string
  description: string
  rules: string[]
  avoid: string[]
  active: boolean
}

const EMPTY = { name: '', description: '', rules: '', avoid: '', active: true }

export default function PlotNormsPanel({ bookId }: { bookId: string }) {
  const [norms, setNorms] = useState<PlotNorm[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState(EMPTY)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const response = await fetch(`/api/books/${bookId}/plot-norms`)
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      setNorms(data.norms || [])
    } catch {
      showToast('加载剧情规范失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetch(`/api/books/${bookId}/plot-norms`)
      .then(async response => {
        if (!response.ok) throw new Error(await response.text())
        return response.json()
      })
      .then(data => { if (!cancelled) setNorms(data.norms || []) })
      .catch(() => { if (!cancelled) showToast('加载剧情规范失败', 'error') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [bookId])

  function beginCreate() {
    setEditingId(null)
    setDraft(EMPTY)
    setShowForm(true)
  }

  function beginEdit(norm: PlotNorm) {
    setEditingId(norm.id)
    setDraft({
      name: norm.name,
      description: norm.description || '',
      rules: (norm.rules || []).join('\n'),
      avoid: (norm.avoid || []).join('\n'),
      active: norm.active,
    })
    setShowForm(true)
  }

  async function save() {
    if (!draft.name.trim()) {
      showToast('请填写规范名称', 'error')
      return
    }
    setSaving(true)
    const payload = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      rules: draft.rules.split('\n').map(line => line.trim()).filter(Boolean),
      avoid: draft.avoid.split('\n').map(line => line.trim()).filter(Boolean),
      active: draft.active,
    }
    try {
      const response = await fetch(
        editingId ? `/api/books/${bookId}/plot-norms/${editingId}` : `/api/books/${bookId}/plot-norms`,
        { method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
      )
      if (!response.ok) throw new Error(await response.text())
      setShowForm(false)
      await load()
      showToast(editingId ? '剧情规范已更新' : '剧情规范已创建', 'success')
    } catch (error) {
      showToast(`保存失败: ${error instanceof Error ? error.message : '未知错误'}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function toggle(norm: PlotNorm) {
    const response = await fetch(`/api/books/${bookId}/plot-norms/${norm.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: !norm.active }),
    })
    if (response.ok) setNorms(current => current.map(item => item.id === norm.id ? { ...item, active: !item.active } : item))
    else showToast('启用状态更新失败', 'error')
  }

  async function remove(norm: PlotNorm) {
    if (!window.confirm(`删除剧情规范“${norm.name}”？`)) return
    const response = await fetch(`/api/books/${bookId}/plot-norms/${norm.id}`, {
      method: 'DELETE', headers: { 'X-Confirm-Delete': 'true' },
    })
    if (response.ok) {
      setNorms(current => current.filter(item => item.id !== norm.id))
      showToast('剧情规范已删除', 'success')
    } else showToast('删除失败', 'error')
  }

  if (loading) return <LoadingState text="加载剧情规范..." />

  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-200"><Icon name="list" size={17} /> 剧情规范库</h2>
          <p className="mt-1 text-xs text-zinc-500">把反复调试的节奏、冲突、视角和禁用套路保存下来；只有启用项会注入写作。</p>
        </div>
        <button onClick={beginCreate} className="flex items-center gap-1.5 rounded-lg bg-sky-700 px-3 py-2 text-xs text-white hover:bg-sky-600">
          <Icon name="plus" size={13} /> 新建规范
        </button>
      </header>

      {showForm && (
        <section className="mb-5 space-y-3 rounded-xl border border-sky-900/60 bg-zinc-900/70 p-4">
          <input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} placeholder="规范名称，例如：慢燃悬疑章" className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-sky-700" />
          <textarea value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} placeholder="适用场景和目标（可选）" className="h-16 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-300 outline-none focus:border-sky-700" />
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs text-zinc-500">必须遵守（每行一条）
              <textarea value={draft.rules} onChange={e => setDraft({ ...draft, rules: e.target.value })} className="mt-1 h-32 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-300 outline-none focus:border-emerald-700" />
            </label>
            <label className="text-xs text-zinc-500">禁止套路（每行一条）
              <textarea value={draft.avoid} onChange={e => setDraft({ ...draft, avoid: e.target.value })} className="mt-1 h-32 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-300 outline-none focus:border-red-800" />
            </label>
          </div>
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-xs text-zinc-400"><input type="checkbox" checked={draft.active} onChange={e => setDraft({ ...draft, active: e.target.checked })} /> 创建后立即用于写作</label>
            <div className="flex gap-2"><button onClick={() => setShowForm(false)} className="px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300">取消</button><button disabled={saving} onClick={save} className="rounded-lg bg-sky-700 px-4 py-1.5 text-xs text-white disabled:opacity-50">{saving ? '保存中...' : '保存'}</button></div>
          </div>
        </section>
      )}

      {norms.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-800 py-16 text-center text-sm text-zinc-600">还没有剧情规范。先把你经常重复说明的创作要求保存成模板。</div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {norms.map(norm => <article key={norm.id} className={`rounded-xl border p-4 ${norm.active ? 'border-sky-900/70 bg-sky-950/10' : 'border-zinc-800 bg-zinc-900/40 opacity-70'}`}>
            <div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-medium text-zinc-200">{norm.name}</h3>{norm.description && <p className="mt-1 text-xs text-zinc-500">{norm.description}</p>}</div><button onClick={() => toggle(norm)} className={`rounded-full px-2 py-1 text-[10px] ${norm.active ? 'bg-emerald-900/50 text-emerald-300' : 'bg-zinc-800 text-zinc-500'}`}>{norm.active ? '写作中启用' : '已停用'}</button></div>
            {norm.rules?.length > 0 && <div className="mt-3 text-xs text-zinc-400"><span className="text-emerald-500">必须：</span>{norm.rules.slice(0, 4).join('；')}</div>}
            {norm.avoid?.length > 0 && <div className="mt-2 text-xs text-zinc-400"><span className="text-red-500">禁止：</span>{norm.avoid.slice(0, 4).join('；')}</div>}
            <div className="mt-4 flex justify-end gap-3 text-xs"><button onClick={() => beginEdit(norm)} className="text-zinc-500 hover:text-zinc-200">编辑</button><button onClick={() => remove(norm)} className="text-zinc-600 hover:text-red-400">删除</button></div>
          </article>)}
        </div>
      )}
    </div>
  )
}
