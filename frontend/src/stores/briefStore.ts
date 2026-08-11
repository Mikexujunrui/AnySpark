import { create } from "zustand";
import { getBrief, saveBrief, generateBrief } from "../api/brief";

interface BriefState {
  content: string;
  exists: boolean;
  loading: boolean;
  draft: string;
  note: string;
  generating: boolean;

  fetchBrief: () => Promise<void>;
  save: (content: string) => Promise<void>;
  generate: () => Promise<void>;
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

  fetchBrief: async () => {
    set({ loading: true });
    try {
      const brief = await getBrief();
      set({ content: brief.content, exists: brief.exists, loading: false });
    } catch (error) {
      console.error("Failed to fetch brief:", error);
      set({ loading: false });
    }
  },

  save: async (content) => {
    try {
      const saved = await saveBrief(content);
      set({ content: saved.content, exists: true, draft: "", note: "" });
    } catch (error) {
      console.error("Failed to save brief:", error);
      throw error;
    }
  },

  generate: async () => {
    set({ generating: true, note: "" });
    try {
      const result = await generateBrief();
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
