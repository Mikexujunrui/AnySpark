import { apiFetch } from "./client";

// 操作信号（S75 补全：前端操作反馈 → /api/signals → 对齐闭环/心智提炼/档位调节）
// 后端 SignalIn: kind/content/new_content/context
export type SignalKind =
  | "accepted" // 接受（选候选/接受正文）
  | "modified" // 修改（手动改正文"改成这样更好"——提炼偏好）
  | "deleted" // 删除
  | "rejected" // 拒绝
  | "negative" // 负例（用户明确否定"不要X"——提炼雷区）
  | "custom";

export function reportSignal(
  kind: SignalKind,
  content: string,
  opts: { newContent?: string; context?: string } = {}
): Promise<void> {
  // fire-and-forget：信号上报失败不影响主流程（对齐闭环尽力而为）
  return apiFetch<void>("/api/signals", {
    method: "POST",
    body: JSON.stringify({
      kind,
      content,
      new_content: opts.newContent ?? null,
      context: opts.context ?? "",
    }),
  }).catch(() => {
    // 静默失败：信号是尽力而为的，不阻塞用户操作
  });
}
