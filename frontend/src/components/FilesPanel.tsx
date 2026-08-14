// FilesPanel — AI 文件沙箱浏览（S141 审计缺口①修复）
// read_file/write_file 工具（S60 纯文档通道）的产物（笔记/灵感/参考资料）在此可见，
// 人类可读 AI 记的内容——"内容自然语言可编辑"闭环：AI 写的东西人能看到。
import { useState, useEffect, useCallback } from 'react'
import Icon from './ui/Icon'
import PanelHeader from './ui/PanelHeader'
import { showToast } from './ui/toast-utils'

interface SandboxFile {
  path: string
  name: string
  size: number
  mtime: number
}

interface Props {
  open?: boolean
  onClose?: () => void
  embedded?: boolean
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function FilesPanel({ open = true, onClose, embedded = false }: Props) {
  const [files, setFiles] = useState<SandboxFile[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [dirs, setDirs] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/sandbox')
      const d = await r.json()
      const list: SandboxFile[] = d.files || []
      setFiles(list)
      // 目录树（含子目录路径）
      const ds = new Set<string>()
      for (const f of list) {
        const parts = f.path.split('/')
        if (parts.length > 1) ds.add(parts[0])
      }
      setDirs(Array.from(ds).sort())
    } catch {
      showToast('加载沙箱文件失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const openFile = async (path: string) => {
    setSelected(path)
    setContentLoading(true)
    try {
      const r = await fetch(`/api/sandbox/file?path=${encodeURIComponent(path)}`)
      if (!r.ok) throw new Error((await r.json()).detail || '读取失败')
      const d = await r.json()
      setContent(d.content || '')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '读取失败', 'error')
      setContent('')
    } finally {
      setContentLoading(false)
    }
  }

  const filtered = query
    ? files.filter(f => f.path.toLowerCase().includes(query.toLowerCase()))
    : files

  if (!open) return null

  return (
    <div className={embedded ? 'h-full flex flex-col' : 'fixed inset-0 z-50 flex'}>
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}
      <div className={embedded ? 'h-full w-full flex flex-col' : 'relative ml-auto w-[720px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl'}>
        <PanelHeader
          compact
          maxW={false}
          icon="folder"
          iconClass="text-sky-400"
          title="AI文件"
          desc="read_file/write_file 产物（笔记/灵感/参考资料）"
          actions={
            <div className="flex items-center gap-1">
              <button onClick={() => void load()} className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-zinc-800" title="刷新">
                <Icon name="refresh" size={14} />
              </button>
              {onClose && (
                <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-zinc-800" title="关闭">
                  <Icon name="x" size={14} />
                </button>
              )}
            </div>
          }
        />

        <div className="px-3 pt-2">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="过滤文件路径…"
            className="w-full bg-zinc-800 text-zinc-200 text-xs px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
          />
        </div>

        <div className="flex-1 min-h-0 flex">
          {/* 文件列表 */}
          <div className="w-64 border-r border-zinc-800 overflow-y-auto shrink-0">
            {loading ? (
              <p className="text-center text-zinc-600 text-xs py-8">加载中…</p>
            ) : filtered.length === 0 ? (
              <p className="text-center text-zinc-600 text-xs py-8">暂无文件（AI 用 write_file 写入后出现）</p>
            ) : (
              <div className="p-2 space-y-0.5">
                {dirs.length > 0 && (
                  <div className="px-2 py-1 text-[10px] text-zinc-600 uppercase tracking-wide">目录</div>
                )}
                {dirs.map(d => (
                  <div key={d} className="flex items-center gap-1.5 px-2 py-1 text-xs text-zinc-500">
                    <Icon name="folder" size={12} />
                    <span>{d}/</span>
                  </div>
                ))}
                <div className="px-2 pt-2 text-[10px] text-zinc-600 uppercase tracking-wide">文件（{filtered.length}）</div>
                {filtered.map(f => (
                  <button
                    key={f.path}
                    onClick={() => void openFile(f.path)}
                    className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors flex items-center gap-1.5 ${
                      selected === f.path ? 'bg-sky-900/30 text-sky-200' : 'text-zinc-400 hover:bg-zinc-800/70'
                    }`}
                  >
                    <Icon name="file-text" size={12} className="shrink-0 text-zinc-600" />
                    <span className="truncate flex-1">{f.path}</span>
                    <span className="text-[10px] text-zinc-600 shrink-0">{fmtSize(f.size)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 内容预览 */}
          <div className="flex-1 min-h-0 flex flex-col">
            {selected ? (
              <>
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800 shrink-0">
                  <span className="text-xs text-zinc-400 truncate">{selected}</span>
                  {files.find(f => f.path === selected) && (
                    <span className="text-[10px] text-zinc-600 shrink-0 ml-2">
                      {fmtTime(files.find(f => f.path === selected)!.mtime)}
                    </span>
                  )}
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {contentLoading ? (
                    <p className="text-zinc-600 text-xs">读取中…</p>
                  ) : (
                    <pre className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed font-sans">{content}</pre>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-zinc-600 text-xs">选择左侧文件查看内容</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
