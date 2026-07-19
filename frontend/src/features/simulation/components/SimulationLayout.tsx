import { useState, useEffect, useCallback, useRef } from 'react'
import { Panel, Group, Separator } from 'react-resizable-panels'
import Icon from '../../../components/ui/Icon'
import SimulationSetup from './SimulationSetup'
import StoryStage from './StoryStage'
import SnapshotPanel from './SnapshotPanel'
import BranchTimeline from './BranchTimeline'
import { createNarrativeFilter } from '../stream-parser'
import {
  startSimulationStream,
  sendTurnStream,
  getSimSessions,
  getSimSession,
  deleteSimSession as apiDeleteSession,
  getSimState,
  getSimBranches,
  createSimBranch,
  switchSimBranch,
  getSimCharacters,
  getTimelineEvents,
} from '../api'
import {
  simStore,
  setSimSessions,
  setCurrentSimId,
  setSimTurns,
  setSimBranches,
  setSimLoading,
  setSimError,
  initSimRun,
  setSimStreaming,
  appendSimNarrative,
  setSimNarrative,
  setSimChoices,
  setSimHotChoices,
  setSimStatusText,
  setSimLastEvent,
  resetSimRun,
  useSimSessions,
  useCurrentSimId,
  useSimTurns,
  useSimBranches,
  useSimLoading,
  useSimError,
  useSimRunState,
} from '../stores/simulation-store'
import type {
  SimMode, OpeningMode, CharacterInfo, TimelineEventInfo,
  SessionInfo, SimChoice,
} from '../types'

interface SimulationLayoutProps {
  bookId: string
}

type ViewMode = 'setup' | 'play' | 'branches'

