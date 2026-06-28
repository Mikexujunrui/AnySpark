const API = ''

async function assertOk(res: Response): Promise<void> {
  if (res.ok) return
  let message: string = res.statusText || `请求失败 (${res.status})`
  const data = await res.json().catch(() => null)
  if (data && (data.error || data.detail || data.message)) {
    message = data.error || data.detail || data.message
  }
  throw new Error(message)
}

async function get<T = unknown>(url: string): Promise<T> {
  const res = await fetch(API + url)
  await assertOk(res)
  return res.json()
}

async function post<T = unknown>(url: string, data?: unknown): Promise<T> {
  const res = await fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  await assertOk(res)
  return res.json()
}

async function del<T = unknown>(url: string): Promise<T> {
  const res = await fetch(API + url, {
    method: 'DELETE',
    headers: { 'X-Confirm-Delete': 'true' },
  })
  await assertOk(res)
  return res.json()
}

async function put<T = unknown>(url: string, data?: unknown): Promise<T> {
  const res = await fetch(API + url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  await assertOk(res)
  return res.json()
}

export interface UpdateStatus {
  current_version: string
  update_check_enabled: boolean
}

export interface UpdateCheckResult {
  current_version: string
  latest_version: string | null
  has_update: boolean
  release_url: string
  release_notes: string | null
  published_at: string | null
  error: string | null
  message?: string
  update_check_enabled?: boolean
}

export interface BookData {
  id: string
  title: string
  description: string
  entityCount: number
  chapterCount: number
  createdAt: string
  updatedAt: string
}

export interface SessionData {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messageCount: number
}

export interface ProviderData {
  id: string
  name: string
  type: string
  api_key?: string
  base_url?: string
  models: string[]
}

export interface AutopilotTaskData {
  task_id: string
  status: string
  audit_mode: string
  progress: number
  chapters_completed: number
  total_chapters: number
}

export interface AutopilotStatusData {
  active: boolean
  tasks: AutopilotTaskData[]
}

export interface StylesListData {
  styles: unknown[]
}

export interface SkillsListData {
  skills: SkillData[]
}

export interface SkillData {
  name: string
  description: string
  steps: unknown[]
}

export interface SettingsData {
  mode: string
  providers: ProviderData[]
  slot_pro?: { provider_id: string; model: string }
  slot_flash?: { provider_id: string; model: string }
  custom_map?: Record<string, string>
}

export const api = {
  // Books
  getBooks: (): Promise<BookData[]> => get('/api/books'),
  getBook: (id: string): Promise<BookData> => get(`/api/books/${id}`),
  createBook: (data: Partial<BookData>): Promise<BookData> => post('/api/books', data),
  updateBook: (id: string, data: Partial<BookData>): Promise<BookData> => put(`/api/books/${id}`, data),
  deleteBook: (id: string): Promise<unknown> => del(`/api/books/${id}`),

  // Sessions
  getSessions: (bookId: string): Promise<SessionData[]> => get(`/api/books/${bookId}/sessions`),
  createSession: (bookId: string, title: string): Promise<SessionData> => post(`/api/books/${bookId}/sessions`, { title }),
  deleteSession: (bookId: string, sessionId: string): Promise<unknown> => del(`/api/books/${bookId}/sessions/${sessionId}`),

  // Materials
  getMaterials: (bookId?: string): Promise<unknown[]> => get(`/api/materials?book_id=${bookId || ''}`),
  searchMaterials: (q: string, bookId?: string): Promise<unknown[]> => get(`/api/materials/search?q=${encodeURIComponent(q)}&book_id=${bookId || ''}`),
  createMaterial: (data: unknown): Promise<unknown> => post('/api/materials', data),
  deleteMaterial: (id: string): Promise<unknown> => del(`/api/materials/${id}`),
  subscribeMaterial: (bookId: string, materialId: string): Promise<unknown> => post(`/api/books/${bookId}/material-subs`, { material_id: materialId }),
  unsubscribeMaterial: (bookId: string, materialId: string): Promise<unknown> => del(`/api/books/${bookId}/material-subs/${materialId}`),

  // Reference books
  getReferences: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/references`),
  setReferences: (bookId: string, bookIds: string[]): Promise<unknown> => put(`/api/books/${bookId}/references`, { book_ids: bookIds }),

  // Styles
  getStyles: (): Promise<StylesListData> => get('/api/styles'),
  getStyle: (name: string): Promise<unknown> => get(`/api/styles/${name}`),
  createStyle: (data: unknown): Promise<unknown> => post('/api/styles/custom', data),
  updateStyle: (name: string, data: unknown): Promise<unknown> => put(`/api/styles/custom/${name}`, data),
  deleteStyle: (name: string): Promise<unknown> => del(`/api/styles/custom/${name}`),
  getActiveStyle: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/style`),
  setActiveStyle: (bookId: string, name: string): Promise<unknown> => put(`/api/books/${bookId}/style`, { name }),

  // Skills
  getSkills: (): Promise<SkillsListData> => get('/api/skills'),

  // Workflows (global pool)
  getGlobalWorkflows: (): Promise<unknown[]> => get('/api/workflows'),
  deleteGlobalWorkflow: (wfId: string): Promise<unknown> => del(`/api/workflows/${wfId}`),

  // Stats
  getWritingStats: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/stats`),

  // Character mentions (heatmap)
  getCharacterMentions: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/character-mentions`),
  refreshCharacterMentions: (bookId: string): Promise<unknown> => post(`/api/books/${bookId}/character-mentions/refresh`, {}),

  // Knowledge
  getSummary: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/knowledge/summary`),
  deleteEntity: (bookId: string, entityId: string): Promise<unknown> => del(`/api/books/${bookId}/knowledge/entity/${entityId}`),
  updateEntity: (bookId: string, entityId: string, payload: unknown): Promise<unknown> => put(`/api/books/${bookId}/knowledge/entity/${entityId}`, payload),

  // Extract
  extract: (text: string, bookId: string): Promise<unknown> => post('/api/extract', { text, book_id: bookId }),

  // Tasks
  getTasks: (bookId: string, status?: string): Promise<unknown[]> => get(`/api/books/${bookId}/tasks${status ? `?status=${status}` : ''}`),
  getTask: (bookId: string, taskId: string): Promise<unknown> => get(`/api/books/${bookId}/tasks/${taskId}`),
  createTask: (bookId: string, data: unknown): Promise<unknown> => post(`/api/books/${bookId}/tasks`, data),
  startTask: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/start`, {}),
  pauseTask: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/pause`, {}),
  resumeTask: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/resume`, {}),
  cancelTask: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/cancel`, {}),
  retryTask: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/tasks/${taskId}/retry`, {}),
  setAuditMode: (bookId: string, taskId: string, mode: string): Promise<unknown> => put(`/api/books/${bookId}/tasks/${taskId}/audit-mode`, { mode }),

  // Autopilot
  startAutopilot: (bookId: string, config: unknown): Promise<unknown> => post(`/api/books/${bookId}/autopilot/start`, config),
  confirmAutopilot: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/autopilot/${taskId}/confirm`, {}),
  stopAutopilot: (bookId: string, taskId: string): Promise<unknown> => post(`/api/books/${bookId}/autopilot/${taskId}/stop`, {}),
  getAutopilotStatus: (bookId: string): Promise<AutopilotStatusData> => get(`/api/books/${bookId}/autopilot/status`),
  getAutopilotTaskStatus: (bookId: string, taskId: string): Promise<unknown> => get(`/api/books/${bookId}/autopilot/${taskId}/status`),

  // Supervisor
  getSupervisorStatus: (): Promise<unknown> => get('/api/supervisor/status'),
  triggerRecovery: (): Promise<unknown> => post('/api/supervisor/recover', {}),

  // Settings
  getSettings: (): Promise<SettingsData> => get('/api/settings'),
  updateProvider: (provider: unknown): Promise<SettingsData> => post('/api/settings/providers', provider),
  deleteProvider: (id: string): Promise<SettingsData> => del(`/api/settings/providers/${id}`),
  updateSlots: (slots: unknown): Promise<SettingsData> => post('/api/settings/slots', slots),
  switchMode: (mode: string, customMap?: Record<string, string>): Promise<SettingsData> => post('/api/settings/mode', { mode, custom_map: customMap }),
  testProvider: (providerId: string): Promise<unknown> => post('/api/settings/test', { provider_id: providerId }),

  // Book-level settings (config layering)
  getBookSettings: (bookId: string): Promise<Record<string, unknown>> => get(`/api/books/${bookId}/settings`),
  updateBookSettings: (bookId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> => put(`/api/books/${bookId}/settings`, data),
  deleteBookSettings: (bookId: string): Promise<unknown> => del(`/api/books/${bookId}/settings`),
  getEffectiveSettings: (bookId: string): Promise<SettingsData> => get(`/api/settings/effective/${bookId}`),

  // Update check
  getUpdateStatus: (): Promise<UpdateStatus> => get('/api/update/status'),
  checkForUpdate: (): Promise<UpdateCheckResult> => get('/api/update/check'),
  toggleUpdateCheck: (enabled: boolean): Promise<{ update_check_enabled: boolean }> => post('/api/update/toggle', { enabled }),
}

export function createSSE(url: string, data: unknown, signal?: AbortSignal): Promise<Response> {
  return fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
  })
}

export function createTaskSSE(bookId: string, taskId: string): Promise<Response> {
  return fetch(API + `/api/books/${bookId}/tasks/${taskId}/stream`)
}

export function createAutopilotBridgeSSE(bookId: string, taskId: string): Promise<Response> {
  return fetch(API + `/api/books/${bookId}/autopilot/${taskId}/chat-bridge`)
}

// ── Document Import ──

export async function uploadDocument(bookId: string, file: File): Promise<unknown> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(API + `/api/books/${bookId}/upload`, {
    method: 'POST',
    body: formData,
  })
  await assertOk(res)
  return res.json()
}

export async function detectChapters(bookId: string, docId: string): Promise<unknown> {
  return post(`/api/books/${bookId}/documents/${docId}/detect-chapters`, {})
}

export async function importChapters(bookId: string, docId: string, data: unknown): Promise<unknown> {
  return post(`/api/books/${bookId}/documents/${docId}/import-chapters`, data)
}

export async function batchExtractKnowledge(bookId: string, docId: string, chapterIds: string[]): Promise<unknown> {
  return post(`/api/books/${bookId}/documents/${docId}/import-chapters/batch-extract`, { chapter_ids: chapterIds })
}
