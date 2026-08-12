import { apiFetch } from "./client";

export interface Skill {
  id: string;
  name: string;
  description?: string;
  content: string;
  target?: string;
  enabled?: boolean;
  created_at: string;
  updated_at: string;
}

export function listSkills(): Promise<Skill[]> {
  return apiFetch<Skill[]>("/api/skills");
}

export function createSkill(
  name: string,
  content: string,
  description?: string,
  target?: string
): Promise<Skill> {
  return apiFetch<Skill>("/api/skills", {
    method: "POST",
    body: JSON.stringify({ name, content, description, target }),
  });
}

export function updateSkill(
  id: string,
  data: { name?: string; content?: string; description?: string; target?: string; enabled?: boolean }
): Promise<Skill> {
  return apiFetch<Skill>(`/api/skills/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteSkill(id: string): Promise<void> {
  return apiFetch<void>(`/api/skills/${id}`, {
    method: "DELETE",
  });
}

// ── S103 技能草稿（书库/资料提炼 → 人工确认转正） ──
export interface SkillDraft {
  id: string;
  name: string;
  description?: string;
  content: string;
  example?: string;
  tags?: string;
  target?: string;
  source?: string;
  created_at: string;
}

export function listSkillDrafts(): Promise<SkillDraft[]> {
  return apiFetch<SkillDraft[]>("/api/skills/drafts");
}

export function promoteSkillDraft(draftId: string): Promise<Skill> {
  return apiFetch<Skill>(`/api/skills/drafts/${draftId}/promote`, {
    method: "POST",
  });
}

export function deleteSkillDraft(draftId: string): Promise<void> {
  return apiFetch<void>(`/api/skills/drafts/${draftId}`, {
    method: "DELETE",
  });
}
