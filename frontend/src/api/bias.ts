import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

// AI 倾向档案（双向黑盒：AI 自述 + 用户修正，注入后续对话）
export interface BiasEntry {
  id: string;
  content: string;
  source: "ai" | "user";
  created_at: string;
}

// 列出倾向档案（最新在前）
export function listBias(): Promise<BiasEntry[]> {
  return apiGet<BiasEntry[]>("/api/bias");
}

// 新增倾向自述（source: ai=AI 声明 / user=用户修正）
export function addBias(content: string, source: string): Promise<BiasEntry> {
  return apiPost<BiasEntry>("/api/bias", { content, source });
}

// 修改倾向条目（人类手动编辑：内容/来源）
export function updateBias(id: string, content: string, source: string): Promise<BiasEntry> {
  return apiPatch<BiasEntry>(`/api/bias/${id}`, { content, source });
}

// 删除倾向条目
export function deleteBias(id: string): Promise<void> {
  return apiDelete<void>(`/api/bias/${id}`);
}
