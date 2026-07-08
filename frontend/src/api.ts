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

export interface StructureReportData {
  book_id: string
  chapter_count: number
  total_words: number
  avg_chapter_length: number
  chapter_length_distribution: number[]
  dialogue_ratio_distribution: number[]
  avg_dialogue_ratio: number
  paragraph_stats: { avg_per_chapter: number; avg_length: number }
  sentence_stats: { avg_per_chapter: number; avg_length: number }
  pacing_curve: { chapter: number; title: string; word_count: number; dialogue_ratio: number; pace_score: number }[]
  pov_distribution: Record<string, number>
}

export interface StyleFingerprintData {
  book_id: string
  sentence_length_distribution: Record<string, number>
  vocabulary_richness_ttr: number
  punctuation_pattern: Record<string, number>
  four_char_idiom_density: number
  paragraph_length_stats: { mean: number; median: number; std: number }
  dialogue_density: number
}

export interface AnalysisSummaryData {
  ref_book_id: string
  structure?: { chapter_count: number; total_words: number; avg_chapter_length: number; avg_dialogue_ratio: number }
  style_fingerprint?: { vocabulary_richness_ttr: number; dialogue_density: number; four_char_idiom_density: number }
  deep_style?: { dimensions_analyzed: number }
  emotional_curve?: { chapter_count: number }
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

  // Reference work analysis
  triggerStructureAnalysis: (bookId: string, refBookId?: string): Promise<StructureReportData> =>
    post(`/api/books/${bookId}/analyses/structure${refBookId ? `?ref_book_id=${refBookId}` : ''}`),
  getStructureAnalysis: (bookId: string, refBookId?: string): Promise<StructureReportData> =>
    get(`/api/books/${bookId}/analyses/structure${refBookId ? `?ref_book_id=${refBookId}` : ''}`),
  triggerStyleAnalysis: (bookId: string, refBookId?: string): Promise<StyleFingerprintData> =>
    post(`/api/books/${bookId}/analyses/style${refBookId ? `?ref_book_id=${refBookId}` : ''}`),
  getStyleAnalysis: (bookId: string, refBookId?: string): Promise<StyleFingerprintData> =>
    get(`/api/books/${bookId}/analyses/style${refBookId ? `?ref_book_id=${refBookId}` : ''}`),
  listAnalyses: (bookId: string): Promise<{ analyses: AnalysisSummaryData[] }> =>
    get(`/api/books/${bookId}/analyses`),

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

  // ── Chapters ──
  getChapters: (bookId: string): Promise<unknown[]> => get(`/api/books/${bookId}/chapters`),
  createChapter: (bookId: string, data: unknown): Promise<unknown> =>
    post(`/api/books/${bookId}/chapters`, data),
  updateChapter: (bookId: string, chapterId: string, data: unknown): Promise<unknown> =>
    put(`/api/books/${bookId}/chapters/${chapterId}`, data),
  deleteChapter: (bookId: string, chapterId: string): Promise<unknown> =>
    del(`/api/books/${bookId}/chapters/${chapterId}`),

  // ── Volumes ──
  getVolumes: (bookId: string): Promise<{ volumes: unknown[] }> => get(`/api/books/${bookId}/volumes`),

  // ── Export ──
  exportBook: (bookId: string, format?: string): Promise<Response> =>
    fetch(`/api/books/${bookId}/export?format=${format || 'txt'}`),

  // ── Chapter status ──
  promoteChapter: (bookId: string, chapterId: string): Promise<{ status: string }> =>
    post(`/api/books/${bookId}/chapters/${chapterId}/promote`, {}),
  demoteChapter: (bookId: string, chapterId: string): Promise<{ status: string }> =>
    post(`/api/books/${bookId}/chapters/${chapterId}/demote`, {}),

  // ── Outline ──
  getOutline: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/outline`),
  getDetailedOutline: (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/detailed-outline`),

  // ── Chapter history / versions ──
  getChapterHistory: (bookId: string, chapterId: string): Promise<unknown[]> =>
    get(`/api/books/${bookId}/chapters/${chapterId}/history`),
  getChapterVersion: (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
    get(`/api/books/${bookId}/chapters/${chapterId}/versions/${versionId}`),
  revertChapter: (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
    post(`/api/books/${bookId}/chapters/${chapterId}/revert`, { version_id: versionId }),
  deleteChapterVersion: (bookId: string, chapterId: string, versionId: string): Promise<unknown> =>
    del(`/api/books/${bookId}/chapters/${chapterId}/versions/${versionId}`),

  // ── Deep style analysis ──
  triggerDeepStyle: (bookId: string, analysisType: string, refBookId?: string): Promise<Record<string, unknown>> =>
    post(`/api/books/${bookId}/analyses/deep-style?analysis_type=${analysisType}${refBookId ? `&ref_book_id=${refBookId}` : ''}`),
  getDeepStyle: (bookId: string, analysisType: string, refBookId?: string): Promise<Record<string, unknown>> =>
    get(`/api/books/${bookId}/analyses/deep-style?analysis_type=${analysisType}${refBookId ? `&ref_book_id=${refBookId}` : ''}`),

  // ── Emotional curve ──
  triggerEmotionalCurve: (bookId: string, refBookId?: string): Promise<Record<string, unknown>> =>
    post(`/api/books/${bookId}/analyses/emotional-curve${refBookId ? `?ref_book_id=${refBookId}` : ''}`),
  getEmotionalCurve: (bookId: string, refBookId?: string): Promise<Record<string, unknown>> =>
    get(`/api/books/${bookId}/analyses/emotional-curve${refBookId ? `?ref_book_id=${refBookId}` : ''}`),

  // ── Worldbuilding entry edit ──
  updateWorldbuildingEntry: (bookId: string, entryId: string, data: Record<string, unknown>): Promise<unknown> =>
    put(`/api/books/${bookId}/worldbuilding/entries/${entryId}`, data),
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

export async function uploadDocument(bookId: string, file: File, sessionId?: string): Promise<unknown> {
  const formData = new FormData()
  formData.append('file', file)
  if (sessionId) formData.append('session_id', sessionId)
  const res = await fetch(API + `/api/books/${bookId}/upload`, {
    method: 'POST',
    body: formData,
  })
  await assertOk(res)
  return res.json()
}

export async function detectChapters(bookId: string, docId: string, sessionId?: string): Promise<unknown> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  return post(`/api/books/${bookId}/documents/${docId}/detect-chapters${query}`, {})
}

export async function importChapters(bookId: string, docId: string, data: unknown, sessionId?: string): Promise<unknown> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  return post(`/api/books/${bookId}/documents/${docId}/import-chapters${query}`, data)
}

export async function batchExtractKnowledge(bookId: string, docId: string, chapterIds: string[]): Promise<unknown> {
  return post(`/api/books/${bookId}/documents/${docId}/import-chapters/batch-extract`, { chapter_ids: chapterIds })
}
