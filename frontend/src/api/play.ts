import { apiGet, apiPost } from "./client";

// S65 互动推演：扮演角色多轮选择推进的推演树

// 推演会话（列表项 / session dict）
export interface PlaySession {
  id: string;
  book_id: string;
  title: string;
  role: string;
  status: string;
  max_depth: number;
  current_node_id: string;
  created_at: string;
  updated_at: string;
}

// 候选行动
export interface PlayOption {
  id: string;
  label: string;
  is_custom: boolean;
}

// 推演节点视图（scene + 候选行动）
export interface PlayNode {
  id: string;
  depth: number;
  scene: string;
  chosen_label: string;
  options: PlayOption[];
}

// 会话树
export interface PlayTree {
  nodes: Array<Record<string, unknown>>;
  options: Array<Record<string, unknown>>;
}

// 路径（根 → 当前节点，每步 node + 选择 label）
export interface PlayPathEntry {
  node: Record<string, unknown>;
  chosen_label: string;
}

export interface PlayCreateResult {
  session: PlaySession;
  node: PlayNode;
  ended: boolean;
}

export interface PlayChooseResult {
  node: PlayNode;
  ended: boolean;
}

export interface PlayGetResult {
  session: PlaySession;
  tree: PlayTree;
  path: PlayPathEntry[];
}

export interface PlayExportResult {
  session_id: string;
  markdown: string;
}

// 列出全部推演会话
export function listPlaySessions(): Promise<PlaySession[]> {
  return apiGet<PlaySession[]>("/api/play/sessions");
}

// 创建推演会话
export function createPlaySession(
  role: string,
  seed: string,
  title = "",
  maxDepth = 20
): Promise<PlayCreateResult> {
  return apiPost<PlayCreateResult>("/api/play/sessions", {
    role,
    seed,
    book_id: "main",
    title,
    max_depth: maxDepth,
  });
}

// 获取会话（session + tree + path）
export function getPlaySession(id: string): Promise<PlayGetResult> {
  return apiGet<PlayGetResult>(`/api/play/sessions/${id}`);
}

// 选择候选行动（或自定义输入）
export function playChoose(
  id: string,
  optionId?: string,
  customText?: string
): Promise<PlayChooseResult> {
  return apiPost<PlayChooseResult>(`/api/play/sessions/${id}/choose`, {
    option_id: optionId || "",
    custom_text: customText || "",
  });
}

// 回溯分叉：回到指定节点重新生成候选
export function playBranch(id: string, nodeId: string): Promise<PlayChooseResult> {
  return apiPost<PlayChooseResult>(`/api/play/sessions/${id}/branch`, {
    node_id: nodeId,
  });
}

// 终止会话
export function playStop(id: string): Promise<{ ok: boolean; session_id: string; status: string }> {
  return apiPost<{ ok: boolean; session_id: string; status: string }>(
    `/api/play/sessions/${id}/stop`,
    {}
  );
}

// 导出灵感卡 md
export function playExport(id: string): Promise<PlayExportResult> {
  return apiGet<PlayExportResult>(`/api/play/sessions/${id}/export`);
}
