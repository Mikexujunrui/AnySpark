import { create } from "zustand";
import { listChapters, getChapter, createChapter, deleteChapter, patchChapter } from "../api/chapters";
import { reportSignal } from "../api/signals";
import type { Chapter } from "../types";

interface ChapterState {
  chapters: Chapter[];
  selectedId: string | null;
  selectedChapter: Chapter | null;
  loading: boolean;
  saving: boolean;

  fetchChapters: () => Promise<void>;
  selectChapter: (id: string) => Promise<void>;
  addChapter: (title: string) => Promise<void>;
  removeChapter: (id: string) => Promise<void>;
  updateChapterContent: (content: string) => Promise<void>;
}

export const useChapterStore = create<ChapterState>((set, get) => ({
  chapters: [],
  selectedId: null,
  selectedChapter: null,
  loading: false,
  saving: false,

  fetchChapters: async () => {
    set({ loading: true });
    try {
      const chapters = await listChapters();
      set({ chapters, loading: false });
      
      // 如果之前选中的章节还在列表中，保持选中
      const { selectedId } = get();
      if (selectedId && !chapters.find((c) => c.id === selectedId)) {
        set({ selectedId: null, selectedChapter: null });
      }
    } catch (error) {
      console.error("Failed to fetch chapters:", error);
      set({ loading: false });
    }
  },

  selectChapter: async (id: string) => {
    set({ selectedId: id });
    try {
      const chapter = await getChapter(id);
      set({ selectedChapter: chapter });
    } catch (error) {
      console.error("Failed to get chapter:", error);
      set({ selectedChapter: null });
    }
  },

  addChapter: async (title: string) => {
    try {
      const chapter = await createChapter(title);
      set((state) => ({
        chapters: [...state.chapters, chapter],
      }));
      // 自动选中新建的章节
      await get().selectChapter(chapter.id);
    } catch (error) {
      console.error("Failed to create chapter:", error);
      throw error;
    }
  },

  removeChapter: async (id: string) => {
    const { selectedId, chapters } = get();
    const wasSelected = selectedId === id;
    
    try {
      await deleteChapter(id);
      const remaining = chapters.filter((c) => c.id !== id);
      
      set((state) => ({
        chapters: remaining,
        selectedId: wasSelected ? (remaining[0]?.id ?? null) : state.selectedId,
        selectedChapter: wasSelected ? null : state.selectedChapter,
      }));
      
      // 如果删除的是当前章节且还有其他章节，自动选中第一个
      if (wasSelected && remaining.length > 0) {
        await get().selectChapter(remaining[0].id);
      }
    } catch (error) {
      console.error("Failed to delete chapter:", error);
      throw error;
    }
  },

  updateChapterContent: async (content: string) => {
    const { selectedId, selectedChapter } = get();
    if (!selectedId || !selectedChapter) return;

    // S75：手动改正文 → modified 信号（"改成这样更好"——心智提炼偏好的核心输入）
    const prev = selectedChapter.content;
    set({ saving: true });
    try {
      const updated = await patchChapter(selectedId, { content });
      set((state) => ({
        selectedChapter: updated,
        chapters: state.chapters.map((c) => (c.id === selectedId ? updated : c)),
        saving: false,
      }));
      if (prev !== content) {
        reportSignal("modified", prev, { newContent: content });
      }
    } catch (error) {
      console.error("Failed to save chapter:", error);
      set({ saving: false });
      throw error;
    }
  },
}));
