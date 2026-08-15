import { create } from "zustand";
import {
  saveRoleCard,
  rolePlay,
  type RolePlayCandidate,
  type RolePlayResult,
} from "../api/role";

interface RoleState {
  candidates: RolePlayCandidate[];
  best: RolePlayCandidate | null;
  scoreReason: string;
  loading: boolean;
  error: string;

  runPlay: (role: string, scenario: string, n?: number) => Promise<void>;
  saveCard: (name: string, content: string) => Promise<void>;
}

export const useRoleStore = create<RoleState>((set) => ({
  candidates: [],
  best: null,
  scoreReason: "",
  loading: false,
  error: "",

  runPlay: async (role, scenario, n) => {
    set({ loading: true, error: "" });
    try {
      const result: RolePlayResult = await rolePlay(role, scenario, n);
      set({
        candidates: result.candidates || [],
        best: result.best || null,
        scoreReason: result.score_reason || "",
        loading: false,
      });
    } catch (error) {
      console.error("Failed to run role play:", error);
      set({ loading: false, error: String(error) });
    }
  },

  saveCard: async (name, content) => {
    await saveRoleCard(name, content);
  },
}));
