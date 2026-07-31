// Knowledge / Extract / Styles / Skills / Stats / Workflows / character mentions — domain module.
import { del, get, post, put } from './http'
import type { SkillsListData, StylesListData } from './types'

// ── Workflows (global pool) ──

export const getGlobalWorkflows = (): Promise<unknown[]> => get('/api/workflows')
export const deleteGlobalWorkflow = (wfId: string): Promise<unknown> => del(`/api/workflows/${wfId}`)

// ── Stats ──

export const getWritingStats = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/stats`)

// ── Character mentions (heatmap) ──

export const getCharacterMentions = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/character-mentions`)
export const refreshCharacterMentions = (bookId: string): Promise<unknown> =>
  post(`/api/books/${bookId}/character-mentions/refresh`, {})

// ── Knowledge ──

export const getSummary = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/knowledge/summary`)
export const deleteEntity = (bookId: string, entityId: string): Promise<unknown> =>
  del(`/api/books/${bookId}/knowledge/entity/${entityId}`)
export const updateEntity = (bookId: string, entityId: string, payload: unknown): Promise<unknown> =>
  put(`/api/books/${bookId}/knowledge/entity/${entityId}`, payload)

// ── Extract ──

export const extract = (text: string, bookId: string): Promise<unknown> => post('/api/extract', { text, book_id: bookId })

// ── Styles ──

export const getStyles = (): Promise<StylesListData> => get('/api/styles')
export const getStyle = (name: string): Promise<unknown> => get(`/api/styles/${name}`)
export const createStyle = (data: unknown): Promise<unknown> => post('/api/styles/custom', data)
export const updateStyle = (name: string, data: unknown): Promise<unknown> => put(`/api/styles/custom/${name}`, data)
export const deleteStyle = (name: string): Promise<unknown> => del(`/api/styles/custom/${name}`)
export const getActiveStyle = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/style`)
export const setActiveStyle = (bookId: string, name: string): Promise<unknown> => put(`/api/books/${bookId}/style`, { name })

// ── Skills ──

export const getSkills = (): Promise<SkillsListData> => get('/api/skills')
