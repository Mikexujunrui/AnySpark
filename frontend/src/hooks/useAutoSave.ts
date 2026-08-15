// 自动保存（壳签名适配：{saveFn, interval, enabled} → {isDirty, markDirty, flush}）
import { useCallback, useEffect, useRef } from 'react'

interface AutoSaveOptions {
  saveFn: () => Promise<void>
  interval?: number
  enabled?: boolean
}

export function useAutoSave({ saveFn, interval = 30000, enabled = true }: AutoSaveOptions) {
  const dirtyRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const flush = useCallback(async () => {
    if (!dirtyRef.current) return
    dirtyRef.current = false
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    try { await saveFn() } catch { /* 保存失败留给上层提示 */ }
  }, [saveFn])

  const markDirty = useCallback(() => {
    dirtyRef.current = true
  }, [])

  useEffect(() => {
    if (!enabled) return
    timerRef.current = setInterval(() => { flush() }, interval)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [enabled, interval, flush])

  return { isDirty: dirtyRef.current, isSaving: false, markDirty, flush }
}
