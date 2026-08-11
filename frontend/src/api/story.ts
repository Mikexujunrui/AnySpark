import { apiGet, apiPost, apiDelete, apiFetch } from "./client";

// 叙事树节点
export interface StoryNode {
  id: string;
  book_id: string;
  content: string;
  parent_id: string | null;
  kind: "root" | "main" | "anchor" | "candidate" | "subplot" | "loop";
  chosen: boolean;
  created_at: string;
  pos?: { x: number; y: number } | null; // S76 画布手动坐标（null=自动布局）
}

// 叙事线进度
export interface StoryThread {
  id: string;
  name: string;
  book_id: string;
  content: string;
  progress: string;
  role: "main" | "subplot" | "parallel";
  node_id: string | null;
  status: "active" | "done";
  created_at: string;
}

// 树视图（完整数据）
export interface StoryTree {
  nodes: StoryNode[];
  threads: StoryThread[];
  render: string;
  thread_render: string;
}

// 获取叙事节点列表
export function listStoryNodes(bookId = "main"): Promise<StoryNode[]> {
  return apiGet<StoryNode[]>(`/api/story/nodes?book_id=${bookId}`);
}

// 获取完整叙事树
export function getStoryTree(bookId = "main"): Promise<StoryTree> {
  return apiGet<StoryTree>(`/api/story/tree?book_id=${bookId}`);
}

// 添加叙事节点
export function addStoryNode(
  content: string,
  bookId = "main",
  parentId?: string,
  kind: StoryNode["kind"] = "candidate",
  chosen = false
): Promise<StoryNode> {
  return apiPost<StoryNode>("/api/story/nodes", {
    content,
    book_id: bookId,
    parent_id: parentId ?? null,
    kind,
    chosen,
  });
}

// 选为主线
export function chooseNode(nodeId: string): Promise<StoryNode> {
  return apiPost<StoryNode>(`/api/story/nodes/${nodeId}/choose`, {});
}

// 标为锚点
export function anchorNode(nodeId: string): Promise<StoryNode> {
  return apiPost<StoryNode>(`/api/story/nodes/${nodeId}/anchor`, {});
}

// 删除节点（含后代）
export function deleteNode(nodeId: string): Promise<{ ok: boolean; id: string }> {
  return apiDelete<{ ok: boolean; id: string }>(`/api/story/nodes/${nodeId}`);
}

// S76：批量保存节点手动坐标（DESIGN §12.37）
export function saveStoryLayout(
  positions: Array<{ node_id: string; x: number; y: number }>
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>("/api/story/layout", {
    method: "PUT",
    body: JSON.stringify({ book_id: "main", positions }),
  });
}

// 添加叙事线
export function addThread(
  name: string,
  bookId = "main",
  content = "",
  progress = "",
  role: StoryThread["role"] = "main",
  nodeId?: string
): Promise<StoryThread> {
  return apiPost<StoryThread>("/api/story/threads", {
    name,
    book_id: bookId,
    content,
    progress,
    role,
    node_id: nodeId ?? null,
  });
}
