// Document import — domain module.
import { assertOk, diagLog, post } from './http'

const API = ''

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
