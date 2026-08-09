import { create } from "zustand";
import {
  listManual,
  createManual,
  updateManual,
  deleteManual,
  type ManualEntry,
} from "../api/manual";

type Category = "collab" | "style" | "habit";

interface ManualState {
  entries: ManualEntry[];
  loading: boolean;
  filter: Category | "all";

  fetchEntries: () => Promise<void>;
  addEntry: (content: string, category: Category) => Promise<void>;
  editEntry: (id: string, data: { content?: string; locked?: boolean; category?: Category }) => Promise<void>;
  removeEntry: (id: string) => Promise<void>;
  setFilter: (f: Category | "all") => void;
}

export const useManualStore = create<ManualState>((set, get) => ({
  entries: [],
  loading: false,
  filter: "all",

  fetchEntries: async () => {
    set({ loading: true });
    try {
      const entries = await listManual();
      set({ entries, loading: false });
    } catch (error) {
      console.error("Failed to fetch manual entries:", error);
      set({ loading: false });
    }
  },

  addEntry: async (content, category) => {
    try {
      const entry = await createManual(content, category);
      set((state) => ({ entries: [...state.entries, entry] }));
    } catch (error) {
      console.error("Failed to create entry:", error);
      throw error;
    }
  },

  editEntry: async (id, data) => {
    try {
      const updated = await updateManual(id, data);
      set((state) => ({
        entries: state.entries.map((e) => (e.id === id ? updated : e)),
      }));
    } catch (error) {
      console.error("Failed to update entry:", error);
      throw error;
    }
  },

  removeEntry: async (id) => {
    try {
      await deleteManual(id);
      set((state) => ({ entries: state.entries.filter((e) => e.id !== id) }));
    } catch (error) {
      console.error("Failed to delete entry:", error);
      throw error;
    }
  },

  setFilter: (f) => set({ filter: f }),
}));
