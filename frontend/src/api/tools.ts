import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

// 扩展工具（P5 注册表：人工批准生效）
export interface ExtTool {
  id: string;
  name: string;
  description: string;
  params: unknown[];
  code_preview: string;
  status: "draft" | "active";
  created_at: string;
}

export interface RegisterToolResult {
  ok: boolean;
  id: string;
  name: string;
  status: string;
  note?: string;
}

// 列出全部扩展工具
export function listTools(): Promise<ExtTool[]> {
  return apiGet<ExtTool[]>("/api/tools");
}

// 登记新工具（status=draft，人工批准后生效）
export function registerTool(
  name: string,
  description: string,
  paramsJson: string,
  code: string
): Promise<RegisterToolResult> {
  return apiPost<RegisterToolResult>("/api/tools/register", {
    name,
    description,
    params_json: paramsJson,
    code,
  });
}

// 人工批准 → active
export function approveTool(id: string): Promise<RegisterToolResult> {
  return apiPost<RegisterToolResult>(`/api/tools/${id}/approve`, {});
}

// 更新工具（改后自动回 draft 重新批准）
export function updateTool(
  id: string,
  data: { name?: string; description?: string; params_json?: string; code?: string }
): Promise<RegisterToolResult> {
  return apiPatch<RegisterToolResult>(`/api/tools/${id}`, data);
}

// 停用（回 draft）
export function disableTool(id: string): Promise<RegisterToolResult> {
  return apiPost<RegisterToolResult>(`/api/tools/${id}/disable`, {});
}

// 删除工具
export function deleteTool(id: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/api/tools/${id}`);
}
