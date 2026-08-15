let toastId = 0
const listeners = new Set<(toast: any) => void>()

export function showToast(message: string, type = 'info', duration = 4000, undoAction: (() => void) | null = null) {
  const id = ++toastId
  listeners.forEach(fn => fn({ id, message, type, duration, undoAction }))
}

export { listeners }