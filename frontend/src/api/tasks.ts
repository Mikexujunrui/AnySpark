// Tasks / Autopilot — V4 无此能力（对端专属），全部降级空。
// 保留签名兼容壳组件调用（壳传多参，降级函数收任意参）；autopilot 返回空闲态。

export const getTasks = (..._args: unknown[]): Promise<unknown[]> => Promise.resolve([]);
export const getTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve(null);
export const createTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ id: "none", status: "done" });
export const startTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const pauseTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const resumeTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const cancelTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const retryTask = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const setAuditMode = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });

export const startAutopilot = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const confirmAutopilot = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const stopAutopilot = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
export const getAutopilotStatus = (..._args: unknown[]): Promise<unknown> =>
  Promise.resolve({ status: "idle", active: false, tasks: [] });
export const getAutopilotTaskStatus = (..._args: unknown[]): Promise<unknown> =>
  Promise.resolve({ status: "done", total_steps: 0, done_steps: 0 });

export const getSupervisorStatus = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ online: true });
export const triggerRecovery = (..._args: unknown[]): Promise<unknown> => Promise.resolve({ ok: true });