export default function SimulationLayout({ bookId }: SimulationLayoutProps) {
  // ── Setup state ──
  const [mode, setMode] = useState<SimMode>('character_pov')
  const [openingMode, setOpeningMode] = useState<OpeningMode>('free')
  const [characters, setCharacters] = useState<CharacterInfo[]>([])
  const [selectedChars, setSelectedChars] = useState<string[]>([])
  const [povCharId, setPovCharId] = useState<string | null>(null)
  const [setting, setSetting] = useState('')
  const [condition, setCondition] = useState('')
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventInfo[]>([])
  const [selectedTimelineEvent, setSelectedTimelineEvent] = useState<string | null>(null)
  const [userSupplement, setUserSupplement] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('setup')
  const [showSnapshot, setShowSnapshot] = useState(true)
  const [excludeChoices, setExcludeChoices] = useState<string[]>([])

  const abortRef = useRef<AbortController | null>(null)

  // Store state
  const sessions = useSimSessions()
  const currentSimId = useCurrentSimId()
  const simTurns = useSimTurns()
  const branches = useSimBranches()
  const loading = useSimLoading()
  const error = useSimError()
  const { streaming, narrative, narrative: runNarrative } = useSimRunState()

  // Load characters and sessions on mount
  useEffect(() => {
    loadInitialData()
  }, [bookId])

  async function loadInitialData() {
    try {
      const [chars, simSessions, tlEvents] = await Promise.all([
        getSimCharacters(bookId),
        getSimSessions(bookId),
        getTimelineEvents(bookId),
      ])
      setCharacters(chars)
      setSimSessions(simSessions)
      setTimelineEvents(tlEvents)
    } catch (e) {
      setSimError('加载初始数据失败: ' + (e as Error).message)
    }
  }

  // ── Start Simulation ──

  const startSimulation = useCallback(async () => {
    setSimLoading(true)
    setSimError(null)
    initSimRun()
    setViewMode('play')

    try {
      const params = {
        mode,
        setting: openingMode === 'free' ? setting : '',
        character_ids: selectedChars,
        pov_character_id: mode === 'character_pov' ? povCharId : null,
        condition: mode === 'narrator_pov' ? condition || setting : undefined,
        timeline_event_id: openingMode === 'timeline' ? selectedTimelineEvent : null,
        user_supplement: userSupplement,
      }

      const narrativeFilter = createNarrativeFilter()
      let simId = ''
      let fullNarrative = ''

      for await (const event of startSimulationStream(bookId, params)) {
        const data = event.parsed as Record<string, unknown> || {}

        if (event.type === 'session') {
          simId = (data as any).simulation_id || ''
          setCurrentSimId(simId)
          setSimStatusText('配置完成')
        } else if (event.type === 'config_preview') {
          setSimStatusText('推演配置完成')
        } else if (event.type === 'narrator_synthesizing') {
          setSimStatusText('叙事合成中...')
        } else if (event.type === 'narrative_chunk') {
          const chunk = (data as any).text || ''
          const cleaned = narrativeFilter.push(chunk)
          if (cleaned) {
            fullNarrative += cleaned
            appendSimNarrative(cleaned)
          }
        } else if (event.type === 'generating_options') {
          setSimStatusText('生成选项中...')
        } else if (event.type === 'generating_hot_choices') {
          setSimStatusText('生成快捷选择...')
        } else if (event.type === 'choices_ready') {
          const choices: SimChoice[] = (data as any).choices || []
          const choicePrompt = (data as any).choice_prompt || ''
          setSimChoices(choices, choicePrompt)
          setSimStatusText('')
          // Store choice texts for exclusion
          setExcludeChoices(choices.map(c => c.text))
        } else if (event.type === 'hot_choices') {
          const hc: string[] = (data as any).choices || []
          setSimHotChoices(hc)
        } else if (event.type === 'done') {
          setSimStreaming(false)
          setSimStatusText('')
          // Reload session to get updated data
          if (simId) {
            loadSessionDetail(simId)
          }
        } else if (event.type === 'error') {
          setSimError((data as any).message || '推演启动失败')
          setSimStreaming(false)
          setViewMode('setup')
        }
        setSimLastEvent({ type: event.type, ...data } as any)
      }

      // Flush any remaining narrative
      const remainder = narrativeFilter.flush()
      if (remainder) {
        fullNarrative += remainder
        setSimNarrative(fullNarrative)
      }

    } catch (e) {
      setSimError('推演失败: ' + (e as Error).message)
    } finally {
      setSimLoading(false)
      setSimStreaming(false)
    }
  }, [bookId, mode, openingMode, setting, selectedChars, povCharId, condition, selectedTimelineEvent, userSupplement])

  // ── Continue Session ──

  const continueSession = useCallback(async (simId: string) => {
    setSimLoading(true)
    setSimError(null)
    setCurrentSimId(simId)
    initSimRun()
    setViewMode('play')

    try {
      await loadSessionDetail(simId)
      // Load the last turn's narrative
      const stateSnapshot = simStore.getState()
      if (stateSnapshot.narrative) {
        setSimNarrative(stateSnapshot.narrative)
      }
      // Load branches
      const brs = await getSimBranches(bookId, simId)
      setSimBranches(brs)
    } catch (e) {
      setSimError('加载推演失败: ' + (e as Error).message)
    } finally {
      setSimLoading(false)
    }
  }, [bookId])

  // ── Send Turn ──

  const sendTurn = useCallback(async (choiceText: string, choiceId?: string) => {
    const state = simStore.getState()
    const simId = state.currentSimId
    if (!simId) return

    setSimStreaming(true)
    setSimError(null)
    setSimChoices([], '')

    // Clear choices for new turn
    const narrativeFilter = createNarrativeFilter()
    let fullNarrative = narrative

    try {
      for await (const event of sendTurnStream(bookId, {
        simulation_id: simId,
        choice_id: choiceId || null,
        choice_text: choiceText,
      })) {
        const data = event.parsed as Record<string, unknown> || {}

        if (event.type === 'character_thinking') {
          setSimStatusText(`${(data as any).character || '角色'} 思考中...`)
        } else if (event.type === 'character_response') {
          setSimStatusText('角色响应完成')
        } else if (event.type === 'narrator_synthesizing') {
          setSimStatusText('叙事合成中...')
        } else if (event.type === 'narrative_chunk') {
          const chunk = (data as any).text || ''
          const cleaned = narrativeFilter.push(chunk)
          if (cleaned) {
            fullNarrative += cleaned
            appendSimNarrative(cleaned)
          }
        } else if (event.type === 'generating_options') {
          setSimStatusText('生成选项中...')
        } else if (event.type === 'generating_hot_choices') {
          setSimStatusText('生成快捷选择...')
        } else if (event.type === 'choices_ready') {
          const choices: SimChoice[] = (data as any).choices || []
          const choicePrompt = (data as any).choice_prompt || ''
          setSimChoices(choices, choicePrompt)
          setExcludeChoices(choices.map(c => c.text))
          setSimStatusText('')
        } else if (event.type === 'hot_choices') {
          const hc: string[] = (data as any).choices || []
          setSimHotChoices(hc)
        } else if (event.type === 'done') {
          setSimStreaming(false)
          setSimStatusText('')
          loadSessionDetail(simId)
        } else if (event.type === 'error') {
          setSimError((data as any).message || '回合处理失败')
          setSimStreaming(false)
        }
        setSimLastEvent({ type: event.type, ...data } as any)
      }

      const remainder = narrativeFilter.flush()
      if (remainder) {
        fullNarrative += remainder
        setSimNarrative(fullNarrative)
      }
    } catch (e) {
      setSimError('回合失败: ' + (e as Error).message)
    } finally {
      setSimStreaming(false)
    }
  }, [bookId, narrative])

  // ── Load session detail ──

  async function loadSessionDetail(simId: string) {
    try {
      const detail = await getSimSession(bookId, simId)
      if (detail.turns) {
        setSimTurns(detail.turns)
      }
      // Build narrative from turns if not streaming
      if (!simStore.getState().streaming) {
        const fullNar = detail.turns
          ?.map(t => t.narrative || '')
          .filter(Boolean)
          .join('\n\n') || ''
        if (fullNar) {
          setSimNarrative(fullNar)
        }
      }
      // Restore choices from stored session
      if (detail.choices && detail.choices.length > 0) {
        const choicePrompt = detail.turns?.length
          ? `第${detail.turns.length}回合，你选择：`
          : ''
        setSimChoices(detail.choices as any, choicePrompt)
      }
    } catch (e) {
      // Non-critical
    }
  }

  // ── State polling ──

  const pollState = useCallback(async () => {
    const state = simStore.getState()
    const simId = state.currentSimId
    if (!simId) return

    // Check if state is pending (state_status === 'pending')
    const latestTurn = state.turns[state.turns.length - 1]
    if (latestTurn?.state_status === 'pending') {
      try {
        await getSimState(bookId, simId)
        loadSessionDetail(simId)
      } catch {
        // Ignore poll errors
      }
    }
  }, [bookId])

  useEffect(() => {
    if (!currentSimId) return
    const interval = setInterval(pollState, 3000)
    return () => clearInterval(interval)
  }, [currentSimId, pollState])

  // ── Delete session ──

  const handleDeleteSession = useCallback(async (simId: string) => {
    try {
      await apiDeleteSession(bookId, simId)
      const updated = await getSimSessions(bookId)
      setSimSessions(updated)
    } catch (e) {
      setSimError('删除失败: ' + (e as Error).message)
    }
  }, [bookId])

  // ── Regenerate last turn ──

  const handleRegenerate = useCallback(() => {
    const state = simStore.getState()
    const simId = state.currentSimId
    if (!simId) return
    const turns = state.turns
    const lastTurn = turns[turns.length - 1]
    const lastAction = lastTurn?.user || ''
    sendTurn(lastAction || '重新生成')
  }, [sendTurn])

  // ── Branch operations ──

  const handleCreateBranchFromCurrent = useCallback(async () => {
    const simId = simStore.getState().currentSimId
    if (!simId) return
    const turns = simStore.getState().turns
    const lastTurn = turns[turns.length - 1]
    const parentId = lastTurn?.id || ''
    const turnNum = lastTurn?.turn_number ?? turns.length
    try {
      await createSimBranch(bookId, simId, parentId, `分支-第${turnNum}回合`)
      const brs = await getSimBranches(bookId, simId)
      setSimBranches(brs)
      setViewMode('branches')
    } catch (e) {
      setSimError('创建分支失败: ' + (e as Error).message)
    }
  }, [bookId])

  // General-purpose branch creation (for BranchTimeline with custom title)
  const handleCreateBranch = useCallback(async (title: string) => {
    const simId = simStore.getState().currentSimId
    if (!simId) return
    const turns = simStore.getState().turns
    const lastTurn = turns[turns.length - 1]
    const parentId = lastTurn?.id || ''
    try {
      await createSimBranch(bookId, simId, parentId, title)
      const brs = await getSimBranches(bookId, simId)
      setSimBranches(brs)
    } catch (e) {
      setSimError('创建分支失败: ' + (e as Error).message)
    }
  }, [bookId])

  const handleSwitchBranch = useCallback(async (branchId: string) => {
    const simId = simStore.getState().currentSimId
    if (!simId) return
    try {
      await switchSimBranch(bookId, simId, branchId)
      await loadSessionDetail(simId)
      const brs = await getSimBranches(bookId, simId)
      setSimBranches(brs)
    } catch (e) {
      setSimError('切换分支失败: ' + (e as Error).message)
    }
  }, [bookId])

  // ── Handle choice / custom action ──

  const handleChoice = useCallback((choice: SimChoice | { text: string; description?: string }) => {
    const text = (choice as SimChoice).text || (choice as any).text || ''
    const id = (choice as SimChoice).id
    sendTurn(text, id)
  }, [sendTurn])

  const handleCustomAction = useCallback((action: string) => {
    sendTurn(action)
  }, [sendTurn])

  // ── New simulation ──

  const handleNewSim = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
    }
    resetSimRun()
    setViewMode('setup')
    setSimChoices([], '')
    setSimNarrative('')
    setSimHotChoices([])
    setSimError(null)
    setExcludeChoices([])
  }, [])

  // ── Render ──

  if (viewMode === 'branches') {
    return (
      <BranchTimeline
        branches={branches}
        currentBranchId={simStore.getState().currentBranchId}
        onSwitchBranch={handleSwitchBranch}
        onCreateBranch={handleCreateBranch}
        onDeleteBranch={async (bid) => {
          /* noop for now */
        }}
        onBackToSim={() => setViewMode('play')}
      />
    )
  }

  if (viewMode === 'setup') {
    return (
      <SimulationSetup
        bookId={bookId}
        mode={mode}
        openingMode={openingMode}
        selectedChars={selectedChars}
        povCharId={povCharId}
        setting={setting}
        condition={condition}
        selectedTimelineEvent={selectedTimelineEvent}
        userSupplement={userSupplement}
        timelineEvents={timelineEvents}
        characters={characters}
        sessions={sessions}
        loading={loading}
        error={error}
        onModeChange={setMode}
        onOpeningModeChange={setOpeningMode}
        onSelectedCharsChange={setSelectedChars}
        onPovCharIdChange={setPovCharId}
        onSettingChange={setSetting}
        onConditionChange={setCondition}
        onTimelineEventChange={setSelectedTimelineEvent}
        onUserSupplementChange={setUserSupplement}
        onStart={startSimulation}
        onContinue={continueSession}
        onDeleteSession={handleDeleteSession}
      />
    )
  }

  // Play mode with resizable panels
  return (
    <div className="h-full flex flex-col">
      {/* Status bar */}
      {streaming && (
        <div className="flex items-center gap-2 px-6 py-1.5 bg-purple-950/30 border-b border-purple-900/30">
          <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-pulse" />
          <span className="text-[10px] text-purple-400/80">
            {simStore.getState().statusText || '处理中...'}
          </span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 px-6 py-1.5 bg-red-950/30 border-b border-red-900/30">
          <Icon name="alert-circle" size={12} className="text-red-400" />
          <span className="text-[10px] text-red-400/80">{error}</span>
          <button onClick={() => setSimError(null)} className="ml-auto text-red-400/60 hover:text-red-400">
            <Icon name="x" size={12} />
          </button>
        </div>
      )}

      <Group orientation="horizontal" className="flex-1 min-h-0">
        <Panel defaultSize={showSnapshot ? 65 : 100} minSize={40} className="min-w-0">
          <StoryStage
            loading={loading}
            onNewSim={handleNewSim}
            onCreateBranch={handleCreateBranchFromCurrent}
            onChoice={handleChoice}
            onCustomAction={handleCustomAction}
            onRegenerate={handleRegenerate}
          />
        </Panel>
        {showSnapshot && (
          <>
            <Separator className="w-px bg-zinc-800 hover:bg-zinc-700 transition-colors cursor-col-resize shrink-0" />
            <Panel defaultSize={35} minSize={20} maxSize={50} className="min-w-0">
              <SnapshotPanel
                state={simStore.getState().lastEvent as any || null}
                loading={false}
              />
            </Panel>
          </>
        )}
      </Group>

      {/* Toggle snapshot button */}
      <button
        onClick={() => setShowSnapshot(!showSnapshot)}
        className="absolute bottom-4 right-4 text-[10px] text-zinc-600 hover:text-zinc-400 bg-zinc-900/80 border border-zinc-800 rounded-lg px-2.5 py-1.5 transition-colors"
        title={showSnapshot ? '隐藏状态面板' : '显示状态面板'}
      >
        <Icon name={showSnapshot ? 'panel-right-close' : 'panel-right-open'} size={12} />
      </button>
    </div>
  )
}
