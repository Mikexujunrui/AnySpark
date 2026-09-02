// 章节定位通道（S257）：跨面板「跳到某章」的最小机制。
// 背景：SearchPanel 点击命中结果此前调用 no-op 的 tabStore.openTab——用户点击无任何反应。
// ChaptersPanel 订阅本 store，收到焦点请求后在自己的章节列表里选中该章。
import { create } from 'zustand'

interface ChapterFocusState {
  /** 请求 ChaptersPanel 定位到的章节 id */
  chapterId: string | null
  /** 自增序号：重复点击同一章也能再次触发 effect */
  seq: number
  focusChapter: (chapterId: string) => void
  /** ChaptersPanel 消费后调用（防状态残留重复触发） */
  consume: () => void
}

export const useChapterFocus = create<ChapterFocusState>((set) => ({
  chapterId: null,
  seq: 0,
  focusChapter: (chapterId) => set((s) => ({ chapterId, seq: s.seq + 1 })),
  consume: () => set({ chapterId: null }),
}))
