// 自动保存（壳签名适配：{saveFn, interval, enabled} → {isDirty, markDirty, flush}）
// S260：isDirty 改用 state（此前是 ref，markDirty 不触发渲染 → UI「● 未保存」
// 指示永不显示，用户不知道有未保存内容）；dirty 只在 true/false 翻转时 setState
// （连续输入不重复渲染）；flush 保存成功后才清 dirty（失败保留，下轮重试）。
import { useCallback, useEffect, useRef, useState } from 'react'

interface AutoSaveOptions {
  saveFn: () => Promise<void>
  interval?: number
  enabled?: boolean
}

export function useAutoSave({ saveFn, interval = 30000, enabled = true }: AutoSaveOptions) {
  const dirtyRef = useRef(false)
  const [isDirty, setIsDirty] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const setDirty = useCallback((v: boolean) => {
    dirtyRef.current = v
    setIsDirty(v)
  }, [])

  const flush = useCallback(async () => {
    if (!dirtyRef.current) return
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    try {
      await saveFn()
      setDirty(false) // 保存成功才清 dirty；失败保留，下个 interval 重试
    } catch { /* 保存失败留给上层提示 */ }
  }, [saveFn, setDirty])

  const markDirty = useCallback(() => {
    if (!dirtyRef.current) setDirty(true) // 翻转才渲染，连续输入零开销
  }, [setDirty])

  // 保存成功后由调用方调用（手动保存不走 flush）
  const markClean = useCallback(() => {
    if (dirtyRef.current) setDirty(false)
  }, [setDirty])

  useEffect(() => {
    if (!enabled) return
    timerRef.current = setInterval(() => { void flush() }, interval)
    return () => {
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    }
  }, [enabled, interval, flush])

  return { isDirty, isSaving: false, markDirty, markClean, flush }
}
