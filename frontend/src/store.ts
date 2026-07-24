import { useSyncExternalStore } from 'react'

export interface AppState {
  books: unknown[]
  currentBookId: string | null
  refreshKey: number
  notifications: Notification[]
  // 4D Map: Time axis synchronization
  selectedTimeOrder: number
  maxTimeOrder: number
  timelineEvents: { timeOrder: number; label: string; chapterRef: string }[]
  // ── Backend connection status ──
  backendStatus: BackendStatusState
}

export interface BackendStatusState {
  status: 'connecting' | 'online' | 'degraded' | 'offline'
  latencyMs: number | null
  lastCheckAt: number | null
  failCount: number
  failReason: string | null
}

export interface Notification {
  id: number
  msg: string
  type: string
}

type Listener = () => void
type SetStateFn<T> = T | ((prev: T) => T)

function createStore<T extends object>(initialState: T) {
  let state: T = initialState
  const listeners = new Set<Listener>()

  function getState(): T {
    return state
  }

  function setState(partial: SetStateFn<Partial<T>>): void {
    const next = typeof partial === 'function' ? partial(state) : partial
    state = { ...state, ...next }
    listeners.forEach(l => l())
  }

  function subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
  }

  function useStore<R>(selector: (s: T) => R): R {
    return useSyncExternalStore(
      subscribe,
      () => selector(state),
    )
  }

  return { getState, setState, subscribe, useStore }
}

export const appStore = createStore<AppState>({
  books: [],
  currentBookId: null,
  refreshKey: 0,
  notifications: [],
  // 4D Map defaults
  selectedTimeOrder: 0,
  maxTimeOrder: 0,
  timelineEvents: [],
  // Backend connection defaults
  backendStatus: {
    status: 'connecting',
    latencyMs: null,
    lastCheckAt: null,
    failCount: 0,
    failReason: null,
  },
})

export function useBooks(): unknown[] {
  return appStore.useStore(s => s.books)
}

export function useRefreshKey(): number {
  return appStore.useStore(s => s.refreshKey)
}

export function useNotifications(): Notification[] {
  return appStore.useStore(s => s.notifications)
}

export function triggerRefresh(): void {
  appStore.setState(s => ({ refreshKey: s.refreshKey + 1 }))
}

export function addNotification(msg: string, type: string = 'info'): void {
  const id = Date.now()
  appStore.setState(s => ({
    notifications: [...s.notifications, { id, msg, type }]
  }))
  setTimeout(() => {
    appStore.setState(s => ({
      notifications: s.notifications.filter(n => n.id !== id)
    }))
  }, 5000)
}

export { createStore }

// ── 4D Map: Time axis selectors ──

export function useSelectedTimeOrder(): number {
  return appStore.useStore(s => s.selectedTimeOrder)
}

export function useMaxTimeOrder(): number {
  return appStore.useStore(s => s.maxTimeOrder)
}

export function useTimelineEvents(): { timeOrder: number; label: string; chapterRef: string }[] {
  return appStore.useStore(s => s.timelineEvents)
}

export function setTimeOrder(order: number): void {
  appStore.setState({ selectedTimeOrder: order })
}

export function setTimelineMeta(events: { timeOrder: number; label: string; chapterRef: string }[]): void {
  const max = events.length > 0 ? Math.max(...events.map(e => e.timeOrder)) : 0
  appStore.setState({ timelineEvents: events, maxTimeOrder: max })
}

// ── Backend connection status ──

export function useBackendStatus(): BackendStatusState {
  return appStore.useStore(s => s.backendStatus)
}

export function setBackendStatus(partial: Partial<BackendStatusState>): void {
  appStore.setState(s => ({
    backendStatus: { ...s.backendStatus, ...partial },
  }))
}
