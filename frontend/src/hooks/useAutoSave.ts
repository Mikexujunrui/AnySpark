import { useState, useRef, useEffect, useCallback } from 'react'

interface UseAutoSaveOptions {
  /** 保存函数，返回 Promise */
  saveFn: () => Promise<void>
  /** 自动保存间隔（毫秒），默认 30000 */
  interval?: number
  /** 是否启用自动保存，默认 true */
  enabled?: boolean
}

/**
 * 自动保存 Hook — 独立于编辑器组件，可复用。
 * - 定时自动保存（默认 30s）
 * - 页面关闭/刷新前保存（beforeunload）
 * - 脏状态追踪与 UI 指示
 */
export function useAutoSave({
  saveFn,
  interval = 30000,
  enabled = true,
}: UseAutoSaveOptions) {
  const [isDirty, setIsDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const saveFnRef = useRef(saveFn)

  // 同步最新的 saveFn 到 ref（避免闭包陈旧）
  useEffect(() => { saveFnRef.current = saveFn }, [saveFn])

  const doSave = useCallback(async () => {
    if (!isDirty) return
    setIsSaving(true)
    try {
      await saveFnRef.current()
      setIsDirty(false)
    } catch {
      // 保存失败不重置脏状态，下次重试
    } finally {
      setIsSaving(false)
    }
  }, [isDirty])

  // 定时自动保存
  useEffect(() => {
    if (!enabled) return
    const timer = setInterval(() => doSave(), interval)
    return () => clearInterval(timer)
  }, [enabled, interval, doSave])

  // 页面关闭前保存
  useEffect(() => {
    if (!enabled) return
    const onBeforeUnload = () => { doSave() }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [enabled, doSave])

  const markDirty = useCallback(() => setIsDirty(true), [])

  return { save: doSave, markDirty, isSaving, isDirty } as const
}