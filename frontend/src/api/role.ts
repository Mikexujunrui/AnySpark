import { apiGet, apiPost } from "./client";

// S48-P4 角色推演：低成本多探索 + 判别选优（作为参考，不直接写正文）

// 单路推演候选（strategy=策略名，text=推演正文）
export interface RolePlayCandidate {
  strategy: string;
  text: string;
}

// 角色推演结果（best=判别选优后的最佳路；score_reason=选优理由）
export interface RolePlayResult {
  best: RolePlayCandidate | null;
  candidates: RolePlayCandidate[];
  score_reason: string;
}

// 创建/更新角色卡（卡片/角色卡-{name}.md；S152f 按项目）
export function saveRoleCard(
  name: string,
  content: string,
  bookId = "main"
): Promise<{ ok: boolean; name: string; file: string }> {
  return apiPost<{ ok: boolean; name: string; file: string }>("/api/role/card", {
    name,
    content,
    book_id: bookId,
  });
}

// S152f：读卡片文件内容（如 kind=角色卡 name=陈渡 → 卡片/角色卡-陈渡.md）
export function getCard(
  kind: string,
  name: string,
  bookId = "main"
): Promise<{ kind: string; name: string; content: string }> {
  return apiGet<{ kind: string; name: string; content: string }>(
    `/api/card?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(name)}&book_id=${encodeURIComponent(bookId)}`
  );
}

// 角色推演：角色卡 + 当前状态 + 场景 → N 路隔离推演 → 判别选优（S162 按项目）
export function rolePlay(
  role: string,
  scenario: string,
  n = 4,
  bookId = "main"
): Promise<RolePlayResult> {
  return apiPost<RolePlayResult>("/api/role/play", { role, scenario, n, book_id: bookId });
}
