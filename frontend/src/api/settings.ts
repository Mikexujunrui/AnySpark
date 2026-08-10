// 设置 API
import { apiFetch } from "./client";

export interface SettingCategory {
  id: string;
  name: string;
  description: string;
}

export interface WorldSetting {
  id: string;
  category: string;
  name: string;
  content: string;
  created_at: string;
}

// 类别管理
export function listSettingCategories(): Promise<SettingCategory[]> {
  return apiFetch<SettingCategory[]>("/api/settings/categories");
}

export function addSettingCategory(name: string, description: string = ""): Promise<SettingCategory> {
  return apiFetch<SettingCategory>("/api/settings/categories", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function deleteSettingCategory(id: string): Promise<void> {
  return apiFetch<void>(`/api/settings/categories/${id}`, { method: "DELETE" });
}

// 设定条目管理
export function listSettings(): Promise<WorldSetting[]> {
  return apiFetch<WorldSetting[]>("/api/settings");
}

export function addSetting(category: string, name: string, content: string): Promise<WorldSetting> {
  return apiFetch<WorldSetting>("/api/settings", {
    method: "POST",
    body: JSON.stringify({ category, name, content }),
  });
}

export function patchSetting(id: string, data: Partial<{ name: string; content: string }>): Promise<WorldSetting> {
  return apiFetch<WorldSetting>(`/api/settings/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteSetting(id: string): Promise<void> {
  return apiFetch<void>(`/api/settings/${id}`, { method: "DELETE" });
}

// 破限模式
export interface UncensoredConfig {
  enabled: boolean;
  level: string;
}

export function getUncensored(): Promise<UncensoredConfig> {
  return apiFetch<UncensoredConfig>("/api/uncensored");
}

export function setUncensored(enabled: boolean, level: string = "standard"): Promise<UncensoredConfig> {
  return apiFetch<UncensoredConfig>("/api/uncensored", {
    method: "POST",
    body: JSON.stringify({ enabled, level }),
  });
}
