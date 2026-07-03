import { useState, useCallback, useRef, useEffect } from 'react'
import Icon from '../../components/ui/Icon'

// ── Types ──

type SimMode = 'character_pov' | 'narrator_pov'
type OpeningMode = 'free' | 'timeline'

interface CharacterInfo {
  id: string
  name: string
  description: string
  aliases: string[]
}

interface SimChoice {
  id: string
  text: string
  description: string
  choice_type: string
}

interface CharResponse {
  perception: string
  thoughts: string
  action: string
  dialogue: string
}

interface TimelineEventInfo {
  id: string
  label: string
  description: string
  time_label: string
  chapter_ref: string
  order: number
  characters: string[]
}

interface ConfigPreviewChar {
  id: string
  name: string
  personality: string
  phase: string
  relationships_count: number
  skills: string[]
  is_pov: boolean
}

interface ConfigPreview {
  characters: ConfigPreviewChar[]
  graph_insights: {
    forgotten_characters: string[]
    unresolved_foreshadows: number
  }
  timeline_event: TimelineEventInfo | null
  user_supplement: string
  setting: string
}

// ── Main Component ──

export default function SimulationPanel({ bookId }: { bookId: string }) {
  // Setup state
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

  // Session state
  const [simId, setSimId] = useState<string | null>(null)
  const [narrative, setNarrative] = useState('')
  const [choices, setChoices] = useState<SimChoice[]>([])
  const [loading, setLoading] = useState(false)
  const [charThinking, setCharThinking] = useState<string | null>(null)
  const [charResponses, setCharResponses] = useState<{ name: string; data: CharResponse }[]>([])
  const [statusText, setStatusText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [configPreview, setConfigPreview] = useState<ConfigPreview | null>(null)
  const [choicePrompt, setChoicePrompt] = useState('')
  const [simulationHistory, setSimulationHistory] = useState<any[]>([])

  const narrativeEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load characters and history on mount
  useEffect(() => {
    loadCharacters()
    loadHistory()
  }, [bookId])

  // Load timeline events when switching to timeline opening mode
  useEffect(() => {
    if (openingMode === 'timeline' && timelineEvents.length === 0) {
      loadTimelineEvents()
    }
  }, [openingMode, bookId])

  // Auto-scroll narrative
  useEffect(() => {
    narrativeEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [narrative])

  const loadCharacters = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/simulation/characters`)
      if (res.ok) {
        const data = await res.json()
        setCharacters(data.characters || [])
      }
    } catch (e) {
      console.error('Failed to load characters:', e)
    }
  }, [bookId])

  const loadTimelineEvents = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/graph/timeline`)
      if (res.ok) {
        const data = await res.json()
        const events: TimelineEventInfo[] = (data.events || []).map((e: any) => ({
          id: e.id,
          label: e.label || '未命名事件',
          description: e.description || '',
          time_label: e.time_label || '',
          chapter_ref: e.chapter_ref || '',
          order: e.order || 0,
          characters: e.characters || [],
        }))
        setTimelineEvents(events)
      }
    } catch (e) {
      console.error('Failed to load timeline events:', e)
    }
  }, [bookId])

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`/api/books/${bookId}/simulation/sessions`)
      if (res.ok) {
        const data = await res.json()
        setSimulationHistory(data.sessions || [])
      }
    } catch (e) {
      console.error('Failed to load simulation history:', e)
    }
  }, [bookId])

  // Continue a past simulation session
  const continueSession = useCallback(async (pastSimId: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/books/${bookId}/simulation/sessions/${pastSimId}`)
      if (!res.ok) {
        setError('加载推演会话失败')
        setLoading(false)
        return
      }
      const data = await res.json()
      const session = data.session
      const events = data.events || []
      // Restore session state
      setSimId(pastSimId)
      setMode(session.mode)
      setSetting(session.setting || '')
      setCondition(session.condition || '')
      setPovCharId(session.pov_character_id || null)
      setSelectedChars(session.involved_character_ids || [])
      // Reconstruct narrative from events
      const narrativeEvents = events.filter((e: any) => e.event_type === 'narrative')
      const lastEvent = narrativeEvents[narrativeEvents.length - 1]
      if (lastEvent) {
        setNarrative(lastEvent.content || '')
        setChoices(lastEvent.choices || [])
      } else {
        setNarrative('')
        setChoices([])
      }
      // Load all narrative text for display
      const allNarrative = narrativeEvents.map((e: any) => e.content).join('\n\n')
      setNarrative(allNarrative || '')
      setChoices(lastEvent?.choices || [])
    } catch (e: any) {
      setError(`加载推演失败: ${e.message || '网络错误'}`)
    } finally {
      setLoading(false)
    }
  }, [bookId])

  // Delete a simulation session
  const deleteSession = useCallback(async (pastSimId: string) => {
    try {
      const res = await fetch(`/api/books/${bookId}/simulation/sessions/${pastSimId}`, { method: 'DELETE' })
      if (res.ok) {
        setSimulationHistory(prev => prev.filter((s: any) => s.id !== pastSimId))
      }
    } catch (e) {
      console.error('Failed to delete simulation:', e)
    }
  }, [bookId])

  // ── Start simulation ──

  const startSimulation = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNarrative('')
    setChoices([])
    setCharResponses([])
    setStatusText('正在启动推演...')

    const body: any = {
      mode,
      setting: mode === 'character_pov' ? setting : '',
      character_ids: mode === 'narrator_pov' ? selectedChars : [],
      pov_character_id: mode === 'character_pov' ? povCharId : null,
      condition: mode === 'narrator_pov' ? condition : undefined,
      timeline_event_id: openingMode === 'timeline' ? selectedTimelineEvent : undefined,
      user_supplement: userSupplement || undefined,
    }

    try {
      const res = await fetch(`/api/books/${bookId}/simulation/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '启动失败' }))
        setError(err.detail || '启动失败')
        setLoading(false)
        return
      }

      // Read SSE stream from POST response
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        setError('无法读取响应流')
        setLoading(false)
        return
      }

      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        // Handle both \n and \r\n line endings
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line || line.startsWith('event:')) {
            continue
          }
          if (line.startsWith('data:')) {
            const dataStr = line.slice(5).trim()
            if (!dataStr) continue
            try {
              const evt = JSON.parse(dataStr)
              try {
                handleSSEEvent(evt)
              } catch (handlerErr) {
                console.error('SSE event handler error:', handlerErr)
              }
            } catch {
              // Skip non-JSON data lines
            }
          }
        }
      }
    } catch (e: any) {
      setError(`推演启动失败: ${e.message || '网络错误'}`)
    } finally {
      setLoading(false)
      setStatusText('')
    }
  }, [bookId, mode, setting, condition, selectedChars, povCharId, openingMode, selectedTimelineEvent, userSupplement])

  // ── Process turn ──

  const processTurn = useCallback(async (choice?: SimChoice | { text: string; custom?: boolean }) => {
    if (!simId) return
    setLoading(true)
    setError(null)
    setChoices([])
    setCharResponses([])
    setStatusText('推演中...')

    const body: any = { simulation_id: simId }
    if (choice && 'id' in choice && choice.id) {
      body.choice_id = choice.id
    } else if (choice) {
      body.choice_text = choice.text
    }

    try {
      const res = await fetch(`/api/books/${bookId}/simulation/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '推演失败' }))
        setError(err.detail || '推演失败')
        setLoading(false)
        return
      }

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      if (!reader) {
        setError('无法读取响应流')
        setLoading(false)
        return
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        // Handle both \n and \r\n line endings
        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line || line.startsWith('event:')) {
            continue
          }
          if (line.startsWith('data:')) {
            const dataStr = line.slice(5).trim()
            if (!dataStr) continue
            try {
              const evt = JSON.parse(dataStr)
              try {
                handleSSEEvent(evt)
              } catch (handlerErr) {
                console.error('SSE event handler error:', handlerErr)
              }
            } catch {
              // Skip non-JSON data lines
            }
          }
        }
      }
    } catch (e: any) {
      setError(`推演失败: ${e.message || '网络错误'}`)
    } finally {
      setLoading(false)
      setStatusText('')
    }
  }, [bookId, simId])

  // ── SSE event handler ──

  const handleSSEEvent = useCallback((evt: any) => {
    switch (evt.type) {
      case 'session':
        setSimId(evt.simulation_id)
        break
      case 'config_preview':
        setConfigPreview(evt.data || null)
        break
      case 'character_thinking':
        setCharThinking(evt.character || '角色')
        setStatusText(`${evt.character || '角色'} 思考中...`)
        break
      case 'character_response':
        setCharThinking(null)
        if (evt.character && evt.data) {
          setCharResponses(prev => [...prev, { name: evt.character, data: evt.data }])
        }
        break
      case 'analyzing_condition':
        setStatusText('分析条件中...')
        break
      case 'narrator_synthesizing':
        setStatusText('叙事者综合中...')
        break
      case 'narrative_chunk':
        setStatusText('')
        setNarrative(prev => prev + (evt.text || ''))
        break
      case 'generating_options':
        setStatusText('生成选项中...')
        break
      case 'choices_ready':
        setChoices(evt.choices || [])
        setChoicePrompt(evt.choice_prompt || '')
        break
      case 'done':
        setStatusText('')
        break
      case 'error':
        setError(evt.message || '未知错误')
        break
    }
  }, [])

  // ── Render ──

  // Setup screen (no active simulation)
  if (!simId && !loading) {
    return (
      <SetupScreen
        mode={mode}
        setMode={setMode}
        openingMode={openingMode}
        setOpeningMode={setOpeningMode}
        characters={characters}
        selectedChars={selectedChars}
        setSelectedChars={setSelectedChars}
        povCharId={povCharId}
        setPovCharId={setPovCharId}
        setting={setting}
        setSetting={setSetting}
        condition={condition}
        setCondition={setCondition}
        timelineEvents={timelineEvents}
        selectedTimelineEvent={selectedTimelineEvent}
        setSelectedTimelineEvent={setSelectedTimelineEvent}
        userSupplement={userSupplement}
        setUserSupplement={setUserSupplement}
        onStart={startSimulation}
        error={error}
        simulationHistory={simulationHistory}
        onContinue={continueSession}
        onDelete={deleteSession}
      />
    )
  }

  // Simulation screen
  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-zinc-800 bg-zinc-950/50 shrink-0">
        <div className="flex items-center gap-2">
          <Icon name="git-branch" size={16} className="text-purple-400" />
          <span className="text-sm font-semibold text-zinc-300">
            {mode === 'character_pov' ? '角色推演' : '叙事者推演'}
          </span>
        </div>
        {simId && (
          <span className="text-[10px] text-zinc-600 font-mono">{simId.slice(0, 12)}...</span>
        )}
        <div className="flex-1" />
        {statusText && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
            {statusText}
          </div>
        )}
        <button
          onClick={() => {
            setSimId(null)
            setNarrative('')
            setChoices([])
            setCharResponses([])
            setConfigPreview(null)
          }}
          className="text-xs text-zinc-500 hover:text-zinc-300 px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition-colors"
        >
          新推演
        </button>
      </div>

      {/* Narrative Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Config Preview */}
        {configPreview && (
          <div className="border border-zinc-800 rounded-lg p-4 bg-zinc-900/40 max-w-2xl mx-auto space-y-3">
            <div className="flex items-center gap-2 text-xs text-zinc-500 font-semibold">
              <Icon name="compass" size={14} className="text-purple-400" />
              推演配置预览
            </div>
            {/* Timeline event context */}
            {configPreview.timeline_event && (
              <div className="text-[11px] text-zinc-500">
                <span className="text-amber-400">从正文事件启动：</span>
                {configPreview.timeline_event.label}
                {configPreview.timeline_event.time_label && `
              (${configPreview.timeline_event.time_label})`}
              </div>
            )}
            {/* Character cards */}
            <div className="grid grid-cols-2 gap-2">
              {configPreview.characters.map((char) => (
                <div key={char.id} className={`p-2 rounded border ${char.is_pov ? 'border-purple-700/50 bg-purple-900/10' : 'border-zinc-800 bg-zinc-900/30'}`}>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-zinc-300">{char.name}</span>
                    {char.is_pov && <span className="text-[9px] text-purple-400 bg-purple-900/30 px-1 rounded">主视角</span>}
                  </div>
                  <p className="text-[10px] text-zinc-600 truncate">{char.personality || '暂无描述'}</p>
                  <div className="flex items-center gap-2 mt-1 text-[9px] text-zinc-700">
                    <span>{char.phase}</span>
                    <span>·</span>
                    <span>{char.relationships_count}关系</span>
                    {char.skills.length > 0 && <span>· {char.skills.slice(0, 2).join('/')}</span>}
                  </div>
                </div>
              ))}
            </div>
            {/* Graph insights */}
            {(configPreview.graph_insights.forgotten_characters.length > 0 || configPreview.graph_insights.unresolved_foreshadows > 0) && (
              <div className="flex flex-wrap gap-2 text-[10px]">
                {configPreview.graph_insights.forgotten_characters.length > 0 && (
                  <span className="text-yellow-500 bg-yellow-900/20 px-2 py-0.5 rounded">
                    遗忘角色：{configPreview.graph_insights.forgotten_characters.join('、')}
                  </span>
                )}
                {configPreview.graph_insights.unresolved_foreshadows > 0 && (
                  <span className="text-blue-500 bg-blue-900/20 px-2 py-0.5 rounded">
                    未解决伏笔：{configPreview.graph_insights.unresolved_foreshadows}个
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Character Thinking Badge */}
        {charThinking && (
          <div className="flex items-center gap-2 text-xs text-purple-400 py-2">
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
            {charThinking} 思考中...
          </div>
        )}

        {/* Character Responses — inline within narrative flow */}
        {charResponses.map((resp, i) => (
          <div key={i} className="border-l-2 border-purple-800/50 pl-3 ml-2 max-w-2xl mx-auto space-y-0.5">
            <div className="text-[10px] text-purple-400 font-semibold">{resp.name}</div>
            {resp.data.perception && (
              <p className="text-[11px] text-zinc-500">{resp.data.perception}</p>
            )}
            {resp.data.thoughts && (
              <p className="text-[11px] text-zinc-600 italic">{resp.data.thoughts}</p>
            )}
            {resp.data.action && (
              <p className="text-xs text-zinc-300">{resp.data.action}</p>
            )}
            {resp.data.dialogue && (
              <p className="text-xs text-amber-300">「{resp.data.dialogue}」</p>
            )}
          </div>
        ))}

        {/* Narrative Text */}
        {narrative && (
          <div className="space-y-3 max-w-2xl mx-auto">
            {narrative.split('\n\n').map((para, i) =>
              para.trim() ? (
                <p key={i} className="text-zinc-300 text-sm leading-relaxed font-[serif]">
                  {para}
                </p>
              ) : null
            )}
          </div>
        )}

        {loading && !narrative && !charResponses.length && (
          <div className="flex items-center gap-2 justify-center text-zinc-500 text-xs py-8">
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
          </div>
        )}

        {/* Generating Options Indicator */}
        {loading && narrative && !choices.length && statusText === '生成选项中...' && (
          <div className="flex items-center gap-2 justify-center text-zinc-500 text-xs py-4 max-w-2xl mx-auto">
            <span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
            {statusText}
          </div>
        )}

        {error && (
          <div className="text-xs text-red-400 text-center py-4 border border-red-900/30 rounded-lg bg-red-950/20 max-w-2xl mx-auto">
            {error}
          </div>
        )}

        {/* Choices + Custom Input — inline at end of narrative, not fixed bottom */}
        {narrative && !loading && (
          <div className="max-w-2xl mx-auto">
            <ChoicePanel
              choices={choices}
              mode={mode}
              choicePrompt={choicePrompt}
              onChoice={processTurn}
            />
          </div>
        )}

        <div ref={narrativeEndRef} />
      </div>
    </div>
  )
}

// ── Setup Screen Sub-component ──

function SetupScreen({
  mode, setMode, openingMode, setOpeningMode,
  characters, selectedChars, setSelectedChars,
  povCharId, setPovCharId, setting, setSetting, condition, setCondition,
  timelineEvents, selectedTimelineEvent, setSelectedTimelineEvent,
  userSupplement, setUserSupplement,
  onStart, error,
  simulationHistory, onContinue, onDelete,
}: any) {
  const toggleChar = (id: string) => {
    if (mode === 'character_pov') {
      setPovCharId(id === povCharId ? null : id)
    } else {
      setSelectedChars((prev: string[]) =>
        prev.includes(id) ? prev.filter((c: string) => c !== id) : [...prev, id]
      )
    }
  }

  const canStart = mode === 'character_pov'
    ? povCharId && (openingMode === 'free' ? true : selectedTimelineEvent)
    : selectedChars.length > 0 && (openingMode === 'free' ? true : selectedTimelineEvent)

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Title */}
        <div className="text-center">
          <div className="inline-flex items-center gap-2 text-purple-400 mb-2">
            <Icon name="compass" size={24} />
            <span className="text-lg font-semibold">推演</span>
          </div>
          <p className="text-xs text-zinc-600">在关键分岔点试演不同剧情走向</p>
        </div>

        {/* Mode Selector */}
        <div>
          <label className="text-xs text-zinc-500 mb-2 block">推演模式</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setMode('character_pov')}
              className={`text-left p-3 rounded-lg border transition-all ${
                mode === 'character_pov'
                  ? 'border-purple-700 bg-purple-900/20 text-purple-300'
                  : 'border-zinc-800 bg-zinc-900/50 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-sm font-medium mb-1">角色推演</div>
              <div className="text-[10px] text-zinc-600">代入角色视角，选择行动推动剧情</div>
            </button>
            <button
              onClick={() => setMode('narrator_pov')}
              className={`text-left p-3 rounded-lg border transition-all ${
                mode === 'narrator_pov'
                  ? 'border-purple-700 bg-purple-900/20 text-purple-300'
                  : 'border-zinc-800 bg-zinc-900/50 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-sm font-medium mb-1">叙事者推演</div>
              <div className="text-[10px] text-zinc-600">设定客观条件，推演多角色反应</div>
            </button>
          </div>
        </div>

        {/* Opening Mode Selector */}
        <div>
          <label className="text-xs text-zinc-500 mb-2 block">开场方式</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setOpeningMode('free')}
              className={`text-left p-2.5 rounded-lg border transition-all ${
                openingMode === 'free'
                  ? 'border-purple-700 bg-purple-900/20 text-purple-300'
                  : 'border-zinc-800 bg-zinc-900/50 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-xs font-medium">自由开局</div>
              <div className="text-[10px] text-zinc-600">自定义开局场景</div>
            </button>
            <button
              onClick={() => setOpeningMode('timeline')}
              className={`text-left p-2.5 rounded-lg border transition-all ${
                openingMode === 'timeline'
                  ? 'border-purple-700 bg-purple-900/20 text-purple-300'
                  : 'border-zinc-800 bg-zinc-900/50 text-zinc-500 hover:border-zinc-700'
              }`}
            >
              <div className="text-xs font-medium">从正文事件开始</div>
              <div className="text-[10px] text-zinc-600">选择时间线上的事件作为起点</div>
            </button>
          </div>
        </div>

        {/* Character Picker */}
        <div>
          <label className="text-xs text-zinc-500 mb-2 block">
            {mode === 'character_pov' ? '选择主视角角色' : '选择参与角色（可多选）'}
          </label>
          {characters.length === 0 ? (
            <div className="text-xs text-zinc-600 text-center py-4 border border-dashed border-zinc-800 rounded-lg">
              知识库中暂无角色数据
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
              {characters.map((char: CharacterInfo) => {
                const selected = mode === 'character_pov'
                  ? povCharId === char.id
                  : selectedChars.includes(char.id)
                return (
                  <button
                    key={char.id}
                    onClick={() => toggleChar(char.id)}
                    className={`text-left p-2 rounded-lg border transition-all ${
                      selected
                        ? 'border-purple-700 bg-purple-900/20'
                        : 'border-zinc-800 bg-zinc-900/30 hover:border-zinc-700'
                    }`}
                  >
                    <div className="text-xs font-medium text-zinc-300">{char.name}</div>
                    {char.description && (
                      <div className="text-[10px] text-zinc-600 truncate">{char.description}</div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Timeline Event Picker (when timeline opening mode) */}
        {openingMode === 'timeline' && (
          <div>
            <label className="text-xs text-zinc-500 mb-2 block">选择正文事件起点</label>
            {timelineEvents.length === 0 ? (
              <div className="text-xs text-zinc-600 text-center py-4 border border-dashed border-zinc-800 rounded-lg">
                时间线中暂无事件数据
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto space-y-1">
                {timelineEvents.map((event: TimelineEventInfo) => (
                  <button
                    key={event.id}
                    onClick={() => setSelectedTimelineEvent(event.id === selectedTimelineEvent ? null : event.id)}
                    className={`w-full text-left p-2 rounded-lg border transition-all ${
                      selectedTimelineEvent === event.id
                        ? 'border-amber-700 bg-amber-900/20'
                        : 'border-zinc-800 bg-zinc-900/30 hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {event.time_label && (
                        <span className="text-[9px] text-amber-500 shrink-0">{event.time_label}</span>
                      )}
                      <span className="text-xs text-zinc-300 truncate">{event.label}</span>
                    </div>
                    {event.characters && event.characters.length > 0 && (
                      <div className="text-[9px] text-zinc-600 mt-0.5">涉及：{event.characters.slice(0, 3).join('、')}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Setting / Condition (only in free opening mode) */}
        {openingMode === 'free' && (
          <div>
            <label className="text-xs text-zinc-500 mb-2 block">
              {mode === 'character_pov' ? '开局设定' : '客观条件'}
            </label>
            <textarea
              value={mode === 'character_pov' ? setting : condition}
              onChange={(e) => mode === 'character_pov' ? setSetting(e.target.value) : setCondition(e.target.value)}
              placeholder={mode === 'character_pov'
                ? '描述推演的开局场景，如"张三在城门口遇到了多年未见的老友"...'
                : '描述推演的客观条件，如"王国突然覆灭，各方势力如何反应"...'
              }
              rows={3}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 resize-none"
            />
          </div>
        )}

        {/* User Supplement (always available) */}
        <div>
          <label className="text-xs text-zinc-500 mb-2 block">补充说明（可选）</label>
          <textarea
            value={userSupplement}
            onChange={(e) => setUserSupplement(e.target.value)}
            placeholder={openingMode === 'timeline'
              ? '对选定事件的补充说明，如“此时角色内心已有动摇”...'
              : '对开局设定的补充，如“天气恶劣，气氛紧张”...'
            }
            rows={2}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 resize-none"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="text-xs text-red-400 text-center py-2 border border-red-900/30 rounded-lg bg-red-950/20">
            {error}
          </div>
        )}

        {/* Start Button */}
        <button
          onClick={onStart}
          disabled={!canStart}
          className="w-full text-sm bg-purple-900/40 text-purple-300 border border-purple-800/50 rounded-lg px-4 py-2.5 hover:bg-purple-800/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          开始推演
        </button>

        {/* Simulation History */}
        {simulationHistory && simulationHistory.length > 0 && (
          <div>
            <label className="text-xs text-zinc-500 mb-2 block">推演历史</label>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {simulationHistory.map((sim: any) => (
                <div
                  key={sim.id}
                  className="w-full text-left p-2 rounded-lg border border-zinc-800 bg-zinc-900/30 hover:border-zinc-700 transition-all flex items-center gap-2"
                >
                  <button
                    onClick={() => onContinue(sim.id)}
                    className="flex-1 flex items-center gap-2 min-w-0 text-left"
                  >
                    <Icon name="compass" size={12} className="text-purple-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-zinc-500 shrink-0">
                          {sim.mode === 'character_pov' ? '角色' : '叙事者'}
                        </span>
                        <span className="text-xs text-zinc-400 truncate">
                          {sim.setting || sim.condition || '未命名推演'}
                        </span>
                      </div>
                      <div className="text-[9px] text-zinc-600">
                        {sim.turn_count || 0}回合 · {sim.status}
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => onDelete(sim.id)}
                    className="text-zinc-600 hover:text-red-400 transition-colors shrink-0 p-1"
                    title="删除"
                  >
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Choice Panel Sub-component ──

function ChoicePanel({
  choices, mode, choicePrompt, onChoice,
}: {
  choices: SimChoice[]
  mode: SimMode
  choicePrompt: string
  onChoice: (choice: SimChoice | { text: string; custom?: boolean }) => void
}) {
  return (
    <div className="border-t border-zinc-800/50 pt-4 mt-4">
      {/* Choice Prompt — describes the current situation */}
      <div className="text-xs text-zinc-400 mb-3 font-medium">
        {choicePrompt || (mode === 'character_pov' ? '你选择：' : '剧情将如何发展？')}
      </div>
      {/* Choice Options */}
      {choices.length > 0 && (
        <div className="grid grid-cols-1 gap-2 mb-2">
          {choices.map((choice, i) => (
            <button
              key={i}
              onClick={() => onChoice(choice)}
              className="w-full text-left px-4 py-3 rounded-lg border border-zinc-700 bg-zinc-800/50 hover:bg-zinc-700 hover:border-zinc-600 transition-all group"
            >
              <div className="flex items-start gap-3">
                <span className="text-[10px] text-purple-500 bg-purple-900/30 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 group-hover:text-zinc-100 font-medium">
                    {choice.text}
                  </p>
                  {choice.description && (
                    <p className="text-[10px] text-zinc-500 mt-0.5">{choice.description}</p>
                  )}
                </div>
                <Icon name="chevron-right" size={14} className="text-zinc-600 group-hover:text-zinc-400 mt-1 shrink-0" />
              </div>
            </button>
          ))}
        </div>
      )}
      {/* Custom Input — always available */}
      <div>
        <input
          type="text"
          placeholder={mode === 'character_pov' ? '或输入自定义行动...' : '或设定新的客观条件...'}
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
          onKeyDown={(e) => {
            const target = e.target as HTMLInputElement
            if (e.key === 'Enter' && target.value.trim()) {
              onChoice({ text: target.value, custom: true })
              target.value = ''
            }
          }}
        />
      </div>
    </div>
  )
}
