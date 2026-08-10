import { apiFetch } from "./client";

/* ── 章节计划 ── */

export interface ChapterPlan {
  id: string;
  chapter_order: number;
  title: string;
  content: string;
  status: string; // pending | in_progress | done
  created_at: string;
}

export interface PlanCreate {
  chapter_order: number;
  title?: string;
  content?: string;
}

export interface PlanPatch {
  title?: string;
  content?: string;
  status?: string;
}

export function listPlans(): Promise<ChapterPlan[]> {
  return apiFetch<ChapterPlan[]>("/api/plan");
}

export function createPlan(req: PlanCreate): Promise<ChapterPlan> {
  return apiFetch<ChapterPlan>("/api/plan", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function updatePlan(planId: string, req: PlanPatch): Promise<ChapterPlan> {
  return apiFetch<ChapterPlan>(`/api/plan/${planId}`, {
    method: "PATCH",
    body: JSON.stringify(req),
  });
}

export function deletePlan(planId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/plan/${planId}`, {
    method: "DELETE",
  });
}

/* ── 一章收尾 ── */

export interface WrapupResult {
  chapter_id: string;
  title: string;
  summary: string;
  next_hint: string;
  graph_entities: string[];
  open_hooks: { content: string; chapter_ref: string; category: string; open_since: number | null }[];
}

export function chapterWrapup(chapterId: string): Promise<WrapupResult> {
  return apiFetch<WrapupResult>(`/api/chapters/${chapterId}/wrapup`, {
    method: "POST",
  });
}
