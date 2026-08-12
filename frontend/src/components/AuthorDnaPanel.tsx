import { useCallback, useEffect, useMemo, useState } from 'react'
import Icon from './ui/Icon'
import LoadingState from './ui/Skeleton'
import { showToast } from './ui/toast-utils'

type LayerStatus = 'pending' | 'needs_review' | 'accepted' | 'rejected'

interface DnaRule {
  text: string
  level?: string
  confidence?: string
  evidence_ids?: string[]
  counterexample_ids?: string[]
}

interface DnaLayer {
  key: string
  label: string
  status: LayerStatus
  summary: string
  rules: DnaRule[]
  anti_style: DnaRule[]
}

interface Interpretation {
  id: string
  statement: string
  classification: string
  confidence: string
  reason?: string
  evidence_ids?: string[]
  status: string
  promoted: boolean
}

interface DnaState {
  corpus: {
    status: string
    total_chars: number
    total_chapters: number
    total_chunks: number
    estimated_calls: number
    coverage: Array<{ ref_book_id: string; title: string; chapters: number; chars: number; chunks: number; quartiles: Record<string, number> }>
  }
  layers: Record<string, DnaLayer>
  observations: unknown[]
  audit: { status: string; passed: boolean; conflicts: Array<{ description?: string }>; warnings: string[] }
  interpretations: Interpretation[]
  scene_contract: Record<string, unknown>
  job: { id?: string; status: string; progress: number; message: string; error?: string; estimated_calls?: number }
}

interface SceneForm {
  enabled: boolean
  title: string
  creative_intent: string
  story_function: string
  purpose: string
  pov: string
  start_state: string
  end_state: string
  stop_anchor: string
  hidden_intent: string
  target_words: number
  beats: string
  allowed: string
  forbidden: string
  active_characters: string
  relevant_canon: string
  new_canon: string
}

const EMPTY_SCENE: SceneForm = {
  enabled: false,
  title: '',
  creative_intent: '',
  story_function: '',
  purpose: '',
  pov: '',
  start_state: '',
  end_state: '',
  stop_anchor: '',
  hidden_intent: '',
  target_words: 1600,
  beats: '',
  allowed: '动作、对白、微表情、感官细节、过渡',
  forbidden: '新增重大设定、改变既定人物关系、推进未提供的后续剧情',
  active_characters: '',
  relevant_canon: '',
  new_canon: '',
}

const CLASS_LABELS: Record<string, string> = {
  unverified: '未核验',
  strongly_supported: '原文强支持',
  plausible: '合理且相容',
  ambiguous: '存在多种解释',
  weakly_supported: '证据较弱',
  contradicted: '与重要证据冲突',
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || data.message || `请求失败 (${response.status})`)
  return data
}

function lines(value: string): string[] {
  return value.split('\n').map(item => item.trim().replace(/^[-*]\s*/, '')).filter(Boolean)
}

function sceneFromState(value: Record<string, unknown> | undefined): SceneForm {
  if (!value || Object.keys(value).length === 0) return EMPTY_SCENE
  const join = (field: string) => Array.isArray(value[field]) ? (value[field] as unknown[]).join('\n') : String(value[field] || '')
  return {
    enabled: Boolean(value.enabled),
    title: String(value.title || ''),
    creative_intent: String(value.creative_intent || ''),
    story_function: String(value.story_function || ''),
    purpose: String(value.purpose || ''),
    pov: String(value.pov || ''),
    start_state: String(value.start_state || ''),
    end_state: String(value.end_state || ''),
    stop_anchor: String(value.stop_anchor || ''),
    hidden_intent: String(value.hidden_intent || ''),
    target_words: Number(value.target_words || 1600),
    beats: join('beats'),
    allowed: join('allowed'),
    forbidden: join('forbidden'),
    active_characters: join('active_characters'),
    relevant_canon: join('relevant_canon'),
    new_canon: join('new_canon'),
  }
}

