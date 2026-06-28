import { useSyncExternalStore } from 'react'

export interface AppState {
  books: unknown[]
  currentBookId: string | null
  refreshKey: number
  notifications: Notification[]
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
