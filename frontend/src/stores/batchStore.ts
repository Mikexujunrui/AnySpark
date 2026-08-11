import { create } from "zustand";
import {
  batchRewrite,
  batchReview,
  getBatchStatus,
  type BatchResultItem,
  type BatchStatus,
} from "../api/batch";

interface BatchState {
  batchId: string | null;
  status: string;
  done: number;
  total: number;
  results: BatchResultItem[];
  loading: boolean;
  error: string;
  timer: number | null;

  startRewrite: (chapterIds: string[], instruction: string) => Promise<void>;
  startReview: (chapterIds: string[]) => Promise<void>;
  stopPolling: () => void;
  reset: () => void;
}

export const useBatchStore = create<BatchState>((set, get) => ({
  batchId: null,
  status: "",
  done: 0,
  total: 0,
  results: [],
  loading: false,
  error: "",
  timer: null,

  startRewrite: async (chapterIds, instruction) => {
    set({ loading: true, error: "", results: [], done: 0, total: 0, status: "" });
    try {
      const { batch_id, total } = await batchRewrite(chapterIds, instruction);
      set({ batchId: batch_id, total, status: "queued", loading: false });
      get().stopPolling();
      const timer = window.setInterval(async () => {
        try {
          const st: BatchStatus = await getBatchStatus(batch_id);
          set({
            status: st.status,
            done: st.done,
            total: st.total,
            results: st.results,
          });
          if (st.status === "done") {
            get().stopPolling();
          }
        } catch (error) {
          console.error("Failed to poll batch status:", error);
          set({ error: "轮询批量任务失败", loading: false });
          get().stopPolling();
        }
      }, 2000);
      set({ timer });
    } catch (error) {
      console.error("Failed to start batch rewrite:", error);
      set({ loading: false, error: "启动批量改写失败" });
    }
  },

  startReview: async (chapterIds) => {
    set({ loading: true, error: "", results: [], done: 0, total: 0, status: "" });
    try {
      const { batch_id, total } = await batchReview(chapterIds);
      set({ batchId: batch_id, total, status: "queued", loading: false });
      get().stopPolling();
      const timer = window.setInterval(async () => {
        try {
          const st: BatchStatus = await getBatchStatus(batch_id);
          set({
            status: st.status,
            done: st.done,
            total: st.total,
            results: st.results,
          });
          if (st.status === "done") {
            get().stopPolling();
          }
        } catch (error) {
          console.error("Failed to poll batch status:", error);
          set({ error: "轮询批量任务失败", loading: false });
          get().stopPolling();
        }
      }, 2000);
      set({ timer });
    } catch (error) {
      console.error("Failed to start batch review:", error);
      set({ loading: false, error: "启动批量审读失败" });
    }
  },

  stopPolling: () => {
    const { timer } = get();
    if (timer !== null) {
      window.clearInterval(timer);
      set({ timer: null });
    }
  },

  reset: () => {
    get().stopPolling();
    set({
      batchId: null,
      status: "",
      done: 0,
      total: 0,
      results: [],
      loading: false,
      error: "",
    });
  },
}));
