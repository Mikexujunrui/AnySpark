// Books / Sessions / Materials — V4 适配层（壳调用 → V4 端点）
// 壳的多项目结构映射到 V4 的 book_id 参数化端点；会话≈对话会话。
import { del, get, patch, post, put } from "./http";
import type { BookData } from "./types";

// ── Books（书架：V4 新增 /api/books 端点）──
export const getBooks = (): Promise<BookData[]> => get<BookData[]>("/api/books");
export const getBook = (id: string): Promise<BookData> =>
  get<BookData[]>("/api/books").then((bs) => bs.find((b) => b.id === id) as BookData);
export const createBook = (data: Partial<BookData>): Promise<BookData> =>
  post("/api/books", { content: data.title || data.id || "新项目", book_id: data.id || data.title || "" });
export const updateBook = (id: string, data: Partial<BookData>): Promise<BookData> =>
  put(`/api/brief`, { content: data.description || "", book_id: id }).then(() => ({ id, ...data } as BookData));
export const deleteBook = (id: string): Promise<unknown> => del(`/api/books/${id}`);
export const importSparkProject = async (..._args: unknown[]): Promise<{ ok: boolean; book: BookData; stats: Record<string, unknown> }> => {
  throw new Error("旧项目导入不支持（V4 决策A：全新项目不背沉没成本）");
};

// ── Sessions（对话会话）──
export const getSessions = (): Promise<unknown[]> => get<unknown[]>("/api/conversations");
export const createSession = (_bookId: string, title: string): Promise<unknown> =>
  post("/api/conversations", { title });
export const deleteSession = (_bookId: string, sessionId: string): Promise<unknown> =>
  del(`/api/conversations/${sessionId}`);

// ── Materials（资料库）──
export const getMaterials = (bookId?: string): Promise<unknown[]> =>
  get<unknown[]>(`/api/materials${bookId ? `?book_id=${bookId}` : ""}`);
export const searchMaterials = (q: string, _bookId?: string): Promise<unknown[]> => {
  return get<unknown[]>("/api/materials").then((ms) =>
    (ms as any[]).filter((m) => (m.title || "").includes(q) || (m.summary || "").includes(q))
  );
};
export const createMaterial = (data: unknown): Promise<unknown> => post("/api/materials", data);
export const deleteMaterial = (id: string): Promise<unknown> => del(`/api/materials/${id}`);
// S80：局部编辑资料卡（只改传入字段）
export const patchMaterial = (id: string, data: unknown): Promise<unknown> => patch(`/api/materials/${id}`, data);
// S79：双层资料库——从别的池复制（标 copy 冷藏）+ copy 转灵感
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const importMaterial = (data: { card_id: string; from_book_id: string; to_book_id: string }): Promise<any> =>
  post("/api/materials/import", data);
export const promoteMaterial = (id: string): Promise<unknown> => post(`/api/materials/${id}/promote`, {});

// ── Reference books / analyses：V4 无此能力，降级 ──
export const getReferences = (): Promise<unknown> => Promise.resolve([]);
export const setReferences = (): Promise<unknown> => Promise.resolve({ ok: true });
export const setReferenceUsage = (): Promise<unknown> => Promise.resolve({ ok: true });
export const triggerStructureAnalysis = (): Promise<unknown> => Promise.resolve({});
export const getStructureAnalysis = (): Promise<unknown> => Promise.resolve({});
export const triggerStyleAnalysis = (): Promise<unknown> => Promise.resolve({});
export const getStyleAnalysis = (): Promise<unknown> => Promise.resolve({});
export const listAnalyses = (): Promise<unknown> => Promise.resolve([]);
export const subscribeMaterial = (): Promise<unknown> => Promise.resolve({ ok: true });
export const unsubscribeMaterial = (): Promise<unknown> => Promise.resolve({ ok: true });
