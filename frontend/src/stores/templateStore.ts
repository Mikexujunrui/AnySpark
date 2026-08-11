import { create } from "zustand";
import {
  listTemplates,
  importTemplate,
  deleteTemplate,
  generateTemplates,
  type TemplateItem,
  type TemplateInput,
} from "../api/templates";

interface TemplateState {
  templates: TemplateItem[];
  loading: boolean;

  fetchTemplates: () => Promise<void>;
  addTemplate: (data: TemplateInput) => Promise<void>;
  removeTemplate: (name: string) => Promise<void>;
  generateFromText: (
    sourceText: string,
    hint?: string,
    maxItems?: number
  ) => Promise<TemplateItem[]>;
}

export const useTemplateStore = create<TemplateState>((set) => ({
  templates: [],
  loading: false,

  fetchTemplates: async () => {
    set({ loading: true });
    try {
      const templates = await listTemplates();
      set({ templates, loading: false });
    } catch (error) {
      console.error("Failed to fetch templates:", error);
      set({ loading: false });
    }
  },

  addTemplate: async (data) => {
    try {
      const t = await importTemplate(data);
      set((state) => ({ templates: [...state.templates, t] }));
    } catch (error) {
      console.error("Failed to import template:", error);
      throw error;
    }
  },

  removeTemplate: async (name) => {
    try {
      await deleteTemplate(name);
      set((state) => ({
        templates: state.templates.filter((t) => t.name !== name),
      }));
    } catch (error) {
      console.error("Failed to delete template:", error);
      throw error;
    }
  },

  generateFromText: async (sourceText, hint, maxItems) => {
    try {
      const res = await generateTemplates(sourceText, hint, maxItems);
      return res.candidates;
    } catch (error) {
      console.error("Failed to generate templates:", error);
      throw error;
    }
  },
}));
