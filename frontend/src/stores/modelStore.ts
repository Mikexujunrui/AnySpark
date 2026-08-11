import { create } from "zustand";
import { listModels, activateModel, type ModelConfig } from "../api/models";

interface ModelState {
  models: ModelConfig[];
  activeModel: ModelConfig | null;
  loading: boolean;

  fetchModels: () => Promise<void>;
  switchModel: (id: string) => Promise<void>;
}

export const useModelStore = create<ModelState>((set, get) => ({
  models: [],
  activeModel: null,
  loading: false,

  fetchModels: async () => {
    set({ loading: true });
    try {
      const models = await listModels();
      const active = models.find((m) => m.is_active) || null;
      set({ models, activeModel: active, loading: false });
    } catch (error) {
      console.error("Failed to fetch models:", error);
      set({ loading: false });
    }
  },

  switchModel: async (id: string) => {
    try {
      await activateModel(id);
      // 重新获取列表以更新状态
      await get().fetchModels();
    } catch (error) {
      console.error("Failed to switch model:", error);
      throw error;
    }
  },
}));
