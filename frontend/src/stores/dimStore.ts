import { create } from "zustand";
import {
  listDims,
  addDim,
  setDimEnabled,
  deleteDim,
  type ExploreDim,
} from "../api/dims";

interface DimState {
  dims: ExploreDim[];
  loading: boolean;
  error: string;

  fetchDims: () => Promise<void>;
  add: (name: string) => Promise<void>;
  toggle: (id: string, enabled: boolean) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useDimStore = create<DimState>((set) => ({
  dims: [],
  loading: false,
  error: "",

  fetchDims: async () => {
    set({ loading: true, error: "" });
    try {
      const dims = await listDims();
      set({ dims, loading: false });
    } catch (error) {
      console.error("Failed to fetch dims:", error);
      set({ loading: false, error: String(error) });
    }
  },

  add: async (name) => {
    try {
      const dim = await addDim(name);
      set((state) => ({ dims: [...state.dims, dim] }));
    } catch (error) {
      console.error("Failed to add dim:", error);
      throw error;
    }
  },

  toggle: async (id, enabled) => {
    try {
      const dim = await setDimEnabled(id, enabled);
      set((state) => ({
        dims: state.dims.map((d) => (d.id === id ? dim : d)),
      }));
    } catch (error) {
      console.error("Failed to toggle dim:", error);
      throw error;
    }
  },

  remove: async (id) => {
    try {
      await deleteDim(id);
      set((state) => ({ dims: state.dims.filter((d) => d.id !== id) }));
    } catch (error) {
      console.error("Failed to delete dim:", error);
      throw error;
    }
  },
}));
