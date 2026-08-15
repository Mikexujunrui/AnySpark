import { useState } from "react";
import { runCodex } from "../api/codex";

// S104：代码沙箱面板（P5 codex 前端展示——白名单安全执行 + 只读数据环境）
// 示例：ws_chapters() 返回章节列表；ws_entities() 返回图谱实体——真实统计数据
const SAMPLE = `# 只读数据环境（真实数据）
chs = ws_chapters()  # 全部章节 [{order, title, chars}]
total = sum(c["chars"] for c in chs)
print(f"共 {len(chs)} 章，{total} 字")`;

export default function CodexPanel({ bookId = "main" }: { bookId?: string }) {
  const [code, setCode] = useState(SAMPLE);
  const [result, setResult] = useState<{ ok: boolean; stdout: string; stderr: string; error: string } | null>(null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    if (!code.trim()) return;
    setRunning(true);
    try {
      const r = await runCodex(code, 10, bookId);
      setResult(r);
    } catch (e) {
      setResult({ ok: false, stdout: "", stderr: "", error: (e as Error).message });
    }
    setRunning(false);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 flex flex-col min-h-0 px-4 py-3 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-zinc-500">代码沙箱（白名单安全执行 + 只读数据环境 ws_*：真实章节/图谱统计）</p>
          <button
            onClick={handleRun}
            disabled={running || !code.trim()}
            className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
          >
            {running ? "运行中..." : "运行"}
          </button>
        </div>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          className="flex-1 min-h-0 w-full bg-zinc-950 text-emerald-300 text-xs font-mono px-3 py-2 rounded border border-zinc-800 focus:outline-none focus:border-zinc-600 resize-none"
        />
        {result && (
          <div className="shrink-0 max-h-56 overflow-y-auto bg-zinc-950 rounded border border-zinc-800 px-3 py-2 space-y-2">
            <p className={`text-[11px] font-medium ${result.ok ? "text-emerald-400" : "text-red-400"}`}>
              {result.ok ? "✓ 运行成功" : `✗ 运行失败${result.error ? `：${result.error}` : ""}`}
            </p>
            {result.stdout && (
              <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-mono">{result.stdout}</pre>
            )}
            {result.stderr && (
              <pre className="text-xs text-amber-400 whitespace-pre-wrap font-mono">{result.stderr}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
