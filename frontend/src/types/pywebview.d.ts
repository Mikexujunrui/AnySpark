export {}

declare global {
  interface Window {
    pywebview?: {
      api?: {
        export_book?: (bookId: string, format: string) => Promise<{
          saved: boolean
          cancelled?: boolean
          path?: string
          filename?: string
          error?: string
        }>
      }
    }
  }
}
