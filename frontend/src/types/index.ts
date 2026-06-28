/** Core type definitions for the Novel Writing Agent frontend. */

export interface Book {
  id: string
  title: string
  description: string
  entityCount: number
  chapterCount: number
  createdAt: string
  updatedAt: string
}

export interface Chapter {
  id: string
  bookId?: string
  title: string
  content: string
  is_extra?: boolean
  status?: string  // "draft" | "final"
  version_count?: number
  version_label?: string
  createdAt: string
  updatedAt?: string
}

export interface ChapterVersion {
  id: string
  message: string
  version_label: string
  is_current: boolean
  has_diff: boolean
  timestamp: string
  word_count: number
}

export interface Session {
  id: string
  title: string
  bookId?: string
  createdAt: string
  updatedAt: string
  messageCount: number
}

export interface ChatMessage {
  role: 'user' | 'agent' | 'system' | 'tool'
  text?: string
  content?: string
  tool_calls?: ToolCall[]
  tool_call_id?: string
  parts?: MessagePart[]
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface MessagePart {
  type: 'text' | 'tool_call' | 'tool_result'
  text?: string
  tool_call?: ToolCall
  result?: string
}

export interface Entity {
  id: string
  type: EntityType
  name: string
  aliases: string[]
  data: Record<string, unknown>
  project_id?: string
  created_at?: string
  updated_at?: string
}

export type EntityType = 'character' | 'location' | 'item' | 'organization' | 'concept' | 'event'

export interface Relation {
  id: string
  from: string
  to: string
  type: RelationType
}

export type RelationType =
  | 'KNOWS' | 'BELONGS_TO' | 'LOCATED_AT' | 'OWNS'
  | 'ANTAGONIST' | 'ALLY' | 'FAMILY' | 'ROMANTIC'
  | 'MASTER_OF' | 'CAUSES' | 'BEFORE' | 'AFTER'
  | 'FORESHADOWS' | 'RESOLVES' | 'PARTICIPATES_IN'

export interface Foreshadow {
  id: string
  text: string
  hint: string
  resolved: boolean
  resolution?: string
  created_at?: string
}

export interface CharacterSnapshot {
  id: string
  character_id: string
  phase: string
  is_current: boolean
  time_order: number
  description: string
  data: Record<string, unknown>
}

export interface TimelineEvent {
  id: string
  time_point: string
  time_order: number
  description: string
  chapter_ref?: string
}

export interface Volume {
  id: string
  title: string
  storyLine: string
  order: number
  chapters: VolumeChapter[]
  createdAt: string
  updatedAt: string
}

export interface VolumeChapter {
  id: string
  title: string
}

// ── Interactive Story Types ──

export interface StoryBranch {
  id: string
  project_id: string
  name: string
  description: string
  parent_branch_id?: string
  source_choice_id?: string
  status: 'active' | 'frozen' | 'completed'
  created_at: string
  updated_at: string
  parent_id?: string
  children?: string[]
  event_count?: number
}

export interface BranchEvent {
  id: string
  branch_id: string
  content: string
  event_type: 'narrative' | 'choice_point' | 'outcome'
  turn_number: number
  created_at: string
  choices?: Choice[]
}

export interface Choice {
  id: string
  event_id: string
  text: string
  description: string
  created_at: string
  custom?: boolean
}

// ── UI / App Types ──

export interface TabConfig {
  key: string
  label: string
  icon: string
}

export interface TabGroup {
  label: string
  tabs: TabConfig[]
}

export interface LLMMode {
  key: string
  label: string
  badge: string
}

export interface Toast {
  id: number
  msg: string
  type: 'info' | 'success' | 'error' | 'warning'
}

export interface Notification {
  id: number
  msg: string
  type: string
}

// ── SSE Event Types ──

export interface SSEEvent {
  type: string
  data: string
  parsed: Record<string, unknown> | null
}

export interface ProgressData {
  stage: string
  detail?: string
}

export interface QuestionOption {
  label: string
  description?: string
}

export interface Question {
  question: string
  header: string
  options: QuestionOption[]
  multiple?: boolean
  custom?: boolean
}

// ── Search Types ──

export interface SearchResult {
  id: string
  title?: string
  chapter_title?: string
  chapter_id?: string
  name?: string
  entity_name?: string
  entity_id?: string
  type?: string
  entity_type?: string
  snippet?: string
}

// ── Agent Config Types ──

export interface AgentConfig {
  model: string
  temperature: number
  task: string
  description: string
}

export type AgentType = 'write' | 'extract' | 'reviewer' | 'interactive' | 'plan' | 'edit' | 'research' | 'consistency'
