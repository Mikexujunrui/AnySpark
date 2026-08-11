import { create } from "zustand";
import {
  listWorkflows,
  getWorkflow,
  createWorkflow,
  deleteWorkflow,
  generateWorkflow,
  listWorkflowDrafts,
  promoteDraft,
  deleteDraft,
  runWorkflow,
  listWorkflowTasks,
  getWorkflowTask,
  approveTask,
  type WorkflowDef,
  type WorkflowSummary,
  type WorkflowTask,
} from "../api/workflow";

interface WorkflowState {
  templates: WorkflowSummary[];
  drafts: WorkflowSummary[];
  tasks: WorkflowTask[];
  current: WorkflowDef | null;
  loading: boolean;
  error: string | null;

  fetchAll: () => Promise<void>;
  openWorkflow: (id: string) => Promise<WorkflowDef>;
  saveWorkflow: (wf: WorkflowDef) => Promise<void>;
  removeWorkflow: (id: string) => Promise<void>;
  aiGenerate: (goal: string) => Promise<void>;
  promote: (draftId: string) => Promise<void>;
  discardDraft: (draftId: string) => Promise<void>;
  startRun: (id: string) => Promise<string>;
  refreshTask: (taskId: string) => Promise<WorkflowTask>;
  decide: (taskId: string, decision: "ok" | "reject") => Promise<void>;
  setError: (msg: string | null) => void;
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  templates: [],
  drafts: [],
  tasks: [],
  current: null,
  loading: false,
  error: null,

  fetchAll: async () => {
    set({ loading: true, error: null });
    try {
      const [templates, drafts, tasks] = await Promise.all([
        listWorkflows(),
        listWorkflowDrafts(),
        listWorkflowTasks(),
      ]);
      set({ templates, drafts, tasks, loading: false });
    } catch (e) {
      console.error("Failed to fetch workflows:", e);
      set({ loading: false, error: e instanceof Error ? e.message : "加载工作流失败" });
    }
  },

  openWorkflow: async (id): Promise<WorkflowDef> => {
    set({ loading: true, error: null });
    try {
      const wf = await getWorkflow(id);
      set({ current: wf, loading: false });
      return wf;
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "加载工作流失败" });
      throw e;
    }
  },

  saveWorkflow: async (wf) => {
    set({ loading: true, error: null });
    try {
      const saved = await createWorkflow(wf.name, wf.description, wf.nodes, wf.edges);
      const templates = [...get().templates.filter((t) => t.id !== saved.id), saved];
      set({ templates, current: saved, loading: false });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "保存失败" });
      throw e;
    }
  },

  removeWorkflow: async (id) => {
    try {
      await deleteWorkflow(id);
      set((s) => ({
        templates: s.templates.filter((t) => t.id !== id),
        current: s.current?.id === id ? null : s.current,
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "删除失败" });
      throw e;
    }
  },

  aiGenerate: async (goal) => {
    set({ loading: true, error: null });
    try {
      const wf = await generateWorkflow(goal);
      set((s) => ({ drafts: [wf, ...s.drafts], loading: false }));
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "生成失败" });
      throw e;
    }
  },

  promote: async (draftId) => {
    try {
      const wf = await promoteDraft(draftId);
      // 转正后：完整定义载入画布，列表从后端刷新
      set({ current: wf, drafts: get().drafts.filter((d) => d.id !== draftId) });
      await get().fetchAll();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "转正失败" });
      throw e;
    }
  },

  discardDraft: async (draftId) => {
    try {
      await deleteDraft(draftId);
      set((s) => ({ drafts: s.drafts.filter((d) => d.id !== draftId) }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "删除草稿失败" });
      throw e;
    }
  },

  startRun: async (id) => {
    try {
      const res = await runWorkflow(id);
      return res.task_id;
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "启动失败" });
      throw e;
    }
  },

  refreshTask: async (taskId) => {
    const task = await getWorkflowTask(taskId);
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === taskId ? task : t)),
    }));
    return task;
  },

  decide: async (taskId, decision) => {
    try {
      const task = await approveTask(taskId, decision);
      set((s) => ({
        tasks: s.tasks.map((t) => (t.id === taskId ? task : t)),
      }));
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "审批失败" });
      throw e;
    }
  },

  setError: (msg) => set({ error: msg }),
}));
