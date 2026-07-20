// 推演功能3.0 — API 请求层
// 参照 Nova 的 interactive/api.ts

import { parseSSE, type SSEEvent } from '../../sse'
import type {
  SessionInfo,
  SessionDetailResponse,
  StateResponse,
  BranchesResponse,
  BranchCreateResponse,
  BranchSummary,
  HotChoicesResponse,
  CharactersResponse,
  CharacterInfo,
  TurnEvent,
  TimelineEventInfo,
  SSESimEvent,
} from './types'

const API = '/api'

async function assertOk(res: Response): Promise<void> {
  if (res.ok) return
  let message = res.statusText || `请求失败 (${res.status})`
  const data = await res.json().catch(() => null)
  if (data && (data.error || data.detail || data.message)) {
    message = data.error || data.detail || data.message
  }
  throw new Error(message)
}

// ── SSE 推演流 ──

export interface StartSimParams {
  mode: 'character_pov' | 'narrator_pov'
  setting: string
  character_ids: string[]
  pov_character_id: string | null
  condition?: string
  style_name?: string | null
  reference_book_ids?: string[]
  timeline_event_id?: string | null
  user_supplement?: string
}

export async function* startSimulationStream(
  bookId: string,
  params: StartSimParams,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API}/books/${bookId}/simulation/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  await assertOk(res)
  for await (const event of parseSSE(res)) {
    yield event
  }
}

export interface TurnParams {
  simulation_id: string
  choice_id?: string | null
  choice_text?: string | null
}

export async function* sendTurnStream(
  bookId: string,
  params: TurnParams,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API}/books/${bookId}/simulation/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  await assertOk(res)
  for await (const event of parseSSE(res)) {
    yield event
  }
}

// ── 会话管理 ──

export async function getSimSessions(bookId: string): Promise<SessionInfo[]> {
  const data = await fetch(`${API}/books/${bookId}/simulation/sessions`).then(r => {
    assertOk(r); return r.json()
  })
  return (data as { sessions: SessionInfo[] }).sessions || []
}

export async function getSimSession(
  bookId: string,
  simId: string,
): Promise<SessionDetailResponse> {
  const data = await fetch(`${API}/books/${bookId}/simulation/sessions/${simId}`).then(r => {
    assertOk(r); return r.json()
  })
  return data as SessionDetailResponse
}

export async function deleteSimSession(
  bookId: string,
  simId: string,
): Promise<void> {
  const res = await fetch(`${API}/books/${bookId}/simulation/sessions/${simId}`, {
    method: 'DELETE',
    headers: { 'X-Confirm-Delete': 'true' },
  })
  await assertOk(res)
}

export async function updateSimSession(
  bookId: string,
  simId: string,
  kwargs: { status?: string; summary?: string },
): Promise<{ session: SessionInfo }> {
  const query = new URLSearchParams()
  if (kwargs.status) query.set('status', kwargs.status)
  if (kwargs.summary) query.set('summary', kwargs.summary)
  const res = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}?${query.toString()}`,
    { method: 'PUT' },
  )
  await assertOk(res)
  return res.json()
}

// ── 结构化状态 ──

export async function getSimState(
  bookId: string,
  simId: string,
): Promise<Record<string, unknown>> {
  const data = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/state`,
  ).then(r => { assertOk(r); return r.json() })
  return (data as StateResponse).state || {}
}

// ── 分支管理 ──

export async function getSimBranches(
  bookId: string,
  simId: string,
): Promise<BranchSummary[]> {
  const data = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/branches`,
  ).then(r => { assertOk(r); return r.json() })
  return (data as BranchesResponse).branches || []
}

export async function createSimBranch(
  bookId: string,
  simId: string,
  parentEventId: string,
  title: string,
): Promise<BranchCreateResponse> {
  const res = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/branch`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_event_id: parentEventId, title }),
    },
  )
  await assertOk(res)
  return res.json()
}

export async function switchSimBranch(
  bookId: string,
  simId: string,
  branchId: string,
): Promise<void> {
  const res = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/switch-branch`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch_id: branchId }),
    },
  )
  await assertOk(res)
}

// ── 快捷选择 ──

export async function getSimHotChoices(
  bookId: string,
  simId: string,
  parentId?: string,
): Promise<string[]> {
  const query = parentId ? `?parent_id=${parentId}` : ''
  const data = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/hot-choices${query}`,
  ).then(r => { assertOk(r); return r.json() })
  return (data as HotChoicesResponse).choices || []
}

// ── 角色 ──

export async function getSimCharacters(
  bookId: string,
): Promise<CharacterInfo[]> {
  const data = await fetch(
    `${API}/books/${bookId}/simulation/characters`,
  ).then(r => { assertOk(r); return r.json() })
  return (data as CharactersResponse).characters || []
}

export async function getSimSessionCharacters(
  bookId: string,
  simId: string,
): Promise<CharacterInfo[]> {
  const data = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/characters`,
  ).then(r => { assertOk(r); return r.json() })
  return (data as CharactersResponse).characters || []
}

// ── 时间线事件 ──

export async function getTimelineEvents(
  bookId: string,
): Promise<TimelineEventInfo[]> {
  const data = await fetch(
    `${API}/books/${bookId}/graph/timeline`,
  ).then(r => { assertOk(r); return r.json() })
  const events = (data as { events: Record<string, unknown>[] }).events || []
  return events.map((e: any) => ({
    id: e.id,
    label: e.label || '未命名事件',
    description: e.description || '',
    time_label: e.time_label || '',
    chapter_ref: e.chapter_ref || '',
    order: e.order || 0,
    characters: e.characters || [],
  }))
}

// ── 提拔到时间线 ──

export async function promoteToTimeline(
  bookId: string,
  simId: string,
  eventId: string,
  timelineData: Record<string, unknown>,
): Promise<{ timeline_id: string; promoted_from: string }> {
  const res = await fetch(
    `${API}/books/${bookId}/simulation/sessions/${simId}/promote`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: eventId, timeline_data: timelineData }),
    },
  )
  await assertOk(res)
  return res.json()
}
