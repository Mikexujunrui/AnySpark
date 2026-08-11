// Chapters / Volumes / Notes / Export / Outline / History — V4 适配层
// 壳的多项目 → V4 的 book_id 参数化端点；大纲≈计划；版本历史降级。
import { del, diagLog, get, post, put } from "./http";
import type { Chapter } from "../types";

// ── Chapters（章节）──
export const getChapters = (bookId: string): Promise<unknown[]> =>
  get(`/api/chapters?book_id=${bookId}`);
// 兼容旧 V4 调用（BatchPanel 等）：无参返回 main 书章节
export const listChapters = (): Promise<Chapter[]> =>
  get<Chapter[]>("/api/chapters?book_id=main");
export const createChapter = (_bookId: string, data: unknown): Promise<unknown> =>
  post("/api/chapters", { ...(data as object), book_id: _bookId });
export const updateChapter = (_bookId: string, chapterId: string, data: unknown): Promise<unknown> =>
  put(`/api/chapters/${chapterId}`, data);
export const deleteChapter = (_bookId: string, chapterId: string): Promise<unknown> =>
  del(`/api/chapters/${chapterId}`);

// ── Volumes：V4 无卷概念，降级（兼容任意调用签名）──
export const getVolumes = (..._args: unknown[]): Promise<{ volumes: unknown[] }> =>
  Promise.resolve({ volumes: [] });

// ── Chapter reorder：V4 无重排端点，降级（本地排序由前端处理）──
export const reorderChapters = (..._args: unknown[]): Promise<{ ok: boolean; count: number }> =>
  Promise.resolve({ ok: true, count: 0 });

// ── Notes：V4 无书笔记，降级 ──
export const getNotes = (): Promise<unknown[]> => Promise.resolve([]);
export const addBookNote = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteBookNote = (): Promise<unknown> => Promise.resolve({ ok: true });

// ── Export（导出）──
export const exportBook = (_bookId: string, format?: string): Promise<Response> => {
  const url = `/api/export/book?format=${format || "txt"}`;
  diagLog.info(`GET ${url} — 导出请求`);
  return fetch(url);
};

// ── Chapter status：V4 无 promote/demote，降级（兼容任意调用签名）──
export const promoteChapter = (..._args: unknown[]): Promise<{ status: string }> =>
  Promise.resolve({ status: "ok" });
export const demoteChapter = (..._args: unknown[]): Promise<{ status: string }> =>
  Promise.resolve({ status: "ok" });

// ── Outline（大纲 ≈ V4 计划）──
export const getOutline = (bookId: string): Promise<unknown> => {
  return get<unknown[]>("/api/plan").then((plans) => ({
    outline: (plans as any[]).filter((p) => !p.book_id || p.book_id === bookId),
  }));
};
export const getDetailedOutline = (bookId: string): Promise<unknown> => getOutline(bookId);

// ── Chapter history / versions：V4 无版本历史 API，降级（兼容任意调用签名）──
// ── Chapter history / versions：V4 chapter_versions 表（GET /api/chapters/{id} 返回 versions）──
export const getChapterHistory = (...args: unknown[]): Promise<unknown[]> => {
  const chapterId = args[1] as string;
  if (!chapterId) return Promise.resolve([]);
  return get(`/api/chapters/${chapterId}`).then((ch) => (ch as any)?.versions || []);
};
export const getChapterVersion = (...args: unknown[]): Promise<unknown> => {
  const chapterId = args[1] as string;
  const versionId = args[2] as string;
  if (!chapterId) return Promise.resolve(null);
  return get(`/api/chapters/${chapterId}`).then((ch) => {
    const versions = (ch as any)?.versions || [];
    const found = versions.find((v: any) => String(v.saved_at) === String(versionId));
    return { content: found?.content || '', original_content: null, patches_summary: [] };
  });
};
export const revertChapter = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteChapterVersion = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });

// ── Deep style / emotional curve：V4 无，降级 ──
export const triggerDeepStyle = (): Promise<unknown> => Promise.resolve({});
export const getDeepStyle = (): Promise<unknown> => Promise.resolve({});
export const triggerEmotionalCurve = (): Promise<unknown> => Promise.resolve({});
export const getEmotionalCurve = (): Promise<unknown> => Promise.resolve({});

// ── Worldbuilding entry edit：V4 设定档用 /api/settings，映射 ──
export const updateWorldbuildingEntry = (id: string, data: unknown): Promise<unknown> =>
  put(`/api/settings/${id}`, data);
