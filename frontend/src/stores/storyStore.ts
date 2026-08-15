import { create } from "zustand";
import {
  getStoryTree,
  addStoryNode,
  chooseNode,
  anchorNode,
  deleteNode,
  addThread,
  type StoryNode,
  type StoryThread,
} from "../api/story";

// S152：叙事树按项目隔离——所有读写按 bookId 参数化（后端 story_nodes 已按 book_id 分库，
// 前端此前硬编码 "main" 导致所有项目共用一棵树）。
interface StoryState {
  nodes: StoryNode[];
  threads: StoryThread[];
  loading: boolean;
  selectedNodeId: string | null;

  fetchTree: (bookId: string) => Promise<void>;
  addNode: (content: string, bookId: string, parentId?: string) => Promise<void>;
  choose: (nodeId: string) => Promise<void>;
  anchor: (nodeId: string) => Promise<void>;
  removeNode: (nodeId: string) => Promise<void>;
  selectNode: (nodeId: string | null) => void;
  addNewThread: (name: string, bookId: string, content?: string, role?: StoryThread["role"]) => Promise<void>;
}

export const useStoryStore = create<StoryState>((set) => ({
  nodes: [],
  threads: [],
  loading: false,
  selectedNodeId: null,

  fetchTree: async (bookId) => {
    set({ loading: true });
    try {
      const tree = await getStoryTree(bookId);
      set({ nodes: tree.nodes, threads: tree.threads, loading: false });
    } catch (error) {
      console.error(`Failed to fetch story tree (${bookId}):`, error);
      set({ loading: false });
    }
  },

  addNode: async (content, bookId, parentId?) => {
    try {
      const node = await addStoryNode(content, bookId, parentId);
      set((state) => ({ nodes: [...state.nodes, node] }));
    } catch (error) {
      console.error("Failed to add story node:", error);
      throw error;
    }
  },

  choose: async (nodeId: string) => {
    try {
      await chooseNode(nodeId);
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

  removeNode: async (nodeId: string) => {
    try {
      await deleteNode(nodeId);
      set((state) => {
        // 删除节点及其所有后代
        const toDelete = new Set<string>([nodeId]);
        let changed = true;
        while (changed) {
          changed = false;
          for (const n of state.nodes) {
            if (n.parent_id && toDelete.has(n.parent_id) && !toDelete.has(n.id)) {
              toDelete.add(n.id);
              changed = true;
            }
          }
        }
        return {
          nodes: state.nodes.filter((n) => !toDelete.has(n.id)),
          selectedNodeId: state.selectedNodeId && toDelete.has(state.selectedNodeId) ? null : state.selectedNodeId,
        };
      });
    } catch (error) {
      console.error("Failed to remove node:", error);
      throw error;
    }
  },

  selectNode: (nodeId: string | null) => set({ selectedNodeId: nodeId }),

  addNewThread: async (name, bookId, content = "", role: StoryThread["role"] = "main") => {
    try {
      const thread = await addThread(name, bookId, content, "", role);
      set((state) => ({ threads: [...state.threads, thread] }));
    } catch (error) {
      console.error("Failed to add thread:", error);
      throw error;
    }
  },
}));
