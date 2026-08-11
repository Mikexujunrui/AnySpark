// Memory — V4 心智/偏好用 /api/manual，记忆降级。
// 保留签名兼容壳组件调用（MemoryPanel 已删，无实际消费方）。
import { del, get, post } from "./http";

export const getMemoryStats = (): Promise<unknown> => Promise.resolve({ notes: 0, decisions: 0, preferences: 0 });
export const getProjectMemory = (): Promise<unknown> => Promise.resolve({ notes: [], decisions: [], progress: [] });
export const updateProjectMemory = (): Promise<unknown> => Promise.resolve({ ok: true });
export const addNote = (content: string): Promise<unknown> => post("/api/manual", { content, category: "habit" });
export const deleteNote = (id: string): Promise<unknown> => del(`/api/manual/${id}`);
export const recordDecision = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteDecision = (): Promise<unknown> => Promise.resolve({ ok: true });
export const addProgress = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteProgress = (): Promise<unknown> => Promise.resolve({ ok: true });
export const getPreferences = (): Promise<unknown> =>
  get("/api/manual").then((m) => ({ preferences: m as unknown[] }));
export const createPreference = (content: string): Promise<unknown> =>
  post("/api/manual", { content, category: "style" });
export const confirmPreference = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deletePreference = (id: string): Promise<unknown> => del(`/api/manual/${id}`);
export const toggleMemory = (): Promise<unknown> => Promise.resolve({ ok: true });
