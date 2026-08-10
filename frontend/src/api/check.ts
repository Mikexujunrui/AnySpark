import { apiPost } from "./client";

// 审读发现项
export interface CheckFinding {
  category: string;
  severity: "hard" | "soft" | "info";
  message: string;
  evidence: string;
  suggestion: string;
  source: string;
}

// 审读报告
export interface CheckReport {
  target: string;
  hard_count: number;
  graph_evidence: string;
  temporal_warnings: string[];
  findings: CheckFinding[];
}

// 运行审读
export function runCheck(
  text: string,
  target = "当前章节",
  chapterOrder?: number,
  line = "main"
): Promise<CheckReport> {
  return apiPost<CheckReport>("/api/check", {
    text,
    target,
    chapter_order: chapterOrder ?? null,
    line,
  });
}

// 自定义规则检测
export function runCheckRule(rule: string, text: string): Promise<{ rule: string; hits: string[] }> {
  return apiPost<{ rule: string; hits: string[] }>("/api/check/rule", { rule, text });
}
