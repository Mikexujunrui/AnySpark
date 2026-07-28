import { useState, useMemo } from 'react'
import Modal from './ui/Modal'
import Icon from './ui/Icon'
import Toggle from './ui/Toggle'

interface TransformType {
  id: string
  label: string
  icon: string
  accent: string
  description: string
  placeholder: string
  fields: string[]
}

const TRANSFORM_TYPES: TransformType[] = [
  { id: 'apply_directive_globally', label: '一句话改全书', icon: 'zap', accent: 'amber', description: '自然语言指令对全书或指定范围执行统一变换', placeholder: '如：把所有"小姐"改成"姑娘"、战争场面描写更详细、第一人称改为第三人称', fields: ['directive', 'scope', 'execution_mode', 'dry_run'] },
  { id: 'find_replace_book', label: '查找替换', icon: 'edit', accent: 'sky', description: '全书字面或正则查找替换', placeholder: '要查找的文本', fields: ['pattern', 'replacement', 'scope', 'regex', 'dry_run'] },
  { id: 'transform_chapters_batch', label: '批量变换', icon: 'layers', accent: 'violet', description: '对选定章节批量应用 LLM 变换指令', placeholder: '如：增加环境描写、压缩对话加快节奏', fields: ['instruction', 'chapter_ids', 'mode', 'dry_run'] },
  { id: 'restyle_book', label: '文风调整', icon: 'pen-tool', accent: 'rose', description: '将指定文风应用到全部或指定章节', placeholder: '', fields: ['style_id', 'scope', 'dry_run'] },
  { id: 'summarize_book', label: '生成全书摘要', icon: 'clipboard-list', accent: 'emerald', description: '读取所有章节生成结构化摘要，注入长程上下文', placeholder: '', fields: [] },
]

const ACCENT_STYLES: Record<string, { ring: string; bg: string; text: string; glow: string }> = {
  amber: { ring: 'border-amber-500', bg: 'bg-amber-500/10', text: 'text-amber-400', glow: 'shadow-amber-500/20' },
  sky: { ring: 'border-sky-500', bg: 'bg-sky-500/10', text: 'text-sky-400', glow: 'shadow-sky-500/20' },
  violet: { ring: 'border-violet-500', bg: 'bg-violet-500/10', text: 'text-violet-400', glow: 'shadow-violet-500/20' },
  rose: { ring: 'border-rose-500', bg: 'bg-rose-500/10', text: 'text-rose-400', glow: 'shadow-rose-500/20' },
  emerald: { ring: 'border-emerald-500', bg: 'bg-emerald-500/10', text: 'text-emerald-400', glow: 'shadow-emerald-500/20' },
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-1.5">
        {label}{hint && <span className="text-zinc-600 font-normal">{hint}</span>}
      </label>
      {children}
    </div>
  )
}

const inputCls = 'w-full bg-zinc-800/80 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-accent focus:ring-1 focus:ring-accent/40 focus:outline-none transition-colors'

