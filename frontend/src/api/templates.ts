import { apiDelete, apiGet, apiPost } from "./client";

// 模板库条目（L2 默认库 + L3 外部导入）
export interface TemplateItem {
  name: string;
  description: string;
  granularity: string;
  position: string;
  function: string;
  params: string[];
  layer?: string; // default | external
}

// 模板导入请求
export interface TemplateInput {
  name: string;
  description: string;
  granularity: string;
  position: string;
  function: string;
  params: string[];
}

// 列出全部模板（L2+L3 合并）
export function listTemplates(): Promise<TemplateItem[]> {
  return apiGet<TemplateItem[]>("/api/templates");
}

// 导入自定义模板
export function importTemplate(data: TemplateInput): Promise<TemplateItem> {
  return apiPost<TemplateItem>("/api/templates/import", data);
}

// 删除外部模板（L2 默认模板不可删，后端对 default 库无操作）
export function deleteTemplate(name: string): Promise<{ ok: boolean }> {
  return apiDelete<{ ok: boolean }>(`/api/templates/${encodeURIComponent(name)}`);
}

// 从书提炼模板候选（人工确认后走 import 入库）
export function generateTemplates(
  sourceText: string,
  hint = "",
  maxItems = 5
): Promise<{ candidates: TemplateItem[]; existing_templates: string[] }> {
  return apiPost<{ candidates: TemplateItem[]; existing_templates: string[] }>(
    "/api/templates/generate",
    { source_text: sourceText, hint, max_items: maxItems }
  );
}
