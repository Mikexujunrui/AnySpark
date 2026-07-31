// Memory system — domain module.
import { del, get, post, put } from './http'

export const getMemoryStats = (bookId: string): Promise<{ project: Record<string, unknown>; stats: Record<string, number>; tier0_preview: string }> =>
  get(`/api/memory/stats/${bookId}`)
export const getProjectMemory = (bookId: string): Promise<Record<string, unknown>> => get(`/api/memory/project/${bookId}`)
export const updateProjectMemory = (bookId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> =>
  put(`/api/memory/project/${bookId}`, data)
export const addNote = (bookId: string, title: string, content: string): Promise<{ ok: boolean; note: unknown }> =>
  post(`/api/memory/project/${bookId}/note`, { title, content })
export const deleteNote = (bookId: string, noteId: string): Promise<{ ok: boolean }> =>
  del(`/api/memory/project/${bookId}/note/${noteId}`)
export const recordDecision = (bookId: string, title: string, rationale: string): Promise<{ ok: boolean; decision: unknown }> =>
  post(`/api/memory/project/${bookId}/decision`, { title, rationale })
export const deleteDecision = (bookId: string, decisionId: string): Promise<{ ok: boolean }> =>
  del(`/api/memory/project/${bookId}/decision/${decisionId}`)
export const addProgress = (bookId: string, content: string): Promise<{ ok: boolean; note: unknown }> =>
  post(`/api/memory/project/${bookId}/progress`, { content })
export const deleteProgress = (bookId: string, noteId: string): Promise<{ ok: boolean }> =>
  del(`/api/memory/project/${bookId}/progress/${noteId}`)
export const getPreferences = (): Promise<{ total: number; entries: unknown[]; category_counts: Record<string, number> }> =>
  get('/api/memory/preferences')
export const createPreference = (data: Record<string, unknown>): Promise<{ ok: boolean; entry: unknown }> =>
  post('/api/memory/preferences', data)
export const confirmPreference = (entryId: string): Promise<{ ok: boolean; entry: unknown }> =>
  post(`/api/memory/preferences/${entryId}/confirm`, {})
export const deletePreference = (entryId: string): Promise<{ ok: boolean }> => del(`/api/memory/preferences/${entryId}`)
export const toggleMemory = (enabled: boolean): Promise<{ ok: boolean; enabled: boolean; message: string }> =>
  post('/api/memory/toggle', { enabled })
