import { createStore } from "../store"

export interface Tab {
  id: string
  title: string
  bookId: string
}

interface TabState {
  tabs: Tab[]
  activeTabId: string | null
}

export const tabStore = createStore<TabState>({
  tabs: [],
  activeTabId: null,
})

export function useTabs(): Tab[] {
  return tabStore.useStore(s => s.tabs)
}

export function useActiveTabId(): string | null {
  return tabStore.useStore(s => s.activeTabId)
}

export function openTab(chapterId: string, title: string, bookId: string): string {
  const state = tabStore.getState()
  const existing = state.tabs.find(t => t.id === chapterId)
  if (!existing) {
    tabStore.setState(s => ({
      tabs: [...s.tabs, { id: chapterId, title, bookId }],
      activeTabId: chapterId,
    }))
  } else {
    tabStore.setState({ activeTabId: chapterId })
  }
  return chapterId
}

export function closeTab(chapterId: string): void {
  const state = tabStore.getState()
  const idx = state.tabs.findIndex(t => t.id === chapterId)
  const newTabs = state.tabs.filter(t => t.id !== chapterId)
  let newActiveId = state.activeTabId
  if (state.activeTabId === chapterId) {
    if (newTabs.length > 0) {
      const newIdx = Math.min(idx, newTabs.length - 1)
      newActiveId = newTabs[newIdx].id
    } else {
      newActiveId = null
    }
  }
  tabStore.setState({ tabs: newTabs, activeTabId: newActiveId })
}

export function setActiveTab(chapterId: string): void {
  tabStore.setState({ activeTabId: chapterId })
}

/** 清除指定书籍的所有标签页 */
export function clearTabsForBook(bookId: string): void {
  const state = tabStore.getState()
  const newTabs = state.tabs.filter(t => t.bookId !== bookId)
  const newActiveId = state.activeTabId && !newTabs.find(t => t.id === state.activeTabId)
    ? (newTabs.length > 0 ? newTabs[0].id : null)
    : state.activeTabId
  tabStore.setState({ tabs: newTabs, activeTabId: newActiveId })
}
