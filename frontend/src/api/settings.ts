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
  // 模型激活（V4 /api/models/{id}/activate）
  return post(`/api/models/${encodeURIComponent(newMode)}/activate`, {}).catch(() => ({ ok: false }));
};

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
