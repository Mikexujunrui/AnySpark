import { create } from "zustand";
import {
  exploreIntent,
  exploreCards,
  archiveDirection,
  listArchived,
  type IntentResult,
  type DirectionCard,
  type ArchivedDirection,
} from "../api/explore";

type ExplorePhase = "seed" | "intent" | "cards" | "archived";

interface ExploreState {
  phase: ExplorePhase;
  seed: string;
  intent: IntentResult | null;
  cards: DirectionCard[];
  archived: ArchivedDirection[];
  loading: boolean;
  error: string | null;

  setSeed: (seed: string) => void;
  submitSeed: () => Promise<void>;
  confirmIntent: () => Promise<void>;
  archiveCard: (card: DirectionCard) => Promise<void>;
  fetchArchived: () => Promise<void>;
  reset: () => void;
}

export const useExploreStore = create<ExploreState>((set, get) => ({
  phase: "seed",
  seed: "",
  intent: null,
  cards: [],
  archived: [],
  loading: false,
  error: null,

  setSeed: (seed: string) => set({ seed }),

  submitSeed: async () => {
    const { seed } = get();
    if (!seed.trim()) return;

    set({ loading: true, error: null });
    try {
      const intent = await exploreIntent(seed);
      set({ intent, phase: "intent", loading: false });
    } catch (error) {
      console.error("Failed to explore intent:", error);
      set({ loading: false, error: error instanceof Error ? error.message : "意图理解失败" });
    }
  },

  confirmIntent: async () => {
    const { seed, intent } = get();
    if (!intent) return;

    set({ loading: true, error: null });
    try {
      const cards = await exploreCards(seed, intent);
      set({ cards, phase: "cards", loading: false });
    } catch (error) {
      console.error("Failed to generate cards:", error);
      set({ loading: false, error: error instanceof Error ? error.message : "生成方向卡失败" });
    }
  },

  archiveCard: async (card: DirectionCard) => {
    set({ loading: true, error: null });
    try {
      const result = await archiveDirection(card);
      // 刷新已固化列表
      const archived = await listArchived();
      set({ archived, phase: "archived", loading: false, cards: [] });
    } catch (error) {
      console.error("Failed to archive direction:", error);
      set({ loading: false, error: error instanceof Error ? error.message : "固化失败" });
    }
  },

  fetchArchived: async () => {
    try {
      const archived = await listArchived();
      set({ archived });
    } catch (error) {
      console.error("Failed to fetch archived:", error);
    }
  },

  reset: () =>
    set({
      phase: "seed",
      seed: "",
      intent: null,
      cards: [],
      loading: false,
      error: null,
    }),
}));
