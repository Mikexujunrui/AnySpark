import { apiPost } from "./client";

// 受影响下游章节（S45：改第 N 章涉及实体 → 后续引用这些实体的事件/关系所在章）
export interface ImpactHit {
  chapter_ref: string;
  chapter_order: number;
  entities: string[];
  events: string[];
}

// 影响分析结果（POST /api/impact）
export interface ImpactResult {
  changed_order: number;
  impacted: ImpactHit[];
  count: number;
}

// 影响分析：改第 chapterOrder 章（可显式给涉及实体，缺省后端自动取该章图谱实体）
export function analyzeImpact(
  chapterOrder: number,
  entities?: string[]
): Promise<ImpactResult> {
  return apiPost<ImpactResult>("/api/impact", {
    chapter_order: chapterOrder,
    entities: entities || null,
  });
}
