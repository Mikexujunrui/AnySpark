import { create } from "zustand";
import {
  listTools,
  registerTool,
  approveTool,
  disableTool,
  deleteTool,
  type ExtTool,
} from "../api/tools";

interface ToolState {
  tools: ExtTool[];
  loading: boolean;

  fetchTools: () => Promise<void>;
  addTool: (name: string, description: string, paramsJson: string, code: string) => Promise<void>;
  approve: (id: string) => Promise<void>;
  disable: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useToolStore = create<ToolState>((set) => ({
  tools: [],
  loading: false,

  fetchTools: async () => {
    set({ loading: true });
    try {
      const tools = await listTools();
      set({ tools, loading: false });
    } catch (error) {
      console.error("Failed to fetch tools:", error);
      set({ loading: false });
    }
  },

  addTool: async (name, description, paramsJson, code) => {
    try {
      await registerTool(name, description, paramsJson, code);
      await useToolStore.getState().fetchTools();
    } catch (error) {
      console.error("Failed to register tool:", error);
      throw error;
    }
  },

  approve: async (id) => {
    try {
      await approveTool(id);
      set((state) => ({
        tools: state.tools.map((t) => (t.id === id ? { ...t, status: "active" } : t)),
      }));
    } catch (error) {
      console.error("Failed to approve tool:", error);
      throw error;
    }
  },

  disable: async (id) => {
    try {
      await disableTool(id);
      set((state) => ({
        tools: state.tools.map((t) => (t.id === id ? { ...t, status: "draft" } : t)),
      }));
    } catch (error) {
      console.error("Failed to disable tool:", error);
      throw error;
    }
  },

  remove: async (id) => {
    try {
      await deleteTool(id);
      set((state) => ({ tools: state.tools.filter((t) => t.id !== id) }));
    } catch (error) {
      console.error("Failed to delete tool:", error);
      throw error;
    }
  },
}));
