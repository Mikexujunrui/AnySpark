import { apiGet, apiPost } from "./client";

// 项目简介（S58：给 AI 和用户看的协作总览，权威在 md 文件）
export interface Brief {
  book_id: string;
  content: string;
  exists: boolean;
}

// 读取项目简介（未建档返回空 + exists=false）
export function getBrief(): Promise<Brief> {
  return apiGet<Brief>("/api/brief");
}

// 保存项目简介（用户/前端编辑）
export function saveBrief(content: string): Promise<Brief> {
  return apiPost<Brief>("/api/brief", { content, book_id: "main" });
}

// AI 生成简介草案（人工确认后 save 写回）
export function generateBrief(): Promise<{ draft: string; note: string }> {
  return apiPost<{ draft: string; note: string }>("/api/brief/generate", {
    book_id: "main",
  });
}
