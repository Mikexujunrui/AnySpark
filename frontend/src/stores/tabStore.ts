// tab 状态 stub（V4 壳移植：BookDetail 自管 tab，此 store 降级）
import { create } from 'zustand'

interface TabState {
  activeTab: string
  setActiveTab: (t: string) => void
}

export const useTabs = () => [] as any[]

export const openTab = (..._args: unknown[]) => {}
export const closeTab = (..._args: unknown[]) => {}
export const setActiveTab = (..._args: unknown[]) => {}
export const clearTabsForBook = (..._args: unknown[]) => {}

export const useTabStore = create<TabState>(() => ({
  activeTab: 'chat',
  setActiveTab: () => {},
}))
