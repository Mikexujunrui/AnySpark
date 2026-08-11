import { apiPost } from "./client";

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

// 创建/更新角色卡（卡片/角色卡-{name}.md）
export function saveRoleCard(
  name: string,
  content: string
): Promise<{ ok: boolean; name: string; file: string }> {
  return apiPost<{ ok: boolean; name: string; file: string }>("/api/role/card", {
    name,
    content,
  });
}

// 角色推演：角色卡 + 当前状态 + 场景 → N 路隔离推演 → 判别选优
export function rolePlay(
  role: string,
  scenario: string,
  n = 4
): Promise<RolePlayResult> {
  return apiPost<RolePlayResult>("/api/role/play", { role, scenario, n });
}
