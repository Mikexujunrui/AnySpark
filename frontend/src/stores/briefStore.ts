import { create } from "zustand";
import { getBrief, saveBrief, generateBrief } from "../api/brief";

interface BriefState {
  content: string;
  exists: boolean;
  loading: boolean;
  draft: string;
  note: string;
  generating: boolean;

  fetchBrief: (bookId: string) => Promise<void>;
  save: (bookId: string, content: string) => Promise<void>;
  generate: (bookId: string) => Promise<void>;
  setDraft: (draft: string) => void;
  clearDraft: () => void;
}

export const useBriefStore = create<BriefState>((set) => ({
  content: "",
  exists: false,
  loading: false,
  draft: "",
  note: "",
  generating: false,

  // S101：按 book_id 隔离（此前硬编码 main 跨项目共享）
  fetchBrief: async (bookId) => {
    set({ loading: true });
    try {
      const brief = await getBrief(bookId);
      set({ content: brief.content, exists: brief.exists, loading: false });
    } catch (error) {
      console.error("Failed to fetch brief:", error);
      set({ loading: false });
    }
  },

  save: async (bookId, content) => {
    try {
      const saved = await saveBrief(bookId, content);
      set({ content: saved.content, exists: saved.exists, draft: "", note: "" });
    } catch (error) {
      console.error("Failed to save brief:", error);
      throw error;
    }
  },

  generate: async (bookId) => {
    set({ generating: true, note: "" });
    try {
      const result = await generateBrief(bookId);
      set({
        draft: result.draft,
        note: result.note,
        generating: false,
      });
    } catch (error) {
      console.error("Failed to generate brief:", error);
      set({ generating: false, note: "生成失败（网络/服务错误）" });
    }
  },

  setDraft: (draft) => set({ draft }),
  clearDraft: () => set({ draft: "", note: "" }),
}));
