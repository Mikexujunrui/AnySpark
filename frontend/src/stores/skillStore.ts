import { create } from "zustand";
import {
  listSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  type Skill,
} from "../api/skills";

interface SkillState {
  skills: Skill[];
  loading: boolean;

  fetchSkills: () => Promise<void>;
  addSkill: (name: string, content: string, description?: string, target?: string) => Promise<void>;
  editSkill: (id: string, data: { name?: string; content?: string; description?: string; target?: string; enabled?: boolean }) => Promise<void>;
  removeSkill: (id: string) => Promise<void>;
}

export const useSkillStore = create<SkillState>((set) => ({
  skills: [],
  loading: false,

  fetchSkills: async () => {
    set({ loading: true });
    try {
      const skills = await listSkills();
      set({ skills, loading: false });
    } catch (error) {
      console.error("Failed to fetch skills:", error);
      set({ loading: false });
    }
  },

  addSkill: async (name, content, description, target) => {
    try {
      const skill = await createSkill(name, content, description, target);
      set((state) => ({ skills: [...state.skills, skill] }));
    } catch (error) {
      console.error("Failed to create skill:", error);
      throw error;
    }
  },

  editSkill: async (id, data) => {
    try {
      const updated = await updateSkill(id, data);
      set((state) => ({
        skills: state.skills.map((s) => (s.id === id ? updated : s)),
      }));
    } catch (error) {
      console.error("Failed to update skill:", error);
      throw error;
    }
  },

  removeSkill: async (id) => {
    try {
      await deleteSkill(id);
      set((state) => ({ skills: state.skills.filter((s) => s.id !== id) }));
    } catch (error) {
      console.error("Failed to delete skill:", error);
      throw error;
    }
  },
}));
