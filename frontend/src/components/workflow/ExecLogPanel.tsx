import type { WorkflowNode, WorkflowTask } from "../../api/workflow";

/* ── S152e：执行明细浮层（节点状态时间线） ── */
const EXEC_STATUS_TEXT: Record<string, string> = {
  done: "完成",
  failed: "失败",
  running: "执行中",
  skipped: "跳过",
  pending: "等待",
  queued: "排队",
};
const EXEC_STATUS_COLOR: Record<string, string> = {
  done: "#10b981",
  failed: "#ef4444",
  running: "#facc15",
  skipped: "#71717a",
  pending: "#3f3f46",
  queued: "#3f3f46",
};

export default function ExecLogPanel({
  runningTask,
  nodesById,
  onLocate,
  onClose,
}: {
  runningTask: WorkflowTask;
  nodesById: Record<string, WorkflowNode>;
  onLocate: (nodeId: string) => void;
  onClose: () => void;
}) {
  const states = [...(runningTask.node_states ?? [])].reverse(); // 最新在前
  const statusText = runningTask.status;
  return (
    <div className="absolute bottom-2 left-2 w-72 max-h-64 flex flex-col bg-zinc-900/95 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-zinc-800 bg-zinc-900">
        <span className="text-[10px] text-zinc-400 font-medium">
          执行明细 · {statusText === "done" ? "✓ 完成" : statusText === "failed" ? "✗ 失败" : statusText === "waiting_approval" ? "⏸ 等待确认" : `● ${statusText}`}
        </span>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-xs leading-none">×</button>
      </div>
      <div className="flex-1 overflow-auto p-1">
        {states.length === 0 && <p className="text-[11px] text-zinc-600 px-2 py-2">暂无节点明细（任务初始化中）</p>}
        {states.map((s) => {
          const n = nodesById[s.node_id];
          const color = EXEC_STATUS_COLOR[s.status] ?? "#3f3f46";
          const text = EXEC_STATUS_TEXT[s.status] ?? s.status;
          const summary = (s.output ?? s.error ?? "")
            .replace(/\n+/g, " ")
            .slice(0, 48);
          return (
            <button
              key={s.node_id}
              onClick={() => onLocate(s.node_id)}
              className={`w-full text-left px-2 py-1 rounded hover:bg-zinc-800 transition-colors ${s.status === "running" ? "bg-zinc-800/60" : ""}`}
              title={summary || n?.label || s.node_id}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span className="text-[11px] text-zinc-300 truncate flex-1">
                  {n?.label ?? s.node_id}
                </span>
                <span className="text-[10px] text-zinc-500 shrink-0" style={{ color }}>
                  {text}
                </span>
              </div>
              {summary && (
                <p className="text-[10px] text-zinc-600 truncate pl-3">{summary}</p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
