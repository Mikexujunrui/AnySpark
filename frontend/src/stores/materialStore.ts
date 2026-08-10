import { create } from "zustand";
import { listMaterials, createMaterial, type Material, type MaterialCreate } from "../api/materials";

interface MaterialState {
  materials: Material[];
  loading: boolean;
  error: string | null;
  fetchAll: () => Promise<void>;
  add: (data: MaterialCreate) => Promise<void>;
}

export const useMaterialStore = create<MaterialState>((set, get) => ({
  materials: [],
  loading: false,
  error: null,

  fetchAll: async () => {
    set({ loading: true, error: null });
    try {
      const materials = await listMaterials();
      set({ materials, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  add: async (data) => {
    try {
      const card = await createMaterial(data);
      set({ materials: [...get().materials, card] });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },
}));
