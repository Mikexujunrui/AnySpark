import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Panel, Group, Separator } from 'react-resizable-panels'
import { storage } from "../storage"
import { api } from "../api"
import { showToast } from './ui/Toast'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import PanelHost from './panels/PanelHost'
import { useSplitLayout } from "../hooks/useSplitLayout"
import SettingsModal from './SettingsModal'
import ShortcutsModal from './ShortcutsModal'
import SessionMenu from './SessionMenu'
import ExportMenu from './ExportMenu'
import AutopilotModal from './AutopilotModal'
import TaskProgressPanel from './TaskProgressPanel'
import SupervisorBadge from './SupervisorBadge'
import ImportDialog from './ImportDialog'
import ThemeToggle from './ThemeToggle'
import CommandPalette from './CommandPalette'

interface TabConfig { key: string; label: string; icon: string }
interface TabGroup { label: string; tabs: TabConfig[] }
interface LLMMode { key: string; label: string; badge: string }

const TAB_GROUPS: TabGroup[] = [
  {
    label: '写作',
    tabs: [
      { key: 'chat', label: '对话', icon: 'message-circle' },
      { key: 'chapters', label: '章节', icon: 'file-text' },
      { key: 'interactive', label: '互动', icon: 'message-circle' },
      { key: 'files', label: '文件', icon: 'folder' },
    ],
  },
  {
    label: '设定',
    tabs: [
      { key: 'characters', label: '角色', icon: 'users' },
      { key: 'map', label: '地图', icon: 'map' },
      { key: 'worldbuilding', label: '世界观', icon: 'globe' },
      { key: 'knowledge', label: '知识库', icon: 'database' },
    ],
  },
  {
    label: '辅助',
    tabs: [
      { key: 'outline', label: '大纲', icon: 'list' },
      { key: 'timeline', label: '时间线', icon: 'clock' },
      { key: 'foreshadows', label: '伏笔', icon: 'target' },
      { key: 'references', label: '参考书', icon: 'book-open' },
    ],
  },
  {
    label: '工具',
    tabs: [
      { key: 'styles', label: '导演', icon: 'pen-tool' },
      { key: 'workflow', label: '工作流', icon: 'settings' },
      { key: 'review', label: '评审团', icon: 'clipboard-list' },
      { key: 'search', label: '搜索', icon: 'search' },
    ],
  },
]

const ALL_TABS: TabConfig[] = TAB_GROUPS.flatMap(g => g.tabs)

