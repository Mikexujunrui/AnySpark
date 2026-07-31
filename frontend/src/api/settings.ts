// Settings / Providers / Update check — domain module.
import { del, get, post, put } from './http'
import type { SettingsData, UpdateCheckResult, UpdateStatus } from './types'

// ── Settings ──

export const getSettings = (): Promise<SettingsData> => get('/api/settings')
export const updateProvider = (provider: unknown): Promise<SettingsData> => post('/api/settings/providers', provider)
export const deleteProvider = (id: string): Promise<SettingsData> => del(`/api/settings/providers/${id}`)
export const updateSlots = (slots: unknown): Promise<SettingsData> => post('/api/settings/slots', slots)
export const switchMode = (mode: string, customMap?: Record<string, string>): Promise<SettingsData> =>
  post('/api/settings/mode', { mode, custom_map: customMap })
export const testProvider = (providerId: string): Promise<unknown> => post('/api/settings/test', { provider_id: providerId })

// ── Book-level settings (config layering) ──

export const getBookSettings = (bookId: string): Promise<Record<string, unknown>> => get(`/api/books/${bookId}/settings`)
export const updateBookSettings = (bookId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> =>
  put(`/api/books/${bookId}/settings`, data)
export const deleteBookSettings = (bookId: string): Promise<unknown> => del(`/api/books/${bookId}/settings`)
export const getEffectiveSettings = (bookId: string): Promise<SettingsData> => get(`/api/settings/effective/${bookId}`)

// ── Update check ──

export const getUpdateStatus = (): Promise<UpdateStatus> => get('/api/update/status')
export const checkForUpdate = (): Promise<UpdateCheckResult> => get('/api/update/check')
export const toggleUpdateCheck = (enabled: boolean): Promise<{ update_check_enabled: boolean }> =>
  post('/api/update/toggle', { enabled })
