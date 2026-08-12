// Settings / Providers / Modes — V4 适配层
// 模型档位→/api/models；设置→/api/settings；无 provider 管理（V4 单模型注册表）。
import { get, post } from "./http";

export const getSettings = (): Promise<unknown> => {
  return get("/api/models").then((models) => {
    const list = models as any[];
    const active = list.find((m) => m.active) || list[0] || {};
    return { mode: active.id || active.name || "deepseek-v4-pro", models: list };
  });
};

export const updateProvider = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteProvider = (): Promise<unknown> => Promise.resolve({ ok: true });
export const updateSlots = (): Promise<unknown> => Promise.resolve({ ok: true });

export const switchMode = (newMode: string): Promise<unknown> => {
  // S98 快速模式：真实现——模式切换持久化（v3 移植；quality/split/flash/custom）
  return post("/api/settings/mode", { mode: newMode }).catch(() => ({ ok: false }));
};

// S98 模式配置读取（模式 + 槽位 + 任务映射 + 注册表模型列表）
export const getMode = (): Promise<unknown> => get("/api/settings/mode");

export const testProvider = (): Promise<unknown> => Promise.resolve({ ok: true });

export const getBookSettings = (): Promise<unknown> => Promise.resolve({});
export const updateBookSettings = (): Promise<unknown> => Promise.resolve({ ok: true });
export const deleteBookSettings = (): Promise<unknown> => Promise.resolve({ ok: true });
export const getEffectiveSettings = (): Promise<unknown> => Promise.resolve({});

export const getUpdateStatus = (): Promise<unknown> => Promise.resolve({ update_available: false });
export const checkForUpdate = (): Promise<unknown> => Promise.resolve({ update_available: false });
export const toggleUpdateCheck = (): Promise<unknown> => Promise.resolve({ ok: true });

// 示例 provider 配置（SettingsModal 展示用，本地假数据）
export const anthropic = { name: "anthropic", label: "Anthropic" };
export const openai = { name: "openai", label: "OpenAI" };
export const example = { name: "example", label: "示例" };
