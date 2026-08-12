import { apiGet, apiPost } from "./client";

// 项目简介（S58：给 AI 和用户看的协作总览，权威在 md 文件）
// S101：全部接口按 book_id 隔离（此前硬编码 main 导致跨项目共享）
export interface Brief {
  book_id: string;
  content: string;
  exists: boolean;
}

// 读取项目简介（未建档返回空 + exists=false）
export function getBrief(bookId: string): Promise<Brief> {
  return apiGet<Brief>(`/api/brief?book_id=${encodeURIComponent(bookId)}`);
}

// 保存项目简介（空内容=删除，S101）
export function saveBrief(bookId: string, content: string): Promise<Brief> {
  return apiPost<Brief>("/api/brief", { book_id: bookId, content });
}

// AI 生成简介草案（人工确认后 save 写回）
export function generateBrief(bookId: string): Promise<{ draft: string; note: string }> {
  return apiPost<{ draft: string; note: string }>("/api/brief/generate", {
    book_id: bookId,
  });
}
