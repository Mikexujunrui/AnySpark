const PREFIX = 'novel_agent_'

export const storage = {
  getActiveSession(bookId: string): string | null {
    return localStorage.getItem(`${PREFIX}session_${bookId}`) || null
  },

  setActiveSession(bookId: string, sessionId: string): void {
    localStorage.setItem(`${PREFIX}session_${bookId}`, sessionId)
  },

  getActiveTab(bookId: string): string {
    return localStorage.getItem(`${PREFIX}tab_${bookId}`) || 'chat'
  },

  setActiveTab(bookId: string, tab: string): void {
    localStorage.setItem(`${PREFIX}tab_${bookId}`, tab)
  },

  getLastBook(): string | null {
    return localStorage.getItem(`${PREFIX}last_book`) || null
  },

  setLastBook(bookId: string): void {
    localStorage.setItem(`${PREFIX}last_book`, bookId)
  },

  getChatMode(bookId: string): string {
    return localStorage.getItem(`${PREFIX}chat_mode_${bookId}`) || 'write'
  },

  setChatMode(bookId: string, mode: string): void {
    localStorage.setItem(`${PREFIX}chat_mode_${bookId}`, mode)
  },

  getAutoMode(bookId: string): boolean | null {
    const val = localStorage.getItem(`${PREFIX}auto_mode_${bookId}`)
    return val === null ? null : val === 'true'
  },

  setAutoMode(bookId: string, enabled: boolean): void {
    localStorage.setItem(`${PREFIX}auto_mode_${bookId}`, String(enabled))
  },

  // ── Generic key-value storage (for layout, preferences, etc.) ──
  get<T = unknown>(key: string): T | null {
    try {
      const raw = localStorage.getItem(`${PREFIX}${key}`)
      return raw ? (JSON.parse(raw) as T) : null
    } catch {
      return null
    }
  },

  set(key: string, value: unknown): void {
    localStorage.setItem(`${PREFIX}${key}`, JSON.stringify(value))
  },
}
