import { create } from "zustand";

export type DisplayMode = "paper" | "tree" | "skills" | "check" | "explore" | "plot" | "plan";

interface DisplayState {
  mode: DisplayMode;
  setMode: (mode: DisplayMode) => void;
}

export const useDisplayStore = create<DisplayState>((set) => ({
  mode: "paper",
  setMode: (mode) => set({ mode }),
}));
