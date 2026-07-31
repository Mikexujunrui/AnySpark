// Chapters / Volumes / Notes / Export / Outline / History / analyses / worldbuilding — domain module.
import { del, diagLog, get, post, put } from './http'

const API = ''

// ── Chapters ──

export const getChapters = (bookId: string): Promise<unknown[]> => get(`/api/books/${bookId}/chapters`)
export const createChapter = (bookId: string, data: unknown): Promise<unknown> =>
  post(`/api/books/${bookId}/chapters`, data)
export const updateChapter = (bookId: string, chapterId: string, data: unknown): Promise<unknown> =>
  put(`/api/books/${bookId}/chapters/${chapterId}`, data)
export const deleteChapter = (bookId: string, chapterId: string): Promise<unknown> =>
  del(`/api/books/${bookId}/chapters/${chapterId}`)

// ── Volumes ──

export const getVolumes = (bookId: string): Promise<{ volumes: unknown[] }> => get(`/api/books/${bookId}/volumes`)

// ── Chapter reorder ──

export const reorderChapters = (bookId: string, order: string[]): Promise<{ ok: boolean; count: number }> =>
  post(`/api/books/${bookId}/chapters/reorder`, { order })

// ── Notes ──

export const getNotes = (bookId: string): Promise<unknown[]> => get(`/api/books/${bookId}/notes`)
export const addBookNote = (bookId: string, content: string, tags?: string[]): Promise<unknown> =>
  post(`/api/books/${bookId}/notes`, { content, tags })
export const deleteBookNote = (bookId: string, noteId: string): Promise<unknown> =>
  del(`/api/books/${bookId}/notes/${noteId}`)

// ── Export ──

export const exportBook = (bookId: string, format?: string): Promise<Response> => {
  const url = `/api/books/${bookId}/export?format=${format || 'txt'}`
  diagLog.info(`GET ${url} — 导出请求`)
  return fetch(API + url)
}

// ── Chapter status ──

export const promoteChapter = (bookId: string, chapterId: string): Promise<{ status: string }> =>
  post(`/api/books/${bookId}/chapters/${chapterId}/promote`, {})
export const demoteChapter = (bookId: string, chapterId: string): Promise<{ status: string }> =>
  post(`/api/books/${bookId}/chapters/${chapterId}/demote`, {})

// ── Outline ──

export const getOutline = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/outline`)
export const getDetailedOutline = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/detailed-outline`)

// ── Chapter history / versions ──

export const getChapterHistory = (bookId: string, chapterId: string): Promise<unknown[]> =>
  get(`/api/books/${bookId}/chapters/${chapterId}/history`)
export const getChapterVersion = (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
  get(`/api/books/${bookId}/chapters/${chapterId}/versions/${versionId}`)
export const revertChapter = (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
  post(`/api/books/${bookId}/chapters/${chapterId}/revert`, { version_id: versionId })
export const deleteChapterVersion = (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
  del(`/api/books/${bookId}/chapters/${chapterId}/versions/${versionId}`)

// ── Deep style analysis ──

export const triggerDeepStyle = (bookId: string, analysisType: string, refBookId?: string): Promise<Record<string, unknown>> =>
  post(`/api/books/${bookId}/analyses/deep-style?analysis_type=${analysisType}${refBookId ? `&ref_book_id=${refBookId}` : ''}`)
export const getDeepStyle = (bookId: string, analysisType: string, refBookId?: string): Promise<Record<string, unknown>> =>
  get(`/api/books/${bookId}/analyses/deep-style?analysis_type=${analysisType}${refBookId ? `&ref_book_id=${refBookId}` : ''}`)

// ── Emotional curve ──

export const triggerEmotionalCurve = (bookId: string, refBookId?: string): Promise<Record<string, unknown>> =>
  post(`/api/books/${bookId}/analyses/emotional-curve${refBookId ? `?ref_book_id=${refBookId}` : ''}`)
export const getEmotionalCurve = (bookId: string, refBookId?: string): Promise<Record<string, unknown>> =>
  get(`/api/books/${bookId}/analyses/emotional-curve${refBookId ? `?ref_book_id=${refBookId}` : ''}`)

// ── Worldbuilding entry edit ──

export const updateWorldbuildingEntry = (bookId: string, entryId: string, data: Record<string, unknown>): Promise<unknown> =>
  put(`/api/books/${bookId}/worldbuilding/entries/${entryId}`, data)
