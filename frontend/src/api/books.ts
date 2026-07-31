// Books / Sessions / Materials / Reference books / Analyses — domain module.
import { assertOk, del, get, post, put } from './http'
import type {
  AnalysisSummaryData,
  BookData,
  SessionData,
  StructureReportData,
  StyleFingerprintData,
} from './types'

// ── Books ──

export const getBooks = (): Promise<BookData[]> => get('/api/books')
export const getBook = (id: string): Promise<BookData> => get(`/api/books/${id}`)
export const createBook = (data: Partial<BookData>): Promise<BookData> => post('/api/books', data)
export const updateBook = (id: string, data: Partial<BookData>): Promise<BookData> => put(`/api/books/${id}`, data)
export const deleteBook = (id: string): Promise<unknown> => del(`/api/books/${id}`)
export const importSparkProject = async (file: File): Promise<{ ok: boolean; book: BookData; stats: Record<string, unknown> }> => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/books/import-spark', { method: 'POST', body: formData })
  await assertOk(res)
  return res.json()
}

// ── Sessions ──

export const getSessions = (bookId: string): Promise<SessionData[]> => get(`/api/books/${bookId}/sessions`)
export const createSession = (bookId: string, title: string): Promise<SessionData> => post(`/api/books/${bookId}/sessions`, { title })
export const deleteSession = (bookId: string, sessionId: string): Promise<unknown> => del(`/api/books/${bookId}/sessions/${sessionId}`)

// ── Materials ──

export const getMaterials = (bookId?: string): Promise<unknown[]> => get(`/api/materials?book_id=${bookId || ''}`)
export const searchMaterials = (q: string, bookId?: string): Promise<unknown[]> =>
  get(`/api/materials/search?q=${encodeURIComponent(q)}&book_id=${bookId || ''}`)
export const createMaterial = (data: unknown): Promise<unknown> => post('/api/materials', data)
export const deleteMaterial = (id: string): Promise<unknown> => del(`/api/materials/${id}`)
export const subscribeMaterial = (bookId: string, materialId: string): Promise<unknown> =>
  post(`/api/books/${bookId}/material-subs`, { material_id: materialId })
export const unsubscribeMaterial = (bookId: string, materialId: string): Promise<unknown> =>
  del(`/api/books/${bookId}/material-subs/${materialId}`)

// ── Reference books ──

export const getReferences = (bookId: string): Promise<unknown> => get(`/api/books/${bookId}/references`)
export const setReferences = (bookId: string, bookIds: string[]): Promise<unknown> =>
  put(`/api/books/${bookId}/references`, { book_ids: bookIds })
export const setReferenceUsage = (bookId: string, refBookId: string, usage: 'style' | 'canon' | 'both'): Promise<unknown> =>
  put(`/api/books/${bookId}/references/${refBookId}/usage`, { usage })

// ── Reference work analysis ──

export const triggerStructureAnalysis = (bookId: string, refBookId?: string): Promise<StructureReportData> =>
  post(`/api/books/${bookId}/analyses/structure${refBookId ? `?ref_book_id=${refBookId}` : ''}`)
export const getStructureAnalysis = (bookId: string, refBookId?: string): Promise<StructureReportData> =>
  get(`/api/books/${bookId}/analyses/structure${refBookId ? `?ref_book_id=${refBookId}` : ''}`)
export const triggerStyleAnalysis = (bookId: string, refBookId?: string): Promise<StyleFingerprintData> =>
  post(`/api/books/${bookId}/analyses/style${refBookId ? `?ref_book_id=${refBookId}` : ''}`)
export const getStyleAnalysis = (bookId: string, refBookId?: string): Promise<StyleFingerprintData> =>
  get(`/api/books/${bookId}/analyses/style${refBookId ? `?ref_book_id=${refBookId}` : ''}`)
export const listAnalyses = (bookId: string): Promise<{ analyses: AnalysisSummaryData[] }> =>
  get(`/api/books/${bookId}/analyses`)
