import { apiFetch } from "./client";
import type { Chapter } from "../types";

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
