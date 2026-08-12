import { useState, useEffect } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { Panel, Group, Separator } from 'react-resizable-panels'
import { ApprovalProvider } from './approval/ApprovalContext'
import { onTabSwitch } from '../lib/events'
import { storage } from "../storage"
import { api } from "../api"
import { showToast } from './ui/toast-utils'
import Icon from './ui/Icon'
import ConfirmModal from './ui/ConfirmModal'
import PanelHost from './panels/PanelHost'
import { useSplitLayout } from "../hooks/useSplitLayout"
import SettingsModal from './SettingsModal'
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
      { key: 'explore', label: '探索', icon: 'compass' },
      { key: 'chapters', label: '章节', icon: 'file-text' },
      { key: 'storytree', label: '叙事树', icon: 'git-branch' },
      { key: 'workflow', label: '工作流', icon: 'settings' },
      { key: 'search', label: '搜索', icon: 'search' },
    ],
  },
  {
    label: '设定',
    tabs: [
      { key: 'knowledge', label: '知识库', icon: 'database' },
      { key: 'outline', label: '大纲', icon: 'list' },
      { key: 'foreshadows', label: '伏笔', icon: 'target' },
      { key: 'materials', label: '资料', icon: 'book-open' },
      { key: 'references', label: '参考书', icon: 'book-marked' },
    ],
  },
  {
    label: '辅助',
    tabs: [
      { key: 'styles', label: '技巧', icon: 'pen-tool' },
      { key: 'review', label: '评审团', icon: 'clipboard-list' },
      { key: 'brief', label: '简介', icon: 'file-text' },
      { key: 'bias', label: 'AI倾向', icon: 'brain' },
    ],
  },
  {
    label: '工具',
    tabs: [
      { key: 'batch', label: '批量', icon: 'layers' },
      { key: 'templates', label: '模板', icon: 'copy' },
      { key: 'tools', label: '扩展工具', icon: 'wrench' },
      { key: 'play', label: '互动推演', icon: 'compass' },
      { key: 'dims', label: '维度', icon: 'grid' },
      { key: 'upload', label: '上传', icon: 'upload' },
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

// 审批节点宿主：全局 ApprovalProvider（自主模式联动，不耦合业务）
export default function BookDetailWrapper() {
  return (
    <ApprovalProvider>
      <BookDetail />
    </ApprovalProvider>
  )
}

function BookDetail() {
  const { bookId } = useParams<{ bookId: string }>()
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get('tab')
  const { isSplit, primaryTab, secondaryTab, toggleSplit, setPrimaryTab, setSecondaryTab } = useSplitLayout(bookId!, urlTab || storage.getActiveTab(bookId!))
  const [book, setBook] = useState<Record<string, any> | null>(null)
  const [llmMode, setLlmMode] = useState<string>(DEFAULT_MODE.key)
  const [loadingErr, setLoadingErr] = useState('')
  const [sessions, setSessions] = useState<Record<string, any>[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [showSessionMenu, setShowSessionMenu] = useState(false)
  const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
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
    api.getSettings().then((d: any) => { if (!cancelled) setLlmMode(d.mode || DEFAULT_MODE.key) }).catch(() => {})
    return () => { cancelled = true }
  }, [bookId])

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

  // 监听斜杠 UI 命令的 tab 切换事件（/tree /graph /outline 等）
  useEffect(() => {
    const off = onTabSwitch((tab) => {
      if (tab === 'settings') {
        setShowSettings(true)  // 设置是弹窗不是 tab
        return
      }
      switchTab(tab)
    })
    return off
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId])

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
      setLlmMode((data as any).mode || newMode)
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

    setTimeout(() => {
      api.deleteSession(bookId!, deletedId).catch(() => {})
    }, 3000)
  }

  if (loadingErr) {
    return <div className="flex flex-col items-center justify-center min-h-screen text-zinc-400 gap-4">
      <Icon name="alert-circle" size={32} className="text-amber-500" aria-label="错误" />
      <p className="text-zinc-300 text-lg">{loadingErr}</p>
      <div className="flex gap-3">
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

          <button onClick={toggleMode} className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors shrink-0 ${modeConf.badge}`} title={`当前: ${modeConf.label} 模式 (点击循环切换)`} aria-label={`LLM 模式：${modeConf.label}，点击切换`}>
            {modeConf.label}
          </button>
          <button onClick={() => setShowSettings(true)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="设置" aria-label="设置">
            <Icon name="settings" size={16} />
          </button>
          <ThemeToggle />
          <div className="relative">
            <button onClick={() => setShowExportMenu(!showExportMenu)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="导出全文" aria-label="导出全文" aria-expanded={showExportMenu}>
              <Icon name="download" size={16} />
            </button>
            {showExportMenu && (
              <div className="absolute right-0 top-full mt-1 w-44 bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg z-40 overflow-hidden">
                {(['txt', 'md', 'epub'] as const).map(fmt => (
                  <a
                    key={fmt}
                    href={`/api/export/book?format=${fmt}`}
                    download
                    onClick={() => setShowExportMenu(false)}
                    className="block w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
                  >
                    导出 {fmt.toUpperCase()}
                  </a>
                ))}
              </div>
            )}
          </div>
          <div className="relative">
            <button onClick={() => setShowSessionMenu(!showSessionMenu)} className="text-zinc-500 hover:text-zinc-300 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors shrink-0" title="会话管理" aria-label="会话管理" aria-expanded={showSessionMenu}>
              <Icon name="more-horizontal" size={18} />
            </button>
            {showSessionMenu && (
              <div className="absolute right-0 top-full mt-1 w-64 bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg z-40 overflow-hidden">
                <button onClick={handleNewSession} className="w-full px-3 py-2 text-left text-xs text-zinc-200 hover:bg-zinc-700 flex items-center gap-2">
                  <Icon name="plus" size={14} /> 新建会话
                </button>
                <div className="border-t border-zinc-700" />
                {sessions.map(s => (
                  <div key={s.id} className={`flex items-center gap-1 px-2 ${s.id === sessionId ? 'bg-zinc-700/50' : ''}`}>
                    <button onClick={() => switchSession(s.id)} className="flex-1 px-1 py-2 text-left text-xs text-zinc-300 hover:text-zinc-100 truncate">
                      {s.title || '会话'}
                    </button>
                    <button onClick={() => setDeleteSessionId(s.id)} className="p-1 text-zinc-600 hover:text-red-400 rounded" title="删除会话" aria-label="删除会话">
                      <Icon name="trash-2" size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
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

      <div className="flex-1 overflow-hidden flex flex-col">
        <Group orientation="horizontal">
          <Panel defaultSize={isSplit ? 50 : 100} minSize={25}>
            <PanelHost panelKey={primaryTab} bookId={bookId!} sessionId={sessionId} onPanelClose={() => switchTab('chat')} />
          </Panel>
          {isSplit && (
            <>
              <Separator className="w-1 bg-zinc-800 hover:bg-sky-600 transition-colors cursor-col-resize shrink-0" />
              <Panel defaultSize={50} minSize={25}>
                <PanelHost panelKey={secondaryTab} bookId={bookId!} sessionId={sessionId} onPanelClose={() => switchSecondaryTab('chat')} />
              </Panel>
            </>
          )}
        </Group>
      </div>

      <ConfirmModal open={!!deleteSessionId} title="删除会话" message="删除此会话？消息历史将永久删除。" confirmText="删除" danger onConfirm={handleDeleteSession} onCancel={() => setDeleteSessionId(null)} />
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} onModeChanged={(mode: string) => setLlmMode(mode)} bookId={bookId} />}
      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} onSwitchTab={(tab) => { switchTab(tab); setShowCommandPalette(false) }} />
    </div>
  )
}
