import { create } from "zustand";
import { runCheck, type CheckReport } from "../api/check";
import { useChapterStore } from "./chapterStore";

interface CheckState {
  report: CheckReport | null;
  loading: boolean;
  error: string | null;
  timestamp: string | null;

  runCheck: (chapterId?: string) => Promise<void>;
  clearReport: () => void;
}

export const useCheckStore = create<CheckState>((set) => ({
  report: null,
  loading: false,
  error: null,
  timestamp: null,

  runCheck: async (chapterId?: string) => {
    set({ loading: true, error: null });
    try {
      // 获取当前章节内容
      const { selectedChapter, chapters, selectChapter } = useChapterStore.getState();
      let chapter = selectedChapter;
      
      // 如果指定了章节 ID 且与当前不同，先切换
      if (chapterId && chapterId !== selectedChapter?.id) {
        await selectChapter(chapterId);
        chapter = useChapterStore.getState().selectedChapter;
      }

      if (!chapter || !chapter.content?.trim()) {
        set({ loading: false, error: "当前章节无内容" });
        return;
      }

      // 获取章节序号（用于时序校验）
      const chapterOrder = chapters.findIndex((c) => c.id === chapter.id);
      
      const report = await runCheck(
        chapter.content,
        chapter.title || "当前章节",
        chapterOrder >= 0 ? chapterOrder : undefined
      );
      
      set({ report, loading: false, timestamp: new Date().toISOString() });
    } catch (error) {
      console.error("Failed to run check:", error);
      set({ loading: false, error: error instanceof Error ? error.message : "审读失败" });
    }
  },

  clearReport: () => set({ report: null, error: null, timestamp: null }),
}));
