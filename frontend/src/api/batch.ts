import { apiGet, apiPost } from "./client";

// 批量任务结果项（改写或审读的逐章结果）
export interface BatchResultItem {
  id: string;
  title?: string;
  ok: boolean;
  chars?: number;
  hard?: number;
  report?: string;
  error?: string;
}

// 批量任务状态
export interface BatchStatus {
  batch_id: string;
  status: string; // queued | running | done
  done: number;
  total: number;
  results: BatchResultItem[];
}

// 批量改写：多章统一指令改写
export function batchRewrite(
  chapterIds: string[],
  instruction: string
): Promise<{ batch_id: string; total: number }> {
  return apiPost<{ batch_id: string; total: number }>("/api/batch/rewrite", {
    chapter_ids: chapterIds,
    instruction,
  });
}

// 批量审读：多章检测网审读
export function batchReview(
  chapterIds: string[]
): Promise<{ batch_id: string; total: number }> {
  return apiPost<{ batch_id: string; total: number }>("/api/batch/review", {
    chapter_ids: chapterIds,
  });
}

// 查询批量任务状态/进度/结果
export function getBatchStatus(batchId: string): Promise<BatchStatus> {
  return apiGet<BatchStatus>(`/api/batch/${batchId}`);
}
