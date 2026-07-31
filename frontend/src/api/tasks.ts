// Tasks / Autopilot / Supervisor — domain module.
import { get, post, put } from './http'
import type { AutopilotStatusData } from './types'

// ── Tasks ──

export const getTasks = (bookId: string, status?: string): Promise<unknown[]> =>
  get(`/api/books/${bookId}/tasks${status ? `?status=${status}` : ''}`)
export const getTask = (bookId: string, taskId: string): Promise<unknown> => get(`/api/books/${bookId}/tasks/${taskId}`)
export const createTask = (bookId: string, data: unknown): Promise<unknown> => post(`/api/books/${bookId}/tasks`, data)
export const startTask = (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/start`, {})
export const pauseTask = (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/pause`, {})
export const resumeTask = (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/resume`, {})
export const cancelTask = (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/cancel`, {})
export const retryTask = (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/retry`, {})
export const setAuditMode = (bookId: string, taskId: string, mode: string): Promise<unknown> =>
  put(`/api/books/${bookId}/tasks/${taskId}/audit-mode`, { mode })

// ── Autopilot ──

export const startAutopilot = (bookId: string, config: unknown): Promise<unknown> =>
  post(`/api/books/${bookId}/autopilot/start`, config)
export const confirmAutopilot = (bookId: string, taskId: string): Promise<unknown> =>
  post(`/api/books/${bookId}/autopilot/${taskId}/confirm`, {})
export const stopAutopilot = (bookId: string, taskId: string): Promise<unknown> =>
  post(`/api/books/${bookId}/autopilot/${taskId}/stop`, {})
export const getAutopilotStatus = (bookId: string): Promise<AutopilotStatusData> =>
  get(`/api/books/${bookId}/autopilot/status`)
export const getAutopilotTaskStatus = (bookId: string, taskId: string): Promise<unknown> =>
  get(`/api/books/${bookId}/autopilot/${taskId}/status`)

// ── Supervisor ──

export const getSupervisorStatus = (): Promise<unknown> => get('/api/supervisor/status')
export const triggerRecovery = (): Promise<unknown> => post('/api/supervisor/recover', {})