export default function AuthorDnaPanel({ bookId }: { bookId: string }) {
  const [state, setState] = useState<DnaState | null>(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [active, setActive] = useState<'corpus' | 'layers' | 'interpretations' | 'scene'>('corpus')
  const [expandedLayer, setExpandedLayer] = useState('')
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null)
  const [interpretationText, setInterpretationText] = useState('')
  const [scene, setScene] = useState<SceneForm>(EMPTY_SCENE)
  const [packageText, setPackageText] = useState('')

  const load = useCallback(async (quiet = false) => {
    try {
      const data = await request<DnaState>(`/api/books/${bookId}/author-dna`)
      setState(data)
      if (!quiet) setScene(sceneFromState(data.scene_contract))
    } catch (error) {
      if (!quiet) showToast(error instanceof Error ? error.message : '加载失败', 'error')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [bookId])

  useEffect(() => {
    let cancelled = false
    request<DnaState>(`/api/books/${bookId}/author-dna`)
      .then(data => {
        if (cancelled) return
        setState(data)
        setScene(sceneFromState(data.scene_contract))
      })
      .catch(error => {
        if (!cancelled) showToast(error instanceof Error ? error.message : '加载失败', 'error')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [bookId])

  useEffect(() => {
    const status = state?.job?.status
    if (!state?.job?.id || !['queued', 'running'].includes(status)) return
    const timer = window.setInterval(() => load(true), 1600)
    return () => window.clearInterval(timer)
  }, [state?.job?.id, state?.job?.status, load])

  async function buildCorpus() {
    setWorking('corpus')
    try {
      const data = await request<DnaState>(`/api/books/${bookId}/author-dna/corpus`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chunk_chars: 5000, batch_size: 3 }),
      })
      setState(data)
      showToast(`语料地图完成：${data.corpus.total_chunks} 个可核验证据块`, 'success')
    } catch (error) {
      showToast(error instanceof Error ? error.message : '建立语料地图失败', 'error')
    } finally { setWorking('') }
  }

  async function startAnalysis(force = false) {
    const calls = state?.corpus?.estimated_calls || 0
    if (!window.confirm(`本次预计约 ${calls} 次模型调用，并会按批次保存检查点。是否开始？`)) return
    setWorking('analysis')
    try {
      const job = await request<DnaState['job']>(`/api/books/${bookId}/author-dna/jobs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force }),
      })
      setState(old => old ? { ...old, job } : old)
      showToast('作者 DNA 分析已在后台开始', 'success')
    } catch (error) {
      showToast(error instanceof Error ? error.message : '启动失败', 'error')
    } finally { setWorking('') }
  }

  async function retryAnalysis() {
    if (!state?.job?.id) return
    try {
      const job = await request<DnaState['job']>(`/api/books/${bookId}/author-dna/jobs/${state.job.id}/retry`, { method: 'POST' })
      setState(old => old ? { ...old, job } : old)
    } catch (error) { showToast(error instanceof Error ? error.message : '继续失败', 'error') }
  }

  async function setLayerStatus(key: string, status: LayerStatus) {
    try {
      const layer = await request<DnaLayer>(`/api/books/${bookId}/author-dna/layers/${key}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
      })
      setState(old => old ? { ...old, layers: { ...old.layers, [key]: layer } } : old)
      showToast(status === 'accepted' ? '已确认：后续写作会使用这一层规则' : '已更新', 'success')
    } catch (error) { showToast(error instanceof Error ? error.message : '更新失败', 'error') }
  }

  async function viewEvidence(id: string) {
    try {
      setEvidence(await request(`/api/books/${bookId}/author-dna/evidence/${encodeURIComponent(id)}`))
    } catch (error) { showToast(error instanceof Error ? error.message : '证据读取失败', 'error') }
  }

  async function addInterpretation() {
    if (!interpretationText.trim()) return
    setWorking('interpretation')
    try {
      await request(`/api/books/${bookId}/author-dna/interpretations`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ statement: interpretationText }),
      })
      setInterpretationText('')
      await load(true)
    } catch (error) { showToast(error instanceof Error ? error.message : '保存失败', 'error') }
    finally { setWorking('') }
  }

  async function updateInterpretation(id: string, changes: Record<string, unknown>) {
    try {
      await request(`/api/books/${bookId}/author-dna/interpretations/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
      })
      await load(true)
    } catch (error) { showToast(error instanceof Error ? error.message : '更新失败', 'error') }
  }

  async function verifyInterpretation(id: string) {
    setWorking(id)
    try {
      await request(`/api/books/${bookId}/author-dna/interpretations/${id}/verify`, { method: 'POST' })
      await load(true)
      showToast('已与候选原文证据交叉核验；结果仍需你决定是否采纳', 'success')
    } catch (error) { showToast(error instanceof Error ? error.message : '核验失败', 'error') }
    finally { setWorking('') }
  }

  async function removeInterpretation(id: string) {
    try {
      await request(`/api/books/${bookId}/author-dna/interpretations/${id}`, { method: 'DELETE', headers: { 'X-Confirm-Delete': 'true' } })
      await load(true)
    } catch (error) { showToast(error instanceof Error ? error.message : '删除失败', 'error') }
  }

  const scenePayload = useMemo(() => ({
    ...scene,
    beats: lines(scene.beats), allowed: lines(scene.allowed), forbidden: lines(scene.forbidden),
    active_characters: lines(scene.active_characters), relevant_canon: lines(scene.relevant_canon), new_canon: lines(scene.new_canon),
  }), [scene])

  async function saveScene(compile = false) {
    setWorking('scene')
    try {
      await request(`/api/books/${bookId}/author-dna/scene-contract`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scenePayload),
      })
      if (compile) {
        const result = await request<{ text: string }>(`/api/books/${bookId}/author-dna/writer-package`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scenePayload),
        })
        setPackageText(result.text)
      }
      showToast(scene.enabled ? '场景合同已启用，正式写作会自动读取' : '场景合同已保存但未启用', 'success')
      await load(true)
    } catch (error) { showToast(error instanceof Error ? error.message : '保存失败', 'error') }
    finally { setWorking('') }
  }

  if (loading || !state) return <LoadingState text="加载作者 DNA 实验室..." />

  const accepted = Object.values(state.layers).filter(layer => layer.status === 'accepted').length
  const tabs = [
    { key: 'corpus' as const, label: '语料覆盖' },
    { key: 'layers' as const, label: `六层 DNA ${accepted}/6` },
    { key: 'interpretations' as const, label: '我的原作理解' },
    { key: 'scene' as const, label: '场景写作包' },
  ]

  return (
    <div className="h-full overflow-y-auto p-6 text-zinc-200">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Icon name="microscope" size={20} />作者 DNA 实验室 <span className="rounded bg-amber-950 px-2 py-0.5 text-[10px] font-normal text-amber-300">实验性 · 仅续写</span></h2>
          <p className="mt-1 text-xs leading-relaxed text-zinc-500">原文证据、作者规律、你的阅读理解和续写设定分层保存；未经确认的模型结论不会进入正文。</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] ${accepted === 6 ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300' : 'border-zinc-700 bg-zinc-900 text-zinc-400'}`}>{accepted === 6 ? 'DNA 已启用' : `${accepted}/6 层已确认`}</span>
      </header>

      <div className="mb-5 flex flex-wrap gap-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-1">
        {tabs.map(tab => <button key={tab.key} onClick={() => setActive(tab.key)} className={`rounded-lg px-3 py-2 text-xs transition ${active === tab.key ? 'bg-violet-700 text-white' : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300'}`}>{tab.label}</button>)}
      </div>

      {active === 'corpus' && <section className="space-y-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <div className="flex items-start justify-between gap-4">
            <div><h3 className="text-sm font-semibold">证据优先，不做一次性长文总结</h3><p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">参考书会按章节切成稳定块 ID。模型先逐批做六层观察，再分别蒸馏、交叉审计。每个规则都能点回原文。</p></div>
            <button disabled={working === 'corpus'} onClick={buildCorpus} className="shrink-0 rounded-lg bg-violet-700 px-3 py-2 text-xs text-white hover:bg-violet-600 disabled:opacity-50">{state.corpus.status === 'ready' ? '重建语料地图' : '建立语料地图'}</button>
          </div>
          {state.corpus.status === 'ready' && <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="参考总字数" value={(state.corpus.total_chars || 0).toLocaleString()} />
            <Metric label="章节" value={String(state.corpus.total_chapters || 0)} />
            <Metric label="证据块" value={String(state.corpus.total_chunks || 0)} />
            <Metric label="预计模型调用" value={`约 ${state.corpus.estimated_calls || 0} 次`} />
          </div>}
        </div>

        {state.corpus.coverage?.map(work => <div key={work.ref_book_id} className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
          <div className="flex items-center justify-between"><div><h4 className="text-sm font-medium">{work.title}</h4><p className="mt-1 text-[10px] text-zinc-500">{work.chapters} 章 · {work.chars.toLocaleString()} 字 · {work.chunks} 块</p></div><Icon name="book-open" size={18} className="text-violet-400" /></div>
          <div className="mt-3 grid grid-cols-4 gap-2">{Object.entries(work.quartiles || {}).map(([quartile, count]) => <div key={quartile} className={`rounded-lg border p-2 ${count > 0 ? 'border-emerald-900 bg-emerald-950/20' : 'border-red-900 bg-red-950/20'}`}><p className="text-[9px] text-zinc-500">{quartile}</p><p className={`mt-1 text-xs ${count > 0 ? 'text-emerald-300' : 'text-red-300'}`}>{count > 0 ? `${count} 块` : '无覆盖'}</p></div>)}</div>
        </div>)}

        {state.corpus.status === 'ready' && <div className="rounded-xl border border-sky-900/50 bg-sky-950/10 p-4">
          <div className="flex items-center justify-between gap-3"><div><h4 className="text-sm font-medium text-sky-300">六层后台蒸馏</h4><p className="mt-1 text-[10px] text-zinc-500">关闭页面仍会继续；失败时从最近批次恢复，不重复扣已完成的调用。</p></div>
            {['failed', 'interrupted'].includes(state.job.status) ? <button onClick={retryAnalysis} className="rounded-lg bg-amber-700 px-3 py-2 text-xs text-white">从检查点继续</button> : <button disabled={['queued', 'running'].includes(state.job.status) || working === 'analysis'} onClick={() => startAnalysis(state.job.status === 'completed')} className="rounded-lg bg-sky-700 px-3 py-2 text-xs text-white hover:bg-sky-600 disabled:opacity-50">{state.job.status === 'completed' ? '重新分析' : '开始完整分析'}</button>}
          </div>
          {state.job.status !== 'none' && <div className="mt-3"><div className="h-1.5 overflow-hidden rounded-full bg-zinc-800"><div className={`h-full transition-all ${state.job.status === 'failed' ? 'bg-red-500' : state.job.status === 'completed' ? 'bg-emerald-500' : 'bg-sky-500'}`} style={{ width: `${Math.max(2, state.job.progress || 0)}%` }} /></div><div className="mt-1.5 flex justify-between text-[10px] text-zinc-500"><span>{state.job.message}</span><span>{state.job.progress || 0}%</span></div>{state.job.error && <p className="mt-2 break-words text-[10px] text-red-400">{state.job.error}</p>}</div>}
        </div>}
      </section>}

      {active === 'layers' && <section className="space-y-3">
        {Object.entries(state.layers).map(([key, layer]) => {
          const open = expandedLayer === key
          return <div key={key} className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
            <button onClick={() => setExpandedLayer(open ? '' : key)} className="flex w-full items-center justify-between p-4 text-left"><div className="flex items-center gap-3"><span className={`h-2.5 w-2.5 rounded-full ${layer.status === 'accepted' ? 'bg-emerald-400' : layer.status === 'needs_review' ? 'bg-amber-400' : layer.status === 'rejected' ? 'bg-red-400' : 'bg-zinc-700'}`} /><div><h3 className="text-sm font-medium">{layer.label}</h3><p className="mt-0.5 text-[10px] text-zinc-500">{layer.rules?.length || 0} 条规则 · {layer.anti_style?.length || 0} 条反风格</p></div></div><Icon name={open ? 'chevron-up' : 'chevron-down'} size={14} /></button>
            {open && <div className="space-y-4 border-t border-zinc-800 p-4">
              {layer.summary && <p className="rounded-lg bg-zinc-950/60 p-3 text-xs leading-relaxed text-zinc-400">{layer.summary}</p>}
              <div className="space-y-2">{(layer.rules || []).map((rule, index) => <div key={index} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"><div className="flex gap-2"><span className="mt-0.5 text-[9px] text-violet-400">{rule.level || 'rule'}</span><p className="flex-1 text-xs leading-relaxed">{rule.text}</p></div>{rule.evidence_ids?.length ? <div className="mt-2 flex flex-wrap gap-1">{rule.evidence_ids.map(id => <button key={id} onClick={() => viewEvidence(id)} className="rounded bg-sky-950 px-1.5 py-0.5 text-[9px] text-sky-400 hover:text-sky-200">{id}</button>)}</div> : null}</div>)}</div>
              {layer.anti_style?.length > 0 && <div><h4 className="mb-2 text-xs font-medium text-rose-300">Anti-style</h4>{layer.anti_style.map((rule, index) => <p key={index} className="mb-1 rounded bg-rose-950/15 px-3 py-2 text-xs text-zinc-400">避免：{rule.text}</p>)}</div>}
              <div className="flex justify-end gap-2"><button onClick={() => setLayerStatus(key, 'rejected')} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-red-300">暂不采用</button><button onClick={() => setLayerStatus(key, 'accepted')} className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs text-white hover:bg-emerald-600">确认并用于写作</button></div>
            </div>}
          </div>
        })}
        {state.audit.status !== 'pending' && <div className={`rounded-xl border p-4 ${state.audit.passed ? 'border-emerald-900 bg-emerald-950/10' : 'border-amber-900 bg-amber-950/10'}`}><h3 className="text-sm font-medium">六层交叉审计：{state.audit.passed ? '未发现硬冲突' : '需要人工复核'}</h3>{state.audit.warnings?.map((warning, index) => <p key={index} className="mt-2 text-xs text-zinc-400">• {warning}</p>)}{state.audit.conflicts?.map((conflict, index) => <p key={index} className="mt-2 text-xs text-amber-300">• {conflict.description || JSON.stringify(conflict)}</p>)}</div>}
      </section>}

      {active === 'interpretations' && <section className="space-y-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4"><h3 className="text-sm font-medium">记录“我为什么喜欢这部作品”</h3><p className="mt-1 text-xs text-zinc-500">默认只是你的阅读解释，不会冒充原作事实；可让模型找证据核验，最后由你决定是否采纳或升级为本次续写 Canon。</p><textarea value={interpretationText} onChange={event => setInterpretationText(event.target.value)} rows={4} placeholder="例如：我认为她不是缺乏主动欲望，而是很在乎自己在对方面前显得太主动……" className="mt-3 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-xs leading-relaxed outline-none focus:border-violet-600" /><div className="mt-2 flex justify-end"><button disabled={!interpretationText.trim() || working === 'interpretation'} onClick={addInterpretation} className="rounded-lg bg-violet-700 px-3 py-2 text-xs text-white disabled:opacity-50">保存为待核验解读</button></div></div>
        {state.interpretations.map(item => <div key={item.id} className={`rounded-xl border p-4 ${item.promoted ? 'border-violet-700 bg-violet-950/15' : item.status === 'accepted' ? 'border-emerald-900 bg-emerald-950/10' : 'border-zinc-800 bg-zinc-900'}`}><div className="flex items-start justify-between gap-3"><p className="text-sm leading-relaxed">{item.statement}</p><button onClick={() => removeInterpretation(item.id)} className="text-zinc-600 hover:text-red-400"><Icon name="trash" size={13} /></button></div><div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]"><span className="rounded bg-zinc-800 px-2 py-1 text-zinc-400">{CLASS_LABELS[item.classification] || item.classification}</span>{item.confidence && item.confidence !== 'unknown' && <span className="text-zinc-500">置信度 {item.confidence}</span>}{item.promoted && <span className="rounded bg-violet-900 px-2 py-1 text-violet-300">续写解释 Canon</span>}</div>{item.reason && <p className="mt-3 rounded-lg bg-zinc-950/50 p-3 text-xs leading-relaxed text-zinc-500">{item.reason}</p>}{item.evidence_ids?.length ? <div className="mt-2 flex flex-wrap gap-1">{item.evidence_ids.map(id => <button key={id} onClick={() => viewEvidence(id)} className="rounded bg-sky-950 px-1.5 py-0.5 text-[9px] text-sky-400">{id}</button>)}</div> : null}<div className="mt-3 flex flex-wrap justify-end gap-2"><button disabled={working === item.id} onClick={() => verifyInterpretation(item.id)} className="rounded-lg border border-sky-800 px-3 py-1.5 text-xs text-sky-300 disabled:opacity-50">{working === item.id ? '核验中…' : '用原文证据核验'}</button>{item.status !== 'accepted' && <button onClick={() => updateInterpretation(item.id, { status: 'accepted' })} className="rounded-lg border border-emerald-800 px-3 py-1.5 text-xs text-emerald-300">采纳为阅读解释</button>}<button onClick={() => updateInterpretation(item.id, { promoted: !item.promoted })} className="rounded-lg bg-violet-800 px-3 py-1.5 text-xs text-white">{item.promoted ? '取消 Canon' : '采用为续写 Canon'}</button></div></div>)}
      </section>}

      {active === 'scene' && <section className="space-y-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4"><div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-medium">当前场景合同</h3><p className="mt-1 text-xs text-zinc-500">只保存当前场景；未来场景字段不会被 API 接受，也不会送给正文模型。</p></div><label className="flex items-center gap-2 text-xs text-zinc-400"><input type="checkbox" checked={scene.enabled} onChange={event => setScene(old => ({ ...old, enabled: event.target.checked }))} className="accent-violet-500" />自动注入正式写作</label></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="场景名" value={scene.title} onChange={value => setScene(old => ({ ...old, title: value }))} /><Field label="POV / 叙事距离" value={scene.pov} onChange={value => setScene(old => ({ ...old, pov: value }))} /><Field label="优先保留的创作意图" value={scene.creative_intent} onChange={value => setScene(old => ({ ...old, creative_intent: value }))} /><Field label="剧情功能" value={scene.story_function} onChange={value => setScene(old => ({ ...old, story_function: value }))} /><Field label="本场唯一目的" value={scene.purpose} onChange={value => setScene(old => ({ ...old, purpose: value }))} /><Field label="表层之下的意图" value={scene.hidden_intent} onChange={value => setScene(old => ({ ...old, hidden_intent: value }))} /><Field label="开始状态" value={scene.start_state} onChange={value => setScene(old => ({ ...old, start_state: value }))} /><Field label="结束状态" value={scene.end_state} onChange={value => setScene(old => ({ ...old, end_state: value }))} /><Field label="停止锚点（到此立刻停）" value={scene.stop_anchor} onChange={value => setScene(old => ({ ...old, stop_anchor: value }))} /><label className="block text-[10px] text-zinc-500">目标字数<input type="number" value={scene.target_words} onChange={event => setScene(old => ({ ...old, target_words: Number(event.target.value) }))} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-violet-600" /></label></div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2"><Area label="当前 Beats（每行一项）" value={scene.beats} onChange={value => setScene(old => ({ ...old, beats: value }))} /><Area label="当前人物状态" value={scene.active_characters} onChange={value => setScene(old => ({ ...old, active_characters: value }))} /><Area label="当前场景所需原作事实" value={scene.relevant_canon} onChange={value => setScene(old => ({ ...old, relevant_canon: value }))} /><Area label="本次新增 Canon" value={scene.new_canon} onChange={value => setScene(old => ({ ...old, new_canon: value }))} /><Area label="允许自由发挥" value={scene.allowed} onChange={value => setScene(old => ({ ...old, allowed: value }))} /><Area label="禁止项" value={scene.forbidden} onChange={value => setScene(old => ({ ...old, forbidden: value }))} /></div>
          <div className="mt-4 flex justify-end gap-2"><button disabled={working === 'scene'} onClick={() => saveScene(false)} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300">保存</button><button disabled={working === 'scene'} onClick={() => saveScene(true)} className="rounded-lg bg-violet-700 px-3 py-2 text-xs text-white">保存并预览写作包</button></div>
        </div>
        {packageText && <div className="rounded-xl border border-violet-900 bg-zinc-950 p-4"><div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-medium text-violet-300">正文模型实际会看到的内容</h3><button onClick={() => navigator.clipboard?.writeText(packageText)} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-200"><Icon name="copy" size={12} />复制</button></div><pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-zinc-400">{packageText}</pre></div>}
      </section>}

      {evidence && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={() => setEvidence(null)}><div className="max-h-[80vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-950 p-5 shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-medium text-sky-300">{String(evidence.id || '')}</h3><p className="mt-1 text-[10px] text-zinc-500">{String(evidence.ref_title || '')} / {String(evidence.chapter_title || '')}</p></div><button onClick={() => setEvidence(null)}><Icon name="x" size={16} /></button></div><pre className="mt-4 whitespace-pre-wrap break-words text-sm leading-7 text-zinc-300">{String(evidence.text || '')}</pre></div></div>}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"><p className="text-[9px] text-zinc-600">{label}</p><p className="mt-1 text-sm font-medium text-zinc-300">{value}</p></div>
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-[10px] text-zinc-500">{label}<input value={value} onChange={event => onChange(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-violet-600" /></label>
}

function Area({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-[10px] text-zinc-500">{label}<textarea rows={4} value={value} onChange={event => onChange(event.target.value)} className="mt-1 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-200 outline-none focus:border-violet-600" /></label>
}
