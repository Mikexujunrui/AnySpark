import { create } from "zustand";
import {
  listSettingCategories,
  addSettingCategory,
  deleteSettingCategory,
  listSettings,
  addSetting,
  patchSetting,
  deleteSetting,
  getUncensored,
  setUncensored,
  type SettingCategory,
  type WorldSetting,
  type UncensoredConfig,
} from "../api/settings";

interface SettingsState {
  categories: SettingCategory[];
  settings: WorldSetting[];
  uncensored: UncensoredConfig;
  loading: boolean;

  fetchAll: () => Promise<void>;
  addCategory: (name: string, description?: string) => Promise<void>;
  removeCategory: (id: string) => Promise<void>;
  addSetting: (category: string, name: string, content: string) => Promise<void>;
  updateSetting: (id: string, data: Partial<{ name: string; content: string }>) => Promise<void>;
  removeSetting: (id: string) => Promise<void>;
  toggleUncensored: (enabled: boolean, level?: string) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  categories: [],
  settings: [],
  uncensored: { enabled: false, level: "standard" },
  loading: false,

  fetchAll: async () => {
    set({ loading: true });
    try {
      const [categories, settings, uncensored] = await Promise.all([
        listSettingCategories(),
        listSettings(),
        getUncensored(),
      ]);
      set({ categories, settings, uncensored, loading: false });
    } catch (error) {
      console.error("Failed to fetch settings:", error);
      set({ loading: false });
    }
  },

  addCategory: async (name: string, description: string = "") => {
    try {
      const newCat = await addSettingCategory(name, description);
      set({ categories: [...get().categories, newCat] });
    } catch (error) {
      console.error("Failed to add category:", error);
      throw error;
    }
  },

  removeCategory: async (id: string) => {
    try {
      await deleteSettingCategory(id);
      set({ categories: get().categories.filter((c) => c.id !== id) });
    } catch (error) {
      console.error("Failed to delete category:", error);
      throw error;
    }
  },

  addSetting: async (category: string, name: string, content: string) => {
    try {
      const newSetting = await addSetting(category, name, content);
      set({ settings: [...get().settings, newSetting] });
    } catch (error) {
      console.error("Failed to add setting:", error);
      throw error;
    }
  },

  updateSetting: async (id: string, data: Partial<{ name: string; content: string }>) => {
    try {
      const updated = await patchSetting(id, data);
      set({ settings: get().settings.map((s) => (s.id === id ? updated : s)) });
    } catch (error) {
      console.error("Failed to update setting:", error);
      throw error;
    }
  },

  removeSetting: async (id: string) => {
    try {
      await deleteSetting(id);
      set({ settings: get().settings.filter((s) => s.id !== id) });
    } catch (error) {
      console.error("Failed to delete setting:", error);
      throw error;
    }
  },

  toggleUncensored: async (enabled: boolean, level: string = "standard") => {
    try {
      const updated = await setUncensored(enabled, level);
      set({ uncensored: updated });
    } catch (error) {
      console.error("Failed to toggle uncensored:", error);
      throw error;
    }
  },
}));
