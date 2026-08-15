// S104：前端错误捕获——window.onerror / unhandledrejection → localStorage 环形缓冲
// 前端 bug 从此有痕（此前 console 报错零落盘，排查只能靠口述重现）。
const KEY = "anyspark.errorLog";
const MAX = 50;

interface ErrorEntry {
  ts: string;
  type: "error" | "unhandledrejection";
  msg: string;
  src?: string;
  line?: number;
  col?: number;
}

function push(entry: ErrorEntry) {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || "[]");
    list.push(entry);
    while (list.length > MAX) list.shift();
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* 存储失败静默 */
  }
}

export function initErrorLog() {
  if (typeof window === "undefined") return;
  window.addEventListener("error", (e) => {
    push({
      ts: new Date().toISOString(),
      type: "error",
      msg: e.message || "未知错误",
      src: e.filename || undefined,
      line: e.lineno || undefined,
      col: e.colno || undefined,
    });
  });
  window.addEventListener("unhandledrejection", (e) => {
    let msg = "Promise rejection";
    try {
      const r = e.reason;
      if (r instanceof Error) msg = r.message;
      else if (typeof r === "string") msg = r;
      else if (r && typeof r === "object") msg = JSON.stringify(r).slice(0, 500);
    } catch {
      /* 序列化失败用默认 */
    }
    push({ ts: new Date().toISOString(), type: "unhandledrejection", msg });
  });
}

export function getErrorLog(): ErrorEntry[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function clearErrorLog() {
  localStorage.removeItem(KEY);
}

export function exportErrorLog() {
  const blob = new Blob([JSON.stringify(getErrorLog(), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `anyspark-frontend-errors-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
