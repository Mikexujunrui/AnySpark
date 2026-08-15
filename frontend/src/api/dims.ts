import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

// S50 探索维度（内容化：可增删改/开关）——探索该从哪些维度发散取决于用户与作品

// 探索维度条目（enabled 后端为 0/1 整数）
export interface ExploreDim {
  id: string;
  name: string;
  enabled: number;
  order_index: number;
  created_at: string;
}

// 列出全部探索维度
export function listDims(): Promise<ExploreDim[]> {
  return apiGet<ExploreDim[]>("/api/explore/dims");
}

// 新增维度
export function addDim(name: string): Promise<ExploreDim> {
  return apiPost<ExploreDim>("/api/explore/dims", { name });
}

// 启用/停用维度
export function setDimEnabled(id: string, enabled: boolean): Promise<ExploreDim> {
  return apiPatch<ExploreDim>(`/api/explore/dims/${id}`, { enabled });
}

// 删除维度
export function deleteDim(id: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/api/explore/dims/${id}`);
}
