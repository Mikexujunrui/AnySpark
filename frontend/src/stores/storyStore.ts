import { create } from "zustand";
import {
  getStoryTree,
  addStoryNode,
  chooseNode,
  anchorNode,
  addThread,
  type StoryNode,
  type StoryThread,
} from "../api/story";

interface StoryState {
  nodes: StoryNode[];
  threads: StoryThread[];
  loading: boolean;
  selectedNodeId: string | null;

  fetchTree: () => Promise<void>;
  addNode: (content: string, parentId?: string) => Promise<void>;
  choose: (nodeId: string) => Promise<void>;
  anchor: (nodeId: string) => Promise<void>;
  selectNode: (nodeId: string | null) => void;
  addNewThread: (name: string, content?: string, role?: StoryThread["role"]) => Promise<void>;
}

export const useStoryStore = create<StoryState>((set, get) => ({
  nodes: [],
  threads: [],
  loading: false,
  selectedNodeId: null,

  fetchTree: async () => {
    set({ loading: true });
    try {
      const tree = await getStoryTree();
      set({ nodes: tree.nodes, threads: tree.threads, loading: false });
    } catch (error) {
      console.error("Failed to fetch story tree:", error);
      set({ loading: false });
    }
  },

  addNode: async (content: string, parentId?: string) => {
    try {
      const node = await addStoryNode(content, "main", parentId);
      set((state) => ({ nodes: [...state.nodes, node] }));
    } catch (error) {
      console.error("Failed to add story node:", error);
      throw error;
    }
  },

  choose: async (nodeId: string) => {
    try {
      const updated = await chooseNode(nodeId);
      set((state) => ({
        // 选择节点时，其他节点的 chosen 会被清除
        nodes: state.nodes.map((n) => ({
          ...n,
          chosen: n.id === nodeId ? true : false,
          kind: n.id === nodeId ? "main" : n.kind,
        })),
      }));
    } catch (error) {
      console.error("Failed to choose node:", error);
      throw error;
    }
  },

  anchor: async (nodeId: string) => {
    try {
      await anchorNode(nodeId);
      set((state) => ({
        nodes: state.nodes.map((n) =>
          n.id === nodeId ? { ...n, kind: "anchor" as const } : n
        ),
      }));
    } catch (error) {
      console.error("Failed to anchor node:", error);
      throw error;
    }
  },

  selectNode: (nodeId: string | null) => set({ selectedNodeId: nodeId }),

  addNewThread: async (name: string, content = "", role: StoryThread["role"] = "main") => {
    try {
      const thread = await addThread(name, "main", content, "", role);
      set((state) => ({ threads: [...state.threads, thread] }));
    } catch (error) {
      console.error("Failed to add thread:", error);
      throw error;
    }
  },
}));
