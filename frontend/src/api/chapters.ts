// Chapters / Volumes / Notes / Export / Outline / History — V4 适配层
// 壳的多项目 → V4 的 book_id 参数化端点；大纲≈计划；版本历史降级。
import { del, diagLog, get, post, put } from "./http";
import type { Chapter } from "../types";

// ── Response 类型（后端契约对齐，消除 as any）──
interface ChapterDetail extends Chapter {
  versions: ChapterVersion[];
}
interface ChapterVersion {
  version_id: number;
  saved_at: string;
  content: string;
  summary?: string;
}
interface PlanItem {
  book_id?: string;
  id?: string;
  title?: string;
  content?: string;
  status?: string;
  order_index?: number;
}

// ── Chapters（章节）──
export const getChapters = (bookId: string): Promise<Chapter[]> =>
  get<Chapter[]>(`/api/chapters?book_id=${bookId}`);
// S152：参数化 bookId（此前无参固定 main——BatchPanel/ChatPanel/影响分析全部跨项目读错书）
export const listChapters = (bookId = "main"): Promise<Chapter[]> =>
  get<Chapter[]>("/api/chapters?book_id=" + bookId);
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
  return get<PlanItem[]>("/api/plan").then((plans) => ({
    outline: plans.filter((p) => !p.book_id || p.book_id === bookId),
  }));
};
export const getDetailedOutline = (bookId: string): Promise<unknown> => getOutline(bookId);

// ── Chapter history / versions：V4 chapter_versions 表（GET /api/chapters/{id} 返回 versions）──
export const getChapterHistory = (...args: unknown[]): Promise<unknown[]> => {
  const chapterId = args[1] as string;
  if (!chapterId) return Promise.resolve([]);
  return get<ChapterDetail>(`/api/chapters/${chapterId}`).then((ch) => ch?.versions || []);
};
export const getChapterVersion = (...args: unknown[]): Promise<unknown> => {
  const chapterId = args[1] as string;
  const versionId = args[2] as string;
  if (!chapterId) return Promise.resolve(null);
  return get<ChapterDetail>(`/api/chapters/${chapterId}`).then((ch) => {
    const versions = ch?.versions || [];
    const found = versions.find((v) => String(v.saved_at) === String(versionId));
    return { content: found?.content || '', original_content: null, patches_summary: [] };
  });
};
// S138（回溯安全网 B2）：revert 走真实恢复端点（版本 id）；兼容既有调用签名
// (bookId, chapterId, versionId) 与 (chapterId, versionId)
export const revertChapter = (...args: unknown[]): Promise<unknown> => {
  const chapterId = args.length >= 3 ? (args[1] as string) : (args[0] as string);
  const versionId = args.length >= 3 ? (args[2] as number | string) : (args[1] as number | string);
  return post(`/api/chapters/${chapterId}/restore`, { version_id: Number(versionId) });
};
export const deleteChapterVersion = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });

// ── Deep style / emotional curve：V4 无，降级 ──
export const triggerDeepStyle = (): Promise<unknown> => Promise.resolve({});
export const getDeepStyle = (): Promise<unknown> => Promise.resolve({});
export const triggerEmotionalCurve = (): Promise<unknown> => Promise.resolve({});
export const getEmotionalCurve = (): Promise<unknown> => Promise.resolve({});

// ── Worldbuilding entry edit：V4 设定档用 /api/settings，映射 ──
export const updateWorldbuildingEntry = (id: string, data: unknown): Promise<unknown> =>
  put(`/api/settings/${id}`, data);
