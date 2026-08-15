import { apiGet, apiPost, apiDelete } from "./client";

/* ── 工作流定义（对齐后端 WorkflowNode/Edge/Def）── */

export type WorkflowNodeKind = "agent" | "script" | "approval" | "gate" | "loop";

export interface FailPolicy {
  auto_retry_count: number;
  auto_retry_interval_seconds: number;
  fail_auto_skip: boolean;
}

export interface WorkflowNode {
  id: string;
  kind: WorkflowNodeKind;
  label: string;
  params: Record<string, unknown>;
  fail: FailPolicy;
}

export interface Condition {
  type: "rule" | "model";
  expression?: string;
  prompt?: string;
  expect?: string;
  label?: string;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  condition?: Condition | null;
  label?: string;
}

export interface WorkflowDef {
  id: string;
  name: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  layout?: Record<string, { x: number; y: number }>; // S76 画布坐标
  created_at?: string;
}

export type TaskStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "done"
  | "failed"
  | "cancelled";

export interface WorkflowTask {
  id: string;
  template_id: string | null;
  name: string;
  book_id: string;
  status: TaskStatus;
  current_node_id: string | null;
  definition?: WorkflowDef;
  node_states?: Array<{
    task_id: string;
    node_id: string;
    status: string;
    attempts: number;
    output?: string;
    error?: string;
    token_usage?: number;
    updated_at: string;
  }>;
  results?: Record<string, string>;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  created_at?: string;
  builtin?: boolean; // S152：系统预置模板（不可删）
}

/* ── API ── */

export function listWorkflows(): Promise<WorkflowSummary[]> {
  return apiGet<WorkflowSummary[]>("/api/workflows");
}

export function getWorkflow(id: string): Promise<WorkflowDef> {
  return apiGet<WorkflowDef>(`/api/workflows/${id}`);
}

// S152：id 存在 = 原地更新（后端 add_template upsert），缺省 = 新建
// 注：函数名保留 createWorkflow（兼容历史调用），语义为“写入模板”
export function createWorkflow(
  name: string,
  description: string,
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
  layout?: Record<string, { x: number; y: number }>,
  id?: string
): Promise<WorkflowDef> {
  return apiPost<WorkflowDef>("/api/workflows", {
    id: id ?? "",
    name,
    description,
    nodes,
    edges,
    layout: layout ?? {},
  });
}

export function deleteWorkflow(id: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/api/workflows/${id}`);
}

export function generateWorkflow(goal: string): Promise<WorkflowDef> {
  return apiPost<WorkflowDef>("/api/workflows/generate", { goal });
}

export function listWorkflowDrafts(): Promise<WorkflowSummary[]> {
  return apiGet<WorkflowSummary[]>("/api/workflows/drafts");
}

export function promoteDraft(draftId: string): Promise<WorkflowDef> {
  return apiPost<WorkflowDef>(`/api/workflows/drafts/${draftId}/promote`, {});
}

export function deleteDraft(draftId: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/api/workflows/drafts/${draftId}`);
}

export function runWorkflow(
  id: string,
  bookId = "main",
  params?: Record<string, string>
): Promise<{ task_id: string; status: string }> {
  return apiPost<{ task_id: string; status: string }>(`/api/workflows/${id}/run`, {
    book_id: bookId,
    ...(params && Object.keys(params).length ? { params } : {}),
  });
}

export function listWorkflowTasks(): Promise<WorkflowTask[]> {
  return apiGet<WorkflowTask[]>("/api/workflows/tasks");
}

export function getWorkflowTask(taskId: string): Promise<WorkflowTask> {
  return apiGet<WorkflowTask>(`/api/workflows/tasks/${taskId}`);
}

export function approveTask(
  taskId: string,
  decision: "ok" | "reject"
): Promise<WorkflowTask> {
  return apiPost<WorkflowTask>(`/api/workflows/tasks/${taskId}/approve`, { decision });
}

// S152k：用户取消任务（任务级 stop，不影响并行任务；cancelled 后可 resume 续跑）
export function cancelTask(
  taskId: string
): Promise<{ task_id: string; status: string; note?: string }> {
  return apiPost<{ task_id: string; status: string; note?: string }>(
    `/api/workflows/tasks/${taskId}/cancel`,
    {}
  );
}