const LLM_MODES: LLMMode[] = [
  { key: 'quality', label: 'Pro', badge: 'bg-amber-900/40 text-amber-400 border border-amber-800/50' },
  { key: 'split', label: 'Split', badge: 'bg-blue-900/40 text-blue-400 border border-blue-800/50' },
  { key: 'flash', label: 'Flash', badge: 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' },
  { key: 'custom', label: 'Custom', badge: 'bg-purple-900/40 text-purple-400 border border-purple-800/50' },
]

const DEFAULT_MODE = LLM_MODES[1]

function modeConfig(mode: string): LLMMode {
  return LLM_MODES.find(m => m.key === mode) || DEFAULT_MODE
}

export default function BookDetail() {
  const { bookId } = useParams<{ bookId: string }>()
  const { isSplit, primaryTab, secondaryTab, toggleSplit, setPrimaryTab, setSecondaryTab } = useSplitLayout(bookId!, storage.getActiveTab(bookId!))
  const [book, setBook] = useState<Record<string, any> | null>(null)
  const [llmMode, setLlmMode] = useState<string>(DEFAULT_MODE.key)
  const [loadingErr, setLoadingErr] = useState('')
  const [sessions, setSessions] = useState<Record<string, any>[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [showSessionMenu, setShowSessionMenu] = useState(false)
  const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showAutopilot, setShowAutopilot] = useState(false)
  const [transformSignal, setTransformSignal] = useState(0)
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [autoModeEnabled, setAutoModeEnabled] = useState(() => storage.getAutoMode(bookId!) ?? false)
  const [retryKey, setRetryKey] = useState(0)
  const [showImport, setShowImport] = useState(false)
  const [showCommandPalette, setShowCommandPalette] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoadingErr('')
    storage.setLastBook(bookId!)
    api.getBook(bookId!).then(data => { if (!cancelled) setBook(data as Record<string, any>) }).catch(() => {})
    async function load() {
      try {
        const sess = await api.getSessions(bookId!)
        if (cancelled) return
        setSessions(sess as Record<string, any>[])
        const savedSession = storage.getActiveSession(bookId!)
        const found = (sess as Record<string, any>[]).find((s: Record<string, any>) => s.id === savedSession)
        if (found) {
          setSessionId(found.id)
        } else if ((sess as any[]).length > 0) {
          setSessionId((sess as any[])[0].id)
          storage.setActiveSession(bookId!, (sess as any[])[0].id)
        } else {
          const ns = await api.createSession(bookId!, '默认会话')
          if (cancelled) return
          setSessions([ns as Record<string, any>])
          setSessionId((ns as any).id)
          storage.setActiveSession(bookId!, (ns as any).id)
        }
      } catch {
        if (!cancelled) setLoadingErr('后端连接失败')
      }
    }
    load()
    api.getSettings().then(d => { if (!cancelled) setLlmMode(d.mode || DEFAULT_MODE.key) }).catch(() => {})
    return () => { cancelled = true }
  }, [bookId, retryKey])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && !e.altKey) {
        const num = parseInt(e.key)
        if (num >= 1 && num <= ALL_TABS.length) {
          e.preventDefault()
          if (isSplit && e.shiftKey) {
            switchSecondaryTab(ALL_TABS[num - 1].key)
          } else {
            switchTab(ALL_TABS[num - 1].key)
          }
        }
      }
      if (e.ctrlKey && e.key === '.') {
        e.preventDefault()
        setShowSessionMenu(prev => !prev)
      }
      if (e.ctrlKey && (e.key === '/' || e.key === '?')) {
        e.preventDefault()
        setShowShortcuts(prev => !prev)
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setShowCommandPalette(prev => !prev)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, isSplit])

  function switchTab(t: string) {
    setPrimaryTab(t)
    storage.setActiveTab(bookId!, t)
  }

  function switchSecondaryTab(t: string) {
    setSecondaryTab(t)
  }

  function switchSession(sid: string) {
    setSessionId(sid)
    storage.setActiveSession(bookId!, sid)
    setShowSessionMenu(false)
  }

  async function toggleMode() {
    const idx = LLM_MODES.findIndex(m => m.key === llmMode)
    const newMode = LLM_MODES[(idx + 1) % LLM_MODES.length].key
    try {
      const data = await api.switchMode(newMode)
      setLlmMode(data.mode || newMode)
    } catch {
      showToast('模式切换失败', 'error')
    }
  }

  async function handleNewSession() {
    try {
      const ns = await api.createSession(bookId!, `会话 ${sessions.length + 1}`)
      setSessions(prev => [ns as Record<string, any>, ...prev])
      switchSession((ns as any).id)
      setShowSessionMenu(false)
    } catch {
      showToast('创建会话失败', 'error')
    }
  }

  async function handleDeleteSession() {
    if (!deleteSessionId) return
    const deletedSession = sessions.find(s => s.id === deleteSessionId)
    const deletedId = deleteSessionId
    setDeleteSessionId(null)

    setSessions(prev => prev.filter(s => s.id !== deletedId))
    if (deletedId === sessionId) {
      const remaining = sessions.filter(s => s.id !== deletedId)
      if (remaining.length > 0) {
        switchSession(remaining[0].id)
      } else {
        handleNewSession()
      }
    }

    showToast(`已删除"${deletedSession?.title || '会话'}"`, 'info', 5000, async () => {
      try {
        const restored = await api.createSession(bookId!, deletedSession?.title || '恢复的会话')
        setSessions(prev => [restored as Record<string, any>, ...prev])
        showToast('已恢复会话', 'success')
      } catch {
        showToast('恢复失败', 'error')
      }
    })

    setTimeout(() => {
      api.deleteSession(bookId!, deletedId).catch(() => {})
    }, 5000)
  }

  function handleExport(format: string) {
    setShowExportMenu(false)
    const title = book?.title || 'export'
    const a = document.createElement('a')
    a.href = `/api/books/${bookId}/export?format=${format}`
    a.download = `${title}.${format === 'docx' ? 'docx' : 'txt'}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  if (loadingErr) {
    return <div className="flex flex-col items-center justify-center min-h-screen text-zinc-400 gap-4">
      <Icon name="alert-circle" size={32} className="text-amber-500" aria-label="错误" />
      <p className="text-zinc-300 text-lg">{loadingErr}</p>
      <div className="flex gap-3">
        <button onClick={() => setRetryKey(k => k + 1)} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2 rounded-lg text-sm flex items-center gap-2">
          <Icon name="refresh" size={14} /> 重试
        </button>
        <Link to="/" className="text-zinc-500 hover:text-zinc-300 px-4 py-2 text-sm flex items-center gap-2">
          <Icon name="arrow-left" size={14} /> 返回书架
        </Link>
      </div>
    </div>
  }

  if (!sessionId) {
    return <div className="flex flex-col items-center justify-center min-h-screen text-zinc-500 gap-3">
      <div className="w-6 h-6 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" role="status" aria-label="加载中" />
      <span className="text-sm">加载中...</span>
    </div>
  }

  const currentSessionTitle = sessions.find(s => s.id === sessionId)?.title || '会话'
  const modeConf = modeConfig(llmMode)

  return (
    <div className="h-screen flex flex-col">
      <header className="flex flex-col border-b border-zinc-800 bg-zinc-950 shrink-0 relative z-10">
        <div className="flex items-center gap-1.5 px-4 pt-2 pb-1 text-xs text-zinc-500">
          <Link to="/" className="hover:text-zinc-300 transition-colors">书架</Link>
          <span className="text-zinc-700">/</span>
          <span className="text-zinc-400 truncate" aria-current="page">{book?.title || '加载中...'}</span>
        </div>
        <div className="flex items-center gap-3 px-4 pb-2">
          <Link to="/" className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="返回书架" aria-label="返回书架">
            <Icon name="arrow-left" size={18} />
          </Link>
          <div className="h-5 w-px bg-zinc-800 shrink-0" />
          <h1 className="text-sm font-medium text-zinc-300 truncate flex-1 min-w-0">{currentSessionTitle}</h1>

          <button
            onClick={() => { const next = !autoModeEnabled; setAutoModeEnabled(next); storage.setAutoMode(bookId!, next) }}
            className="group relative inline-flex items-center gap-2 shrink-0"
            title={autoModeEnabled ? '自动模式已开启 — 点击关闭' : '自动模式已关闭 — 点击开启'}
          >
            <Icon name="bot" size={14} className={`transition-colors ${autoModeEnabled ? 'text-purple-400' : 'text-zinc-500'}`} />
            <span className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${autoModeEnabled ? 'bg-purple-600/60 border border-purple-500/40' : 'bg-zinc-700 border border-zinc-600'}`}>
              <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${autoModeEnabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
            </span>
          </button>

          {autoModeEnabled && (
            <>
              <button onClick={() => setShowAutopilot(true)} className="text-xs px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 bg-purple-900/40 text-purple-400 border border-purple-800/50 hover:bg-purple-800/50 flex items-center gap-1.5" title="Autopilot 自主写作">
                <Icon name="bot" size={12} /> Auto
              </button>
              <SupervisorBadge bookId={bookId!} onOpenTasks={() => setActiveTaskId('list')} />
            </>
          )}

          <button onClick={toggleMode} className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 ${modeConf.badge}`} title={`当前: ${modeConf.label} 模式 (点击循环切换)`} aria-label={`LLM 模式：${modeConf.label}，点击切换`}>
            {modeConf.label}
          </button>
          <button onClick={() => setShowSettings(true)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="API 设置" aria-label="API 设置">
            <Icon name="settings" size={16} />
          </button>
          <ThemeToggle />
          <div className="relative">
            <button onClick={() => setShowExportMenu(!showExportMenu)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="导出全文" aria-label="导出全文" aria-expanded={showExportMenu}>
              <Icon name="download" size={16} />
            </button>
            <ExportMenu open={showExportMenu} onClose={() => setShowExportMenu(false)} onExport={handleExport} />
          </div>
          <button onClick={() => setShowImport(true)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="导入小说" aria-label="导入小说">
            <Icon name="upload" size={16} />
          </button>
          <div className="relative">
            <button onClick={() => setShowSessionMenu(!showSessionMenu)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="会话管理" aria-label="会话管理" aria-expanded={showSessionMenu}>
              <Icon name="more-horizontal" size={18} />
            </button>
            <SessionMenu open={showSessionMenu} sessions={sessions} sessionId={sessionId} onSwitch={switchSession} onNew={handleNewSession} onDelete={(sid) => { setDeleteSessionId(sid); setShowSessionMenu(false) }} onClose={() => setShowSessionMenu(false)} />
          </div>
        </div>
      </header>

      <nav className="flex border-b border-zinc-800 bg-zinc-950 shrink-0 overflow-x-auto" aria-label="功能区">
        {TAB_GROUPS.map((group, gi) => (
          <div key={group.label} className="flex items-stretch shrink-0">
            {gi > 0 && <div className="w-px bg-zinc-800/60 my-2" />}
            <div className="flex">
              {group.tabs.map(t => {
                const idx = ALL_TABS.indexOf(t)
                const isPrimary = primaryTab === t.key
                const isSecondary = isSplit && secondaryTab === t.key
                return (
                  <button key={t.key} onClick={() => isSplit ? setPrimaryTab(t.key) : switchTab(t.key)}
                    onContextMenu={(e) => { if (isSplit) { e.preventDefault(); switchSecondaryTab(t.key) } }}
                    title={`${t.label}${isSplit ? ' (左键=主面板, 右键=次面板)' : ` (Ctrl+${idx + 1})`}`}
                    aria-current={isPrimary ? 'page' : undefined}
                    className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-all border-b-2 whitespace-nowrap relative ${isPrimary ? 'border-accent text-zinc-100' : isSecondary ? 'border-purple-500/60 text-purple-300' : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'}`}>
                    <Icon name={t.icon} size={14} />
                    <span className="hidden sm:inline">{t.label}</span>
                    {isSecondary && <span className="absolute -top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-purple-400" />}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        <div className="ml-auto flex items-center px-2">
          <button onClick={toggleSplit} title={isSplit ? '合并为单面板' : '分屏显示 (同时查看两个面板)'}
            className={`text-xs px-2 py-1 rounded transition-colors flex items-center gap-1 ${isSplit ? 'bg-purple-900/40 text-purple-300' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'}`}>
            <Icon name="columns" size={12} />
            <span className="hidden sm:inline">{isSplit ? '合并' : '分屏'}</span>
          </button>
        </div>
      </nav>

      <div className="flex-1 overflow-hidden">
        <Group orientation="horizontal">
          <Panel defaultSize={isSplit ? 50 : 100} minSize={25}>
            <PanelHost panelKey={primaryTab} bookId={bookId!} sessionId={sessionId} autoModeEnabled={autoModeEnabled} transformSignal={transformSignal} />
          </Panel>
          {isSplit && (
            <>
              <Separator className="w-1 bg-zinc-800 hover:bg-sky-600 transition-colors cursor-col-resize shrink-0" />
              <Panel defaultSize={50} minSize={25}>
                <PanelHost panelKey={secondaryTab} bookId={bookId!} sessionId={sessionId} autoModeEnabled={autoModeEnabled} transformSignal={transformSignal} />
              </Panel>
            </>
          )}
        </Group>
      </div>

      <ConfirmModal open={!!deleteSessionId} title="删除会话" message="删除此会话？消息历史将永久删除。" confirmText="删除" danger onConfirm={handleDeleteSession} onCancel={() => setDeleteSessionId(null)} />
      <ShortcutsModal open={showShortcuts} onClose={() => setShowShortcuts(false)} />
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} onModeChanged={(mode: string) => setLlmMode(mode)} bookId={bookId} />}
      {showAutopilot && <AutopilotModal bookId={bookId!} onClose={() => setShowAutopilot(false)} onTaskCreated={(taskId: string) => setActiveTaskId(taskId)} onOpenTransform={() => { setShowAutopilot(false); setTransformSignal(v => v + 1) }} />}
      {activeTaskId && activeTaskId !== 'list' && (
        <div style={{ position: 'fixed', bottom: '20px', right: '20px', width: '380px', zIndex: 50 }}>
          <TaskProgressPanel bookId={bookId!} taskId={activeTaskId} onClose={() => setActiveTaskId(null)} />
        </div>
      )}
      {showImport && <ImportDialog bookId={bookId!} onClose={() => setShowImport(false)} />}
      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} />
    </div>
  )
}
