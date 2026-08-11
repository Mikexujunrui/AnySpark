import { create } from "zustand";
import { analyzeImpact, type ImpactHit } from "../api/impact";
import { listChapters } from "../api/chapters";
import type { Chapter } from "../types";

interface ImpactState {
  chapters: Chapter[];
  impacted: ImpactHit[];
  count: number;
  loading: boolean;
  error: string | null;

  fetchChapters: () => Promise<void>;
  analyze: (chapterOrder: number, entities?: string[]) => Promise<void>;
}

export const useImpactStore = create<ImpactState>((set) => ({
  chapters: [],
  impacted: [],
  count: 0,
  loading: false,
  error: null,

  fetchChapters: async () => {
    set({ loading: true, error: null });
    try {
      const chapters = await listChapters();
      set({ chapters, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  analyze: async (chapterOrder, entities) => {
    set({ loading: true, error: null });
    try {
      const result = await analyzeImpact(chapterOrder, entities);
      set({ impacted: result.impacted, count: result.count, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
