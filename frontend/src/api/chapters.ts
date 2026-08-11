import { apiFetch } from "./client";
import type { Chapter } from "../types";

// 定点编辑操作定义（S44）
export interface PatchOperation {
  op: "insert" | "delete" | "replace";
  anchor: string; // 锚点文本（定位段落）
  text?: string; // insert/replace 用
}

export interface PatchResult {
  ok: boolean;
  op: string;
  anchor: string;
  error?: string;
}

export interface ChapterPatch {
  title: string;
  ok: boolean;
  results: PatchResult[];
  chars: number;
}

// 列出所有章节
export function listChapters(): Promise<Chapter[]> {
  return apiFetch<Chapter[]>("/api/chapters");
}

// 获取单个章节
export function getChapter(id: string): Promise<Chapter> {
  return apiFetch<Chapter>(`/api/chapters/${id}`);
}

// 创建章节
export function createChapter(title: string): Promise<Chapter> {
  return apiFetch<Chapter>("/api/chapters", {
    method: "POST",
    body: JSON.stringify({ title, book_id: "main", content: "" }),
  });
}

// 删除章节
export function deleteChapter(id: string): Promise<void> {
  return apiFetch<void>(`/api/chapters/${id}`, {
    method: "DELETE",
  });
}

// 更新章节内容
export function patchChapter(
  id: string,
  data: { content: string }
): Promise<Chapter> {
  return apiFetch<Chapter>(`/api/chapters/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// S44：定点编辑（锚点段插入/删除/替换，不重写整章，省 token）
export function patchChapterContent(
  id: string,
  operations: PatchOperation[]
): Promise<ChapterPatch> {
  return apiFetch<ChapterPatch>(`/api/chapters/${id}/patch`, {
    method: "POST",
    body: JSON.stringify({ operations }),
  });
}
