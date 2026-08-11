import { create } from "zustand";
import {
  listPlaySessions,
  createPlaySession,
  getPlaySession,
  playChoose,
  playBranch,
  playStop,
  type PlaySession,
  type PlayNode,
  type PlayTree,
  type PlayPathEntry,
} from "../api/play";

interface PlayState {
  sessions: PlaySession[];
  session: PlaySession | null;
  node: PlayNode | null;
  tree: PlayTree | null;
  path: PlayPathEntry[];
  loading: boolean;

  listSessions: () => Promise<void>;
  create: (role: string, seed: string, title?: string, maxDepth?: number) => Promise<PlaySession>;
  get: (id: string) => Promise<void>;
  choose: (optionId?: string, customText?: string) => Promise<void>;
  branch: (nodeId: string) => Promise<void>;
  stop: (id: string) => Promise<void>;
}

// 从树里提取当前节点的候选行动（options）
function nodeOptionsFromTree(
  nodeId: string | undefined,
  tree: PlayTree | null
): PlayNode["options"] {
  if (!nodeId || !tree) return [];
  return tree.options
    .filter((o) => o.node_id === nodeId)
    .map((o) => ({
      id: String(o.id),
      label: String(o.label ?? ""),
      is_custom: Boolean(o.is_custom),
    }));
}

export const usePlayStore = create<PlayState>((set, get) => ({
  sessions: [],
  session: null,
  node: null,
  tree: null,
  path: [],
  loading: false,

  listSessions: async () => {
    set({ loading: true });
    try {
      const sessions = await listPlaySessions();
      set({ sessions, loading: false });
    } catch (error) {
      console.error("Failed to list play sessions:", error);
      set({ loading: false });
    }
  },

  create: async (role, seed, title, maxDepth) => {
    const result = await createPlaySession(role, seed, title, maxDepth);
    set({ session: result.session, node: result.node, tree: null, path: [] });
    await get().get(result.session.id);
    await get().listSessions();
    return result.session;
  },

  get: async (id) => {
    set({ loading: true });
    try {
      const result = await getPlaySession(id);
      set({
        session: result.session,
        tree: result.tree,
        path: result.path,
        loading: false,
      });
      const currentId = result.session.current_node_id || "";
      const nodeEntry = result.path.find((p) => String(p.node.id) === currentId);
      if (nodeEntry) {
        set({
          node: {
            id: String(nodeEntry.node.id),
            depth: Number(nodeEntry.node.depth ?? 0),
            scene: String(nodeEntry.node.scene ?? ""),
            chosen_label: String(nodeEntry.node.chosen_label ?? ""),
            options: nodeOptionsFromTree(currentId, result.tree),
          },
        });
      } else {
        // 当前节点不在路径（数据异常兜底）：取路径最后一步
        const last = result.path[result.path.length - 1];
        if (last) {
          set({
            node: {
              id: String(last.node.id),
              depth: Number(last.node.depth ?? 0),
              scene: String(last.node.scene ?? ""),
              chosen_label: String(last.node.chosen_label ?? ""),
              options: nodeOptionsFromTree(String(last.node.id), result.tree),
            },
          });
        } else {
          set({ node: null });
        }
      }
    } catch (error) {
      console.error("Failed to get play session:", error);
      set({ loading: false });
    }
  },

  choose: async (optionId, customText) => {
    const { session } = get();
    if (!session) return;
    const result = await playChoose(session.id, optionId, customText);
    set({ node: result.node });
    await get().get(session.id);
  },

  branch: async (nodeId) => {
    const { session } = get();
    if (!session) return;
    const result = await playBranch(session.id, nodeId);
    set({ node: result.node });
    await get().get(session.id);
  },

  stop: async (id) => {
    try {
      await playStop(id);
      set((state) => ({
        sessions: state.sessions.map((s) => (s.id === id ? { ...s, status: "ended" } : s)),
        session: state.session?.id === id ? { ...state.session, status: "ended" } : state.session,
      }));
    } catch (error) {
      console.error("Failed to stop play session:", error);
      throw error;
    }
  },
}));
