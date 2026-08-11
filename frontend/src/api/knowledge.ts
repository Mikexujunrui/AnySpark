// Knowledge / Styles / Skills / Workflows / Stats — V4 适配层
// 图谱→/api/graph；文风技巧→/api/skills；工作流→/api/workflows；统计→/api/stats。
import { del, get, patch, post, put } from "./http";
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
// V4 结构：entities=[{id,name,entity_type,aliases,description,state,first_chapter,last_chapter}]
//          relations=[{id,from_name,to_name,rel_type,description}]
//          events=[{id,chapter_ref,time_point,label,description,involved}]
export const getSummary = (bookId: string): Promise<Record<string, unknown>> => {
  const bid = bookId || "main";
  return Promise.all([
    get(`/api/graph/entities?book_id=${bid}`),
    get(`/api/graph/relations?book_id=${bid}`),
    get(`/api/graph/events?book_id=${bid}`),
    get(`/api/plot`).catch(() => []),
  ]).then(([entities, relations, events, foreshadows]) => ({
    entities: entities as unknown[],
    relations: relations as unknown[],
    events: events as unknown[],
    foreshadows: foreshadows as unknown[],
  }));
};
// 实体搜索（V4 支持 q 模糊 + entity_type 过滤）
export const searchEntities = (q: string, entityType = "", bookId = "main"): Promise<unknown[]> =>
  get(`/api/graph/entities?q=${encodeURIComponent(q)}&entity_type=${encodeURIComponent(entityType)}&book_id=${bookId}`);
// 删除实体（name 或 id 定位）
export const deleteEntity = (_bookId: string, entityId: string): Promise<unknown> =>
  del(`/api/graph/entities/${encodeURIComponent(entityId)}`);
// 编辑实体（V4 PATCH：aliases/description/state/entity_type）
export const updateEntity = (_bookId: string, entityId: string, payload: unknown): Promise<unknown> =>
  patch(`/api/graph/entities/${encodeURIComponent(entityId)}`, payload);
// 新建实体（V4 POST：name/entity_type/aliases/description/state）
export const createEntity = (data: {
  name: string;
  entity_type?: string;
  aliases?: string[];
  description?: string;
  state?: string;
  book_id?: string;
}): Promise<unknown> => post("/api/graph/entities", data);

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
