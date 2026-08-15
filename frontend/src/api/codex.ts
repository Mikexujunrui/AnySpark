import { apiFetch } from "./client";

// S104：代码沙箱（P5 codex——白名单安全执行 + 只读数据环境）
export interface CodexResult {
  ok: boolean;
  stdout: string;
  stderr: string;
  error: string;
}

export function runCodex(code: string, timeout = 10, bookId = "main"): Promise<CodexResult> {
  return apiFetch<CodexResult>("/api/codex/run", {
    method: "POST",
    body: JSON.stringify({ code, timeout, book_id: bookId }),
  });
}
