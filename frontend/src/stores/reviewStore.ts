import { create } from "zustand";
import {
  listReviewers,
  runReviewPanel,
  type ReviewerDef,
  type ReviewReport,
} from "../api/review";

interface ReviewState {
  reviewers: ReviewerDef[];
  result: ReviewReport | null;
  loading: boolean;
  error: string;

  fetchReviewers: () => Promise<void>;
  runReview: (body: {
    chapter_ref?: string;
    text?: string;
    reviewer_ids?: string[];
    with_check?: boolean;
    with_foreshadow?: boolean;
  }) => Promise<void>;
}

export const useReviewStore = create<ReviewState>((set) => ({
  reviewers: [],
  result: null,
  loading: false,
  error: "",

  fetchReviewers: async () => {
    try {
      const reviewers = await listReviewers();
      set({ reviewers });
    } catch (error) {
      console.error("Failed to fetch reviewers:", error);
      set({ error: String(error) });
    }
  },

  runReview: async (body) => {
    set({ loading: true, error: "" });
    try {
      const result = await runReviewPanel(body);
      set({ result, loading: false });
    } catch (error) {
      console.error("Failed to run review panel:", error);
      set({ loading: false, error: String(error) });
    }
  },
}));
