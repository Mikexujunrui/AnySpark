import { create } from "zustand";
import { listBias, addBias, deleteBias, type BiasEntry } from "../api/bias";

interface BiasState {
  items: BiasEntry[];
  loading: boolean;

  fetchBias: () => Promise<void>;
  add: (content: string, source: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useBiasStore = create<BiasState>((set) => ({
  items: [],
  loading: false,

  fetchBias: async () => {
    set({ loading: true });
    try {
      const items = await listBias();
      set({ items, loading: false });
    } catch (error) {
      console.error("Failed to fetch bias:", error);
      set({ loading: false });
    }
  },

  add: async (content, source) => {
    try {
      const entry = await addBias(content, source);
      set((state) => ({ items: [entry, ...state.items] }));
    } catch (error) {
      console.error("Failed to add bias:", error);
      throw error;
    }
  },

  remove: async (id) => {
    try {
      await deleteBias(id);
      set((state) => ({ items: state.items.filter((e) => e.id !== id) }));
    } catch (error) {
      console.error("Failed to delete bias:", error);
      throw error;
    }
  },
}));
