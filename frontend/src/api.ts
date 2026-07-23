const API = ''

// ── Connection diagnostics ──
// Structured logging for all API/SSE connections to help diagnose
// frontend-backend connectivity instability.
const DIAG_PREFIX = '[CONN-DIAG]'
const diagLog = {
  info: (msg: string, ...args: unknown[]) => {
    console.log(`${DIAG_PREFIX} ${msg}`, ...args)
  },
  warn: (msg: string, ...args: unknown[]) => {
    console.warn(`${DIAG_PREFIX} ${msg}`, ...args)
  },
  error: (msg: string, ...args: unknown[]) => {
    console.error(`${DIAG_PREFIX} ${msg}`, ...args)
  },
}

// Expose diagnostics for use in other modules
export { diagLog }

async function assertOk(res: Response): Promise<void> {
  if (res.ok) return
  let message: string = res.statusText || `请求失败 (${res.status})`
  const data = await res.json().catch(() => null)
  if (data && (data.error || data.detail || data.message)) {
    message = data.error || data.detail || data.message
  }
  throw new Error(message)
}

async function requestWithDiags<T>(method: string, url: string, options?: RequestInit): Promise<T> {
  const startTime = performance.now()
  diagLog.info(`${method} ${url} — 开始请求`)
  try {
    const res = await fetch(API + url, options)
    const elapsed = Math.round(performance.now() - startTime)
    if (!res.ok) {
      diagLog.warn(`${method} ${url} — 失败 %d | %dms`, res.status, elapsed)
    } else {
      diagLog.info(`${method} ${url} — 成功 | %dms`, elapsed)
    }
    await assertOk(res)
    return res.json()
  } catch (e) {
    const elapsed = Math.round(performance.now() - startTime)
    const errMsg = e instanceof Error ? e.message : String(e)
    diagLog.error(`${method} ${url} — 异常 | %dms | %s`, elapsed, errMsg)
    throw e
  }
}

async function get<T = unknown>(url: string): Promise<T> {
  return requestWithDiags<T>('GET', url)
}

