import { useState, useCallback } from 'react'
import { storage } from '../storage.js'

interface SplitLayoutState {
  isSplit: boolean
  secondaryTab: string
}

const SPLIT_KEY = (bookId: string): string => `split_layout_${bookId}`

export function useSplitLayout(bookId: string, defaultTab: string = 'chapters') {
  const [isSplit, setIsSplit] = useState<boolean>(() => {
    const saved = storage.get<SplitLayoutState>(SPLIT_KEY(bookId))
    return saved?.isSplit || false
  })
  const [primaryTab, setPrimaryTabState] = useState<string>(defaultTab)
  const [secondaryTab, setSecondaryTabState] = useState<string>(() => {
    const saved = storage.get<SplitLayoutState>(SPLIT_KEY(bookId))
    return saved?.secondaryTab || 'outline'
  })

  const saveLayout = useCallback((split: boolean, secTab: string) => {
    storage.set(SPLIT_KEY(bookId), { isSplit: split, secondaryTab: secTab })
  }, [bookId])

  const toggleSplit = useCallback(() => {
    setIsSplit(prev => {
      const next = !prev
      saveLayout(next, secondaryTab)
      return next
    })
  }, [secondaryTab, saveLayout])

  const setPrimaryTab = useCallback((tab: string) => {
    setPrimaryTabState(tab)
    if (!isSplit) {
      storage.setActiveTab(bookId, tab)
    }
  }, [isSplit, bookId])

  const setSecondaryTab = useCallback((tab: string) => {
    setSecondaryTabState(tab)
    saveLayout(isSplit, tab)
  }, [isSplit, saveLayout])

  return {
    isSplit,
    primaryTab,
    secondaryTab,
    toggleSplit,
    setPrimaryTab,
    setSecondaryTab,
  }
}
