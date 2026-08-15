import { apiFetch } from "./client";

export interface ManualEntry {
  id: string;
  content: string;
  confidence?: number;
  scope: string;
  category: "collab" | "style" | "habit";
  locked?: boolean;
  created_at: string;
  updated_at: string;
}

// S152g：bookId 贯通——项目级说明书/通知按当前项目（此前不传，后端默认 main 跨项目）
export function listManual(scope = "project", bookId = "main"): Promise<ManualEntry[]> {
  return apiFetch<ManualEntry[]>(`/api/manual?scope=${scope}&book_id=${encodeURIComponent(bookId)}`);
}

export function createManual(
  content: string,
  category: "collab" | "style" | "habit",
  confidence = 0.8,
  scope = "project",
  bookId = "main"
): Promise<ManualEntry> {
  return apiFetch<ManualEntry>("/api/manual", {
    method: "POST",
    body: JSON.stringify({ content, category, confidence, scope, book_id: bookId }),
  });
}

export function updateManual(
  id: string,
  data: { content?: string; locked?: boolean; category?: "collab" | "style" | "habit" }
): Promise<ManualEntry> {
  return apiFetch<ManualEntry>(`/api/manual/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteManual(id: string): Promise<void> {
  return apiFetch<void>(`/api/manual/${id}`, {
    method: "DELETE",
  });
}

// S74c 心智变更通知（用户知情界面）：谁在何时改了哪条偏好
export interface ManualNotice {
  id: string;
  entry_id?: string;
  action: string; // add|update|delete
  category?: string;
  content?: string;
  old_content?: string;
  new_content?: string;
  source?: string;
  created_at?: string;
  read?: boolean;
}

export function listManualNotices(limit = 20, bookId = "main"): Promise<ManualNotice[]> {
  return apiFetch<ManualNotice[]>(
    `/api/manual/notices?limit=${limit}&book_id=${encodeURIComponent(bookId)}`
  );
}
