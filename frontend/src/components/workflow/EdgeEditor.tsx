import type { WorkflowEdge } from "../../api/workflow";

/* ── 边属性编辑 ── */
export default function EdgeEditor({
  edge,
  onChange,
  onDelete,
}: {
  edge: WorkflowEdge;
  onChange: (e: WorkflowEdge) => void;
  onDelete: () => void;
}) {
  const cond = edge.condition ?? { type: "rule" as const, expression: "" };
  const setCond = (patch: Partial<typeof cond>) => {
    onChange({ ...edge, condition: { ...cond, ...patch } });
  };
  return (
    <div className="p-3 flex flex-wrap gap-x-6 gap-y-2 items-start">
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">条件类型</label>
        <select
          value={cond.type}
          onChange={(e) => setCond({ type: e.target.value as "rule" | "model" })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none"
        >
          <option value="rule">规则 rule</option>
          <option value="model">模型判断 model</option>
        </select>
      </div>
      {cond.type === "rule" ? (
        <div>
          <label className="block text-[10px] text-zinc-500 mb-0.5">{"表达式（{{var}} 引用前序输出）"}</label>
          <input
            value={cond.expression ?? ""}
            onChange={(e) => setCond({ expression: e.target.value })}
            placeholder="例：{{review}} contains '硬伤'"
            className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
            style={{ width: 260 }}
          />
        </div>
      ) : (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">模型问题 prompt</label>
            <input
              value={cond.prompt ?? ""}
              onChange={(e) => setCond({ prompt: e.target.value })}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 240 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">期望回答 expect</label>
            <input
              value={cond.expect ?? ""}
              onChange={(e) => setCond({ expect: e.target.value })}
              placeholder="yes"
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 100 }}
            />
          </div>
        </>
      )}
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">边标签（可选，显示在线上）</label>
        <input
          value={edge.label ?? cond.label ?? ""}
          onChange={(e) => setCond({ label: e.target.value })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 140 }}
        />
      </div>
      <button
        onClick={onDelete}
        className="ml-auto text-[11px] px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40"
      >
        删除连线
      </button>
    </div>
  );
}
