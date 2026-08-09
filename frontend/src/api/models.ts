import { apiFetch } from "./client";

// 模型配置
export interface ModelConfig {
  id: string;
  name: string;
  base_url: string;
  model: string;
  api_key?: string;
  context_window: number;
  max_tokens: number;
  temperature: number;
  thinking?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 模型列表响应
interface ModelsResponse {
  active_id: string;
  models: ModelConfig[];
}

// 获取所有模型
export async function listModels(): Promise<ModelConfig[]> {
  const res = await apiFetch<ModelsResponse>("/api/models");
  return res.models;
}

// 激活模型
export function activateModel(id: string): Promise<void> {
  return apiFetch<void>(`/api/models/${id}/activate`, {
    method: "POST",
  });
}
