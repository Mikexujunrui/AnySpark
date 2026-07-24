// 推演功能3.0 — TypeScript 类型定义
// 参照 Nova 的 interactive/types.ts

// ── 会话与模式 ──

export type SimMode = 'character_pov' | 'narrator_pov'
export type OpeningMode = 'free' | 'timeline'

export interface SessionInfo {
  id: string
  book_id: string
  mode: SimMode
  setting: string
  pov_character_id: string | null
  involved_character_ids: string[]
  condition: string | null
  style_name: string | null
  reference_book_ids: string[]
  status: string
  turn_count: number
  summary: string | null
  current_branch: string
  branches: Record<string, BranchMeta>
  created_at: string
  updated_at: string
}

export interface BranchMeta {
  id: string
  title: string
  created_at: string
  parent_event_id?: string
  from_branch?: string
  is_main?: boolean
}

// ── 角色信息 ──

export interface CharacterInfo {
  id: string
  name: string
  description: string
  aliases: string[]
}

export interface ConfigPreviewCharacter {
  id: string
  name: string
  personality: string
  phase: string
  relationships_count: number
  skills: string[]
  is_pov: boolean
}

export interface ConfigPreview {
  characters: ConfigPreviewCharacter[]
  graph_insights: {
    forgotten_characters: string[]
    unresolved_foreshadows: number
  }
  timeline_event: TimelineEventInfo | null
  user_supplement: string
  setting: string
}

export interface TimelineEventInfo {
  id: string
  label: string
  description: string
  time_label: string
  chapter_ref: string
  order: number
  characters: string[]
}

// ── 回合事件 ──

export interface TurnEvent {
  v?: number
  type?: string
  id: string
  parent_id?: string | null
  branch_id: string
  ts: string
  user: string
  narrative: string
  thinking?: string
  state_delta?: StateDelta
  state_status?: 'pending' | 'ready' | 'failed'
  hot_choices?: string[]
  display_events?: TurnDisplayEvent[]
  turn_number: number
}

export interface TurnDisplayEvent {
  id?: string
  role: 'thinking' | 'tool_call' | 'tool_result'
  content?: string
  name?: string
  status?: 'running' | 'success' | 'error'
  created_at?: string
}

// ── 选项 ──

export interface SimChoice {
  id: string
  event_id: string
  simulation_id: string
  text: string
  description: string
  choice_type: 'action' | 'condition'
  selected: boolean
  created_at: string
}

// ── 结构化状态 ──

export interface StateDelta {
  ops: StateOp[]
}

export interface StateOp {
  op: 'set' | 'merge' | 'push' | 'pull' | 'inc' | 'unset'
  path: string
  value?: unknown
}

// ── 分支 ──

export interface BranchSummary {
  id: string
  title: string
  created_at: string
  parent_event_id?: string
  from_branch?: string
  is_main?: boolean
  current: boolean
}

// ── 角色响应 ──

export interface CharResponse {
  perception: string
  thoughts: string
  action: string
  dialogue: string
}

// ── API 响应 ──

export interface SessionsListResponse {
  sessions: SessionInfo[]
}

export interface SessionDetailResponse {
  session: SessionInfo
  turns: TurnEvent[]
  state: Record<string, unknown>
  hot_choices: string[]
  choices: SimChoice[]
}

export interface StateResponse {
  state: Record<string, unknown>
}

export interface BranchesResponse {
  branches: BranchSummary[]
}

export interface BranchCreateResponse {
  id: string
  title: string
  parent_event_id: string
  created_at: string
}

export interface HotChoicesResponse {
  choices: string[]
}

export interface CharactersResponse {
  characters: CharacterInfo[]
}

// ── SSE 事件类型 ──

export type SSESimEventType =
  | 'session'
  | 'config_preview'
  | 'narrator_synthesizing'
  | 'narrative_chunk'
  | 'character_thinking'
  | 'character_response'
  | 'analyzing_condition'
  | 'generating_options'
  | 'generating_hot_choices'
  | 'choices_ready'
  | 'hot_choices'
  | 'done'
  | 'error'

export interface SSESimEvent {
  type: SSESimEventType
  [key: string]: unknown
}