export default function BookTransformPanel({ open, onClose, onSend, styles = [] }: { open: boolean; onClose: () => void; onSend: (msg: string) => void; styles?: Record<string, any>[] }) {
  const [transformType, setTransformType] = useState('apply_directive_globally')
  const [directive, setDirective] = useState('')
  const [pattern, setPattern] = useState('')
  const [replacement, setReplacement] = useState('')
  const [instruction, setInstruction] = useState('')
  const [scope, setScope] = useState('all')
  const [chapterIds, setChapterIds] = useState('#1-#5')
  const [executionMode, setExecutionMode] = useState('auto')
  const [useRegex, setUseRegex] = useState(false)
  const [mode, setMode] = useState('patch')
  const [dryRun, setDryRun] = useState(false)
  const [styleId, setStyleId] = useState('')

  const currentType = TRANSFORM_TYPES.find(t => t.id === transformType)
  const accent = ACCENT_STYLES[currentType?.accent] || ACCENT_STYLES.amber
  const showField = (name: string) => currentType?.fields.includes(name)

  const canSend = useMemo(() => {
    if (transformType === 'apply_directive_globally') return directive.trim().length > 0
    if (transformType === 'find_replace_book') return pattern.trim().length > 0
    if (transformType === 'transform_chapters_batch') return instruction.trim().length > 0
    if (transformType === 'restyle_book') return !!styleId
    if (transformType === 'summarize_book') return true
    return false
  }, [transformType, directive, pattern, instruction, styleId])

  const preview = useMemo(() => {
    if (transformType === 'apply_directive_globally') return `apply_directive_globally · 指令「${directive.trim() || '…'}」· 范围 ${scope} · ${executionMode} · ${dryRun ? '预览' : '实际执行'}`
    if (transformType === 'find_replace_book') return `find_replace_book · 「${pattern.trim() || '…'}」→「${replacement.trim() || '…'}」· 范围 ${scope} · ${useRegex ? '正则' : '字面'} · ${dryRun ? '预览' : '实际执行'}`
    if (transformType === 'transform_chapters_batch') return `transform_chapters_batch · 「${instruction.trim() || '…'}」· 章节 ${chapterIds} · ${mode} · ${dryRun ? '预览' : '实际执行'}`
    if (transformType === 'restyle_book') return `restyle_book · 文风 ${styleId || '…'} · 范围 ${scope} · ${dryRun ? '预览' : '实际执行'}`
    if (transformType === 'summarize_book') return `summarize_book · 读取全部章节生成结构化摘要`
    return ''
  }, [transformType, directive, pattern, replacement, scope, executionMode, dryRun, useRegex, instruction, chapterIds, mode, styleId])

  function buildMessage(): string {
    if (transformType === 'apply_directive_globally') return `请使用 apply_directive_globally 工具执行以下指令：\n指令: ${directive}\n范围: ${scope}\n执行模式: ${executionMode}\n预览模式: ${dryRun ? '是' : '否'}`
    if (transformType === 'find_replace_book') return `请使用 find_replace_book 工具执行查找替换：\n查找: ${pattern}\n替换: ${replacement}\n范围: ${scope}\n正则模式: ${useRegex ? '是' : '否'}\n预览模式: ${dryRun ? '是' : '否'}`
    if (transformType === 'transform_chapters_batch') return `请使用 transform_chapters_batch 工具执行批量变换：\n指令: ${instruction}\n章节范围: ${chapterIds}\n模式: ${mode}\n预览模式: ${dryRun ? '是' : '否'}`
    if (transformType === 'restyle_book') return `请使用 restyle_book 工具执行文风调整：\n文风: ${styleId}\n范围: ${scope}\n预览模式: ${dryRun ? '是' : '否'}`
    if (transformType === 'summarize_book') return `请使用 summarize_book 工具生成全书摘要。`
    return ''
  }

  function handleSend() {
    if (!canSend) return
    onSend(buildMessage())
    handleClose()
  }

  function handleClose() {
    setDirective(''); setPattern(''); setReplacement(''); setInstruction('')
    setScope('all'); setChapterIds('#1-#5'); setExecutionMode('auto')
    setUseRegex(false); setMode('patch'); setDryRun(false); setStyleId('')
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="全书变换" size="lg">
      <div className="flex flex-col max-h-[85vh]">
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-3">
            <div className={`h-9 w-9 rounded-lg ${accent.bg} ${accent.ring} border flex items-center justify-center`}>
              <Icon name="layers" size={18} className={accent.text} />
            </div>
            <div><h2 className="text-base font-semibold text-zinc-100">全书变换</h2><p className="text-xs text-zinc-500 mt-0.5">批量修改已有章节 · 支持预览不实改</p></div>
          </div>
          <button onClick={handleClose} className="text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg p-1.5 transition-colors shrink-0" aria-label="关闭"><Icon name="x" size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 mb-2.5"><Icon name="target" size={13} /> 选择操作类型</div>
            <div className="grid grid-cols-2 gap-2">
              {TRANSFORM_TYPES.map(t => {
                const a = ACCENT_STYLES[t.accent]; const active = transformType === t.id
                return (
                  <button key={t.id} onClick={() => setTransformType(t.id)}
                    className={`group relative text-left p-2.5 rounded-lg border transition-all duration-150 ${active ? `${a.ring} ${a.bg} shadow-sm ${a.glow}` : 'border-zinc-700/70 bg-zinc-800/40 hover:border-zinc-600 hover:bg-zinc-800/70'}`}>
                    <div className="flex items-center gap-2">
                      <span className={`h-7 w-7 shrink-0 rounded-md flex items-center justify-center transition-colors ${active ? `${a.bg} ${a.text}` : 'bg-zinc-700/50 text-zinc-400 group-hover:text-zinc-300'}`}><Icon name={t.icon} size={14} /></span>
                      <span className={`text-sm font-medium ${active ? 'text-zinc-100' : 'text-zinc-300'}`}>{t.label}</span>
                    </div>
                    <p className="text-[11px] text-zinc-500 mt-1.5 leading-snug">{t.description}</p>
                  </button>
                )
              })}
            </div>
          </div>
          {showField('directive') && <Field label="修改指令"><textarea value={directive} onChange={(e) => setDirective(e.target.value)} placeholder={currentType?.placeholder} rows={3} className={`${inputCls} resize-none`} /></Field>}
          {showField('pattern') && <div className="grid grid-cols-2 gap-3"><Field label="查找"><input value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="要查找的文本" className={inputCls} /></Field><Field label="替换为"><input value={replacement} onChange={(e) => setReplacement(e.target.value)} placeholder="替换文本" className={inputCls} /></Field></div>}
          {showField('instruction') && <Field label="变换指令"><textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder={currentType?.placeholder} rows={2} className={`${inputCls} resize-none`} /></Field>}
          {showField('style_id') && <Field label="文风"><select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={inputCls}><option value="">选择文风...</option>{styles.map((s: any) => <option key={s.name} value={s.name}>{s.name} — {s.description?.slice(0, 40)}</option>)}</select></Field>}
          <div className="grid grid-cols-2 gap-3">
            {showField('scope') && <Field label="章节范围" hint="(all / #1-#5 / #1,#3,#7)"><input value={scope} onChange={(e) => setScope(e.target.value)} placeholder="all 或 #1-#5" className={inputCls} /></Field>}
            {showField('chapter_ids') && <Field label="章节范围" hint="(#1-#5 / #1,#3,#7)"><input value={chapterIds} onChange={(e) => setChapterIds(e.target.value)} placeholder="#1-#5 或 #1,#3,#7" className={inputCls} /></Field>}
            {showField('execution_mode') && <Field label="执行模式"><select value={executionMode} onChange={(e) => setExecutionMode(e.target.value)} className={inputCls}><option value="auto">自动判断</option><option value="parallel">并行（独立修改）</option><option value="serial">串行（前后关联）</option></select></Field>}
            {showField('mode') && <Field label="变换模式"><select value={mode} onChange={(e) => setMode(e.target.value)} className={inputCls}><option value="patch">patch（局部修改）</option><option value="rewrite">rewrite（完全重写）</option></select></Field>}
          </div>
          {(showField('regex') || showField('dry_run')) && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-1">
              {showField('regex') && <Toggle checked={useRegex} onChange={setUseRegex} label="正则模式" hint="使用正则表达式匹配" />}
              {showField('dry_run') && <Toggle checked={dryRun} onChange={setDryRun} label="预览模式" hint="不实际修改，仅查看变更" />}
            </div>
          )}
          {showField('dry_run') && !dryRun && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 border border-amber-700/40 px-3 py-2">
              <Icon name="alert-circle" size={14} className="text-amber-400 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-300/90 leading-relaxed">未开启预览模式，执行后将直接修改全书内容。建议首次操作时先用预览模式确认结果。</p>
            </div>
          )}
        </div>
        <div className="shrink-0 border-t border-zinc-800 px-5 py-3 space-y-2.5 bg-zinc-900/50">
          <div className="rounded-lg bg-zinc-950/60 border border-zinc-800 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-500 mb-1"><Icon name="file-text" size={11} /> 将发送的指令</div>
            <p className="text-xs text-zinc-400 leading-relaxed font-mono break-all">{preview}</p>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] text-zinc-600">{canSend ? '就绪' : '请填写必填项'}</span>
            <div className="flex items-center gap-2">
              <button onClick={handleClose} className="px-3.5 py-2 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors">取消</button>
              <button onClick={handleSend} disabled={!canSend} className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed ${dryRun ? 'bg-zinc-700 hover:bg-zinc-600 text-zinc-100' : 'bg-accent hover:bg-accent-hover text-white shadow-sm active:scale-95'}`}>
                <Icon name="play" size={13} /> {dryRun ? '预览变换' : '执行变换'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
