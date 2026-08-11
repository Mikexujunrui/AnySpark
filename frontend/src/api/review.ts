import { apiGet, apiPost } from "./client";

// S65 拟人化评审团：并发评审 + 主席汇总裁决报告

// 评审员定义（人格 + 评分维度 + 激活态）
export interface ReviewerDef {
  id: string;
  name: string;
  avatar: string;
  category: string;
  active: boolean;
  scoring_dimensions: Array<{ name: string; weight: number; desc: string }>;
  context_keys: string[];
  custom: boolean;
}

// 评审团汇总报告
export interface ReviewReport {
  chapter_ref: string;
  overall_score: number;
  summary: string;
  consensus: string[];
  divergences: string[];
  top_suggestions: string[];
  reviewer_count: number;
  valid_count: number;
  errors: string[];
  markdown: string;
  compact: string;
}

// 列出全部评审员
export function listReviewers(): Promise<ReviewerDef[]> {
  return apiGet<ReviewerDef[]>("/api/review/reviewers");
}

// 运行评审团（chapter_ref 与 text 二选一，ref 优先）
export function runReviewPanel(body: {
  chapter_ref?: string;
  text?: string;
  reviewer_ids?: string[];
  with_check?: boolean;
  with_foreshadow?: boolean;
}): Promise<ReviewReport> {
  return apiPost<ReviewReport>("/api/review/panel", {
    book_id: "main",
    ...body,
  });
}
