import type { WorkflowNode } from "../../api/workflow";
import { KIND_LABEL, SCRIPT_FUNCTIONS, SCRIPT_FN_NAMES } from "./constants";

/* ── 节点属性编辑 ── */
export default function NodeEditor({
  node,
  onChange,
  onDelete,
}: {
  node: WorkflowNode;
  onChange: (n: WorkflowNode) => void;
  onDelete: () => void;
}) {
  const set = (patch: Partial<WorkflowNode>) => onChange({ ...node, ...patch });
  const setParam = (k: string, v: unknown) => onChange({ ...node, params: { ...node.params, [k]: v } });
  const setFail = (patch: Partial<WorkflowNode["fail"]>) => onChange({ ...node, fail: { ...node.fail, ...patch } });

  return (
    <div className="p-3 flex flex-wrap gap-x-6 gap-y-2 items-start">
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">标签</label>
        <input
          value={node.label}
          onChange={(e) => set({ label: e.target.value })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 200 }}
        />
      </div>
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">类型（不可改）</label>
        <span className="text-xs text-zinc-400">{KIND_LABEL[node.kind]}</span>
      </div>

      {node.kind === "agent" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">指令 instruction</label>
            <textarea
              value={(node.params.instruction as string) ?? ""}
              onChange={(e) => setParam("instruction", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 w-72 h-20 resize-none"
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">输出键 output_key</label>
            <input
              value={(node.params.output_key as string) ?? ""}
              onChange={(e) => setParam("output_key", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 120 }}
            />
          </div>
        </>
      ) : node.kind === "script" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">函数 function</label>
            <select
              value={(node.params.function as string) ?? ""}
              onChange={(e) => setParam("function", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 220 }}
            >
              <option value="">（选择函数）</option>
              {SCRIPT_FN_NAMES.map((fn) => (
                <option key={fn} value={fn}>
                  {SCRIPT_FUNCTIONS[fn].label}
                </option>
              ))}
            </select>
          </div>
          {SCRIPT_FUNCTIONS[(node.params.function as string) ?? ""]?.params.map((p) => (
            <div key={p.key}>
              <label className="block text-[10px] text-zinc-500 mb-0.5">{p.label}</label>
              <input
                type={p.type === "number" ? "number" : "text"}
                value={(node.params[p.key] as string | number | undefined) ?? ""}
                onChange={(e) =>
                  setParam(p.key, p.type === "number" ? Number(e.target.value) : e.target.value)
                }
                placeholder={p.placeholder}
                className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
                style={{ width: 140 }}
              />
            </div>
          ))}
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">输出键 output_key</label>
            <input
              value={(node.params.output_key as string) ?? ""}
              onChange={(e) => setParam("output_key", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 120 }}
            />
          </div>
        </>
      ) : node.kind === "approval" ? (
        <div>
          <label className="block text-[10px] text-zinc-500 mb-0.5">审批提示 prompt</label>
          <textarea
            value={(node.params.prompt as string) ?? ""}
            onChange={(e) => setParam("prompt", e.target.value)}
            className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 w-72 h-20 resize-none"
          />
        </div>
      ) : node.kind === "loop" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">最大迭代 max_iterations</label>
            <input
              type="number"
              value={(node.params.max_iterations as number) ?? 1}
              onChange={(e) => setParam("max_iterations", Number(e.target.value))}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 80 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">继续条件 continue_condition</label>
            <input
              value={(node.params.continue_condition as string) ?? ""}
              onChange={(e) => setParam("continue_condition", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 240 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">循环体 body</label>
            <input
              value={((node.params.body as string[]) ?? []).join(",")}
              onChange={(e) =>
                setParam("body", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
              }
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 160 }}
              placeholder="节点id1,节点id2"
            />
          </div>
        </>
      ) : (
        <div className="text-[11px] text-zinc-600 max-w-xs">
          条件节点：出边的条件在边属性里设置（点条件标签编辑）。
        </div>
      )}

      {/* 失败策略 */}
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">失败自动重试</label>
        <input
          type="number"
          value={node.fail.auto_retry_count}
          onChange={(e) => setFail({ auto_retry_count: Number(e.target.value) })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 60 }}
        />
      </div>
      <label className="flex items-center gap-1.5 text-[11px] text-zinc-400 mt-4 cursor-pointer">
        <input
          type="checkbox"
          checked={node.fail.fail_auto_skip}
          onChange={(e) => setFail({ fail_auto_skip: e.target.checked })}
        />
        重试耗尽跳过
      </label>

      <button
        onClick={onDelete}
        className="ml-auto text-[11px] px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40"
      >
        删除节点
      </button>
    </div>
  );
}