async function post<T = unknown>(url: string, data?: unknown): Promise<T> {
  return requestWithDiags<T>('POST', url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

async function del<T = unknown>(url: string): Promise<T> {
  return requestWithDiags<T>('DELETE', url, {
    method: 'DELETE',
    headers: { 'X-Confirm-Delete': 'true' },
  })
}

async function put<T = unknown>(url: string, data?: unknown): Promise<T> {
  return requestWithDiags<T>('PUT', url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
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

  // ── Chapter reorder ──
  reorderChapters: (bookId: string, order: string[]): Promise<{ ok: boolean; count: number }> =>
    post(`/api/books/${bookId}/chapters/reorder`, { order }),

  // ── Notes ──
  getNotes: (bookId: string): Promise<unknown[]> => get(`/api/books/${bookId}/notes`),
  addBookNote: (bookId: string, content: string, tags?: string[]): Promise<unknown> =>
    post(`/api/books/${bookId}/notes`, { content, tags }),
  deleteBookNote: (bookId: string, noteId: string): Promise<unknown> =>
    del(`/api/books/${bookId}/notes/${noteId}`),

  // ── Export ──
  exportBook: (bookId: string, format?: string): Promise<Response> => {
    const url = `/api/books/${bookId}/export?format=${format || 'txt'}`
    diagLog.info(`GET ${url} — 导出请求`)
    return fetch(API + url)
  },

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

  // ── Memory system ──
  getMemoryStats: (bookId: string): Promise<{ project: Record<string, unknown>; stats: Record<string, number>; tier0_preview: string }> =>
    get(`/api/memory/stats/${bookId}`),
  getProjectMemory: (bookId: string): Promise<Record<string, unknown>> =>
    get(`/api/memory/project/${bookId}`),
  updateProjectMemory: (bookId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> =>
    put(`/api/memory/project/${bookId}`, data),
  addNote: (bookId: string, title: string, content: string): Promise<{ ok: boolean; note: unknown }> =>
    post(`/api/memory/project/${bookId}/note`, { title, content }),
  deleteNote: (bookId: string, noteId: string): Promise<{ ok: boolean }> =>
    del(`/api/memory/project/${bookId}/note/${noteId}`),
  recordDecision: (bookId: string, title: string, rationale: string): Promise<{ ok: boolean; decision: unknown }> =>
    post(`/api/memory/project/${bookId}/decision`, { title, rationale }),
  deleteDecision: (bookId: string, decisionId: string): Promise<{ ok: boolean }> =>
    del(`/api/memory/project/${bookId}/decision/${decisionId}`),
  addProgress: (bookId: string, content: string): Promise<{ ok: boolean; note: unknown }> =>
    post(`/api/memory/project/${bookId}/progress`, { content }),
  deleteProgress: (bookId: string, noteId: string): Promise<{ ok: boolean }> =>
    del(`/api/memory/project/${bookId}/progress/${noteId}`),
  getPreferences: (): Promise<{ total: number; entries: unknown[]; category_counts: Record<string, number> }> =>
    get('/api/memory/preferences'),
  createPreference: (data: Record<string, unknown>): Promise<{ ok: boolean; entry: unknown }> =>
    post('/api/memory/preferences', data),
  confirmPreference: (entryId: string): Promise<{ ok: boolean; entry: unknown }> =>
    post(`/api/memory/preferences/${entryId}/confirm`, {}),
  deletePreference: (entryId: string): Promise<{ ok: boolean }> =>
    del(`/api/memory/preferences/${entryId}`),
  toggleMemory: (enabled: boolean): Promise<{ ok: boolean; enabled: boolean; message: string }> =>
    post('/api/memory/toggle', { enabled }),
}

export function createSSE(url: string, data: unknown, signal?: AbortSignal): Promise<Response> {
  diagLog.info(`SSE POST ${url} — 建立连接`)
  return fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
  }).then(res => {
    const ct = res.headers.get('content-type') || ''
    diagLog.info(`SSE POST ${url} — 响应 %d | content-type=%s`, res.status, ct)
    if (!res.ok) {
      diagLog.error(`SSE POST ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    if (e instanceof DOMException && e.name === 'AbortError') {
      diagLog.info(`SSE POST ${url} — 已取消 (AbortError)`)
    } else {
      diagLog.error(`SSE POST ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    }
    throw e
  })
}

export function createTaskSSE(bookId: string, taskId: string): Promise<Response> {
  const url = `/api/books/${bookId}/tasks/${taskId}/stream`
  diagLog.info(`SSE GET ${url} — 建立连接`)
  return fetch(API + url).then(res => {
    diagLog.info(`SSE GET ${url} — 响应 %d`, res.status)
    if (!res.ok) {
      diagLog.error(`SSE GET ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    diagLog.error(`SSE GET ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    throw e
  })
}

export function createAutopilotBridgeSSE(bookId: string, taskId: string): Promise<Response> {
  const url = `/api/books/${bookId}/autopilot/${taskId}/chat-bridge`
  diagLog.info(`SSE GET ${url} — 建立连接`)
  return fetch(API + url).then(res => {
    diagLog.info(`SSE GET ${url} — 响应 %d`, res.status)
    if (!res.ok) {
      diagLog.error(`SSE GET ${url} — 连接失败 %d`, res.status)
    }
    return res
  }).catch(e => {
    diagLog.error(`SSE GET ${url} — 异常: %s`, e instanceof Error ? e.message : String(e))
    throw e
  })
}

// ── Document Import ──

export async function uploadDocument(bookId: string, file: File, sessionId?: string): Promise<unknown> {
  const url = `/api/books/${bookId}/upload`
  diagLog.info(`POST ${url} — 上传文档 | name=%s | size=%d`, file.name, file.size)
  const formData = new FormData()
  formData.append('file', file)
  if (sessionId) formData.append('session_id', sessionId)
  const startTime = performance.now()
  try {
    const res = await fetch(API + url, {
      method: 'POST',
      body: formData,
    })
    const elapsed = Math.round(performance.now() - startTime)
    if (!res.ok) {
      diagLog.warn(`POST ${url} — 失败 %d | %dms`, res.status, elapsed)
    } else {
      diagLog.info(`POST ${url} — 成功 | %dms`, elapsed)
    }
    await assertOk(res)
    return res.json()
  } catch (e) {
    const elapsed = Math.round(performance.now() - startTime)
    diagLog.error(`POST ${url} — 异常 | %dms | %s`, elapsed, e instanceof Error ? e.message : String(e))
    throw e
  }
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
