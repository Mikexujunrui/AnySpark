// 推演功能3.0 — 状态管理
// 使用项目现有的 createStore 模式，无需额外依赖

import { createStore } from '../../../store'
import type {
  SessionInfo,
  TurnEvent,
  SimChoice,
  BranchSummary,
  SSESimEvent,
} from '../types'

// ── 推演运行时状态 ──

export interface SimulationRunState {
  /** 是否正在流式输出 */
  streaming: boolean
  /** 当前累积叙事内容 */
  narrative: string
  /** 当前选项 */
  choices: SimChoice[]
  /** 选择提示 */
  choicePrompt: string
  /** 快捷选项 */
  hotChoices: string[]
  /** 最新的SSE事件 */
  lastEvent: SSESimEvent | null
  /** 状态文本（如"角色思考中…"） */
  statusText: string
}

function emptyRunState(): SimulationRunState {
  return {
    streaming: false,
    narrative: '',
    choices: [],
    choicePrompt: '',
    hotChoices: [],
    lastEvent: null,
    statusText: '',
  }
}

// 稳定的空状态引用，避免 useSyncExternalStore 的 selector 每次返回新对象导致无限循环
const EMPTY_RUN_STATE: SimulationRunState = Object.freeze(emptyRunState())

// ── 推演全局状态 ──

interface SimulationStoreState {
  /** 所有推演会话 */
  sessions: SessionInfo[]
  /** 当前推演ID */
  currentSimId: string | null
  /** 当前分支ID */
  currentBranchId: string
  /** 推演回合列表 */
  turns: TurnEvent[]
  /** 推演历史（查询API用） */
  branches: BranchSummary[]
  /** 加载标志 */
  loading: boolean
  /** 错误信息 */
  error: string | null
  /** 运行时状态（每个会话一个） */
  runs: Record<string, SimulationRunState>
}

const initialState: SimulationStoreState = {
  sessions: [],
  currentSimId: null,
  currentBranchId: '',
  turns: [],
  branches: [],
  loading: false,
  error: null,
  runs: {},
}

export const simStore = createStore<SimulationStoreState>(initialState)

// ── Selector hooks ──

export function useSimSessions(): SessionInfo[] {
  return simStore.useStore(s => s.sessions)
}

export function useCurrentSimId(): string | null {
  return simStore.useStore(s => s.currentSimId)
}

export function useCurrentBranchId(): string {
  return simStore.useStore(s => s.currentBranchId)
}

export function useSimTurns(): TurnEvent[] {
  return simStore.useStore(s => s.turns)
}

export function useSimBranches(): BranchSummary[] {
  return simStore.useStore(s => s.branches)
}

export function useSimLoading(): boolean {
  return simStore.useStore(s => s.loading)
}

export function useSimError(): string | null {
  return simStore.useStore(s => s.error)
}

export function useSimRunState(): SimulationRunState {
  return simStore.useStore(s => {
    const runId = s.currentSimId || '__setup__'
    return s.runs[runId] || EMPTY_RUN_STATE
  })
}

// ── Actions ──

export function setSimSessions(sessions: SessionInfo[], currentId?: string): void {
  simStore.setState({
    sessions,
    currentSimId: currentId || sessions[0]?.id || null,
  })
}

export function setCurrentSimId(id: string | null): void {
  simStore.setState({
    currentSimId: id,
    currentBranchId: '',
    turns: [],
    branches: [],
  })
}

export function setCurrentBranchId(branchId: string): void {
  simStore.setState({ currentBranchId: branchId })
}

export function setSimTurns(turns: TurnEvent[]): void {
  simStore.setState({ turns })
}

export function setSimBranches(branches: BranchSummary[]): void {
  simStore.setState({ branches })
}

export function setSimLoading(loading: boolean): void {
  simStore.setState({ loading })
}

export function setSimError(error: string | null): void {
  simStore.setState({ error })
}

// ── 运行时状态操作 ──

function getRunId(): string {
  const state = simStore.getState()
  return state.currentSimId || '__setup__'
}

export function initSimRun(): void {
  const runId = getRunId()
  simStore.setState(s => ({
    runs: { ...s.runs, [runId]: emptyRunState() },
  }))
}

export function setSimStreaming(streaming: boolean): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, streaming } },
    }
  })
}

export function appendSimNarrative(text: string): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, narrative: run.narrative + text } },
    }
  })
}

export function setSimNarrative(narrative: string): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, narrative } },
    }
  })
}

export function setSimChoices(choices: SimChoice[], choicePrompt: string): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, choices, choicePrompt } },
    }
  })
}

export function setSimHotChoices(choices: string[]): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, hotChoices: choices } },
    }
  })
}

export function setSimStatusText(text: string): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, statusText: text } },
    }
  })
}

export function setSimLastEvent(event: SSESimEvent | null): void {
  const runId = getRunId()
  simStore.setState(s => {
    const run = s.runs[runId] || EMPTY_RUN_STATE
    return {
      runs: { ...s.runs, [runId]: { ...run, lastEvent: event } },
    }
  })
}

export function resetSimRun(): void {
  const runId = getRunId()
  simStore.setState(s => {
    const runs = { ...s.runs }
    delete runs[runId]
    return { runs }
  })
}
