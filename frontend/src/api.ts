// API 层门面 — 各域函数已拆分至 api/ 子模块；本文件保留聚合对象
// 与类型 re-export，兼容既有消费方。HTTP 基础设施见 api/http.ts，SSE 见 api/sse.ts。
import { createAutopilotBridgeSSE, createSSE, createTaskSSE } from './api/sse'
export { createAutopilotBridgeSSE, createSSE, createTaskSSE }

// ── 类型 re-export ──
export type {
  AnalysisSummaryData,
  AutopilotStatusData,
  AutopilotTaskData,
  BookData,
  ProviderData,
  SessionData,
  SettingsData,
  SkillData,
  SkillsListData,
  StructureReportData,
  StyleFingerprintData,
  StylesListData,
  UpdateCheckResult,
  UpdateStatus,
} from './api/types'

// ── 域函数 re-export ──
import * as books from './api/books'
import * as chapters from './api/chapters'
import * as knowledge from './api/knowledge'
import * as tasks from './api/tasks'
import * as settings from './api/settings'
import * as memory from './api/memory'
import { batchExtractKnowledge, detectChapters, importChapters, uploadDocument } from './api/import'

export { books, chapters, knowledge, tasks, settings, memory, uploadDocument, detectChapters, importChapters, batchExtractKnowledge }

// ── 聚合对象（兼容历史消费方 `api.xxx`）──
export const api = {
  // Books
  getBooks: books.getBooks,
  getBook: books.getBook,
  createBook: books.createBook,
  updateBook: books.updateBook,
  deleteBook: books.deleteBook,
  importSparkProject: books.importSparkProject,

  // Sessions
  getSessions: books.getSessions,
  createSession: books.createSession,
  deleteSession: books.deleteSession,

  // Materials
  getMaterials: books.getMaterials,
  searchMaterials: books.searchMaterials,
  createMaterial: books.createMaterial,
  deleteMaterial: books.deleteMaterial,
  subscribeMaterial: books.subscribeMaterial,
  unsubscribeMaterial: books.unsubscribeMaterial,

  // Reference books
  getReferences: books.getReferences,
  setReferences: books.setReferences,
  setReferenceUsage: books.setReferenceUsage,

  // Reference work analysis
  triggerStructureAnalysis: books.triggerStructureAnalysis,
  getStructureAnalysis: books.getStructureAnalysis,
  triggerStyleAnalysis: books.triggerStyleAnalysis,
  getStyleAnalysis: books.getStyleAnalysis,
  listAnalyses: books.listAnalyses,

  // Styles
  getStyles: knowledge.getStyles,
  getStyle: knowledge.getStyle,
  createStyle: knowledge.createStyle,
  updateStyle: knowledge.updateStyle,
  deleteStyle: knowledge.deleteStyle,
  getActiveStyle: knowledge.getActiveStyle,
  setActiveStyle: knowledge.setActiveStyle,

  // Skills
  getSkills: knowledge.getSkills,

  // Workflows (global pool)
  getGlobalWorkflows: knowledge.getGlobalWorkflows,
  deleteGlobalWorkflow: knowledge.deleteGlobalWorkflow,

  // Stats
  getWritingStats: knowledge.getWritingStats,

  // Character mentions (heatmap)
  getCharacterMentions: knowledge.getCharacterMentions,
  refreshCharacterMentions: knowledge.refreshCharacterMentions,

  // Knowledge
  getSummary: knowledge.getSummary,
  deleteEntity: knowledge.deleteEntity,
  updateEntity: knowledge.updateEntity,
  createEntity: knowledge.createEntity,

  // Extract
  extract: knowledge.extract,

  // Tasks
  getTasks: tasks.getTasks,
  getTask: tasks.getTask,
  createTask: tasks.createTask,
  startTask: tasks.startTask,
  pauseTask: tasks.pauseTask,
  resumeTask: tasks.resumeTask,
  cancelTask: tasks.cancelTask,
  retryTask: tasks.retryTask,
  setAuditMode: tasks.setAuditMode,

  // Autopilot
  startAutopilot: tasks.startAutopilot,
  confirmAutopilot: tasks.confirmAutopilot,
  stopAutopilot: tasks.stopAutopilot,
  getAutopilotStatus: tasks.getAutopilotStatus,
  getAutopilotTaskStatus: tasks.getAutopilotTaskStatus,

  // Supervisor
  getSupervisorStatus: tasks.getSupervisorStatus,
  triggerRecovery: tasks.triggerRecovery,

  // Settings
  getSettings: settings.getSettings,
  updateProvider: settings.updateProvider,
  deleteProvider: settings.deleteProvider,
  updateSlots: settings.updateSlots,
  switchMode: settings.switchMode,
  testProvider: settings.testProvider,

  // Book-level settings (config layering)
  getBookSettings: settings.getBookSettings,
  updateBookSettings: settings.updateBookSettings,
  deleteBookSettings: settings.deleteBookSettings,
  getEffectiveSettings: settings.getEffectiveSettings,

  // Update check
  getUpdateStatus: settings.getUpdateStatus,
  checkForUpdate: settings.checkForUpdate,
  toggleUpdateCheck: settings.toggleUpdateCheck,

  // Chapters
  getChapters: chapters.getChapters,
  createChapter: chapters.createChapter,
  updateChapter: chapters.updateChapter,
  deleteChapter: chapters.deleteChapter,

  // Volumes
  getVolumes: chapters.getVolumes,

  // Chapter reorder
  reorderChapters: chapters.reorderChapters,

  // Notes
  getNotes: chapters.getNotes,
  addBookNote: chapters.addBookNote,
  deleteBookNote: chapters.deleteBookNote,

  // Export
  exportBook: chapters.exportBook,

  // Chapter status
  promoteChapter: chapters.promoteChapter,
  demoteChapter: chapters.demoteChapter,

  // Outline
  getOutline: chapters.getOutline,
  getDetailedOutline: chapters.getDetailedOutline,

  // Chapter history / versions
  getChapterHistory: chapters.getChapterHistory,
  getChapterVersion: chapters.getChapterVersion,
  revertChapter: chapters.revertChapter,
  deleteChapterVersion: chapters.deleteChapterVersion,

  // Deep style analysis
  triggerDeepStyle: chapters.triggerDeepStyle,
  getDeepStyle: chapters.getDeepStyle,

  // Emotional curve
  triggerEmotionalCurve: chapters.triggerEmotionalCurve,
  getEmotionalCurve: chapters.getEmotionalCurve,

  // Worldbuilding entry edit
  updateWorldbuildingEntry: chapters.updateWorldbuildingEntry,

  // Memory system
  getMemoryStats: memory.getMemoryStats,
  getProjectMemory: memory.getProjectMemory,
  updateProjectMemory: memory.updateProjectMemory,
  addNote: memory.addNote,
  deleteNote: memory.deleteNote,
  recordDecision: memory.recordDecision,
  deleteDecision: memory.deleteDecision,
  addProgress: memory.addProgress,
  deleteProgress: memory.deleteProgress,
  getPreferences: memory.getPreferences,
  createPreference: memory.createPreference,
  confirmPreference: memory.confirmPreference,
  deletePreference: memory.deletePreference,
  toggleMemory: memory.toggleMemory,
}
