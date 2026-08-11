// Knowledge / Styles / Skills / Workflows / Stats — V4 适配层
// 图谱→/api/graph；文风技巧→/api/skills；工作流→/api/workflows；统计→/api/stats。
import { del, get, post, put } from "./http";
import type { SkillData, SkillsListData, StylesListData } from "./types";

// ── Workflows（工作流池）──
export const getGlobalWorkflows = (): Promise<unknown[]> => get("/api/workflows");
export const deleteGlobalWorkflow = (wfId: string): Promise<unknown> => del(`/api/workflows/${wfId}`);

// ── Stats（写作指标：V4 /api/stats）──
export const getWritingStats = (): Promise<unknown> => get("/api/stats").catch(() => ({}));

// ── Character mentions（角色出场热力）：V4 无，降级 ──
export const getCharacterMentions = (): Promise<unknown> => Promise.resolve([]);
export const refreshCharacterMentions = (): Promise<unknown> => Promise.resolve({});

// ── Knowledge（图谱）──
export const getSummary = (bookId: string): Promise<unknown> => {
  return Promise.all([
    get(`/api/graph/entities?book_id=${bookId || "main"}`),
    get(`/api/graph/relations?book_id=${bookId || "main"}`),
    get(`/api/graph/events?book_id=${bookId || "main"}`),
  ]).then(([entities, relations, events]) => ({ entities, relations, events }));
};
export const deleteEntity = (_bookId: string, entityId: string): Promise<unknown> =>
  del(`/api/graph/entities/${encodeURIComponent(entityId)}`);
export const updateEntity = (_bookId: string, entityId: string, payload: unknown): Promise<unknown> =>
  put(`/api/graph/entities/${encodeURIComponent(entityId)}`, payload);

// ── Extract（图谱抽取：V4 POST /api/graph/extract）──
export const extract = (text: string, bookId: string): Promise<unknown> =>
  post("/api/graph/extract", { chapter_ref: "手动抽取", text, book_id: bookId || "main" });

// ── Styles（文风：V4 技巧 skills）──
export const getStyles = (): Promise<StylesListData> => {
  return get("/api/skills").then((sk) => ({
    styles: (sk as unknown[]).map((s: any) => ({
      name: s.name || s.id,
      description: s.description || s.content || "",
      category: s.category || "style",
    })),
  }));
};
export const getStyle = (name: string): Promise<unknown> =>
  get("/api/skills").then((sk) => (sk as any[]).find((s) => s.name === name || s.id === name) || null);
export const createStyle = (data: unknown): Promise<unknown> =>
  post("/api/skills", { ...(data as object), category: "style" });
export const updateStyle = (name: string, data: unknown): Promise<unknown> => {
  const d = data as any;
  return put(`/api/skills/${name}`, { name: d.name, description: d.description, content: d.content });
};
export const deleteStyle = (name: string): Promise<unknown> => del(`/api/skills/${name}`);
export const getActiveStyle = (): Promise<unknown> => Promise.resolve(null);
export const setActiveStyle = (): Promise<unknown> => Promise.resolve({ ok: true });

// ── Skills（技巧）──
export const getSkills = (): Promise<SkillsListData> => {
  return get<unknown[]>("/api/skills").then((sk) => ({ skills: sk as unknown as SkillData[] }));
};
