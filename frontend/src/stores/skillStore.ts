import { create } from "zustand";
import {
  listSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  listSkillDrafts,
  promoteSkillDraft,
  deleteSkillDraft,
  type Skill,
  type SkillDraft,
} from "../api/skills";

interface SkillState {
  skills: Skill[];
  drafts: SkillDraft[];
  loading: boolean;

  fetchSkills: () => Promise<void>;
  fetchDrafts: () => Promise<void>;
  addSkill: (name: string, content: string, description?: string, target?: string) => Promise<void>;
  editSkill: (id: string, data: { name?: string; content?: string; description?: string; target?: string; enabled?: boolean }) => Promise<void>;
  removeSkill: (id: string) => Promise<void>;
  // S104：草稿确认闸门（AI 生成候选 → 人工采纳/拒绝）
  approveDraft: (draftId: string) => Promise<void>;
  rejectDraft: (draftId: string) => Promise<void>;
}

export const useSkillStore = create<SkillState>((set, get) => ({
  skills: [],
  drafts: [],
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

  // S104：加载草稿（AI 生成候选待确认）
  fetchDrafts: async () => {
    try {
      const drafts = await listSkillDrafts();
      set({ drafts });
    } catch (error) {
      console.error("Failed to fetch skill drafts:", error);
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

  // S104：采纳草稿 → 转正入技能表
  approveDraft: async (draftId) => {
    try {
      const skill = await promoteSkillDraft(draftId);
      set((state) => ({
        drafts: state.drafts.filter((d) => d.id !== draftId),
        skills: [...state.skills, skill],
      }));
    } catch (error) {
      console.error("Failed to approve skill draft:", error);
      throw error;
    }
  },

  // S104：拒绝草稿 → 删除
  rejectDraft: async (draftId) => {
    try {
      await deleteSkillDraft(draftId);
      set((state) => ({ drafts: state.drafts.filter((d) => d.id !== draftId) }));
    } catch (error) {
      console.error("Failed to reject skill draft:", error);
      throw error;
    }
  },
}));
