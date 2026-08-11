import { useState, useEffect } from "react";
import { useToolStore } from "../stores/toolStore";

interface ToolsPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function ToolsPanel({ open, onClose }: ToolsPanelProps) {
  const tools = useToolStore((s) => s.tools);
  const loading = useToolStore((s) => s.loading);
  const fetchTools = useToolStore((s) => s.fetchTools);
  const addTool = useToolStore((s) => s.addTool);
  const approve = useToolStore((s) => s.approve);
  const disable = useToolStore((s) => s.disable);
  const remove = useToolStore((s) => s.remove);

  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [paramsJson, setParamsJson] = useState("[]");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) fetchTools();
  }, [open, fetchTools]);

  const handleAdd = async () => {
    setError("");
    if (!name.trim() || !description.trim()) {
      setError("工具名和描述必填");
      return;
    }
    if (!code.includes("def run(")) {
      setError("工具代码必须定义 def run(args: dict) -> str 函数");
      return;
    }
    try {
      await addTool(name.trim(), description.trim(), paramsJson.trim() || "[]", code);
      setName("");
      setDescription("");
      setParamsJson("[]");
      setCode("");
      setShowAdd(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "登记失败");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-[480px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">扩展工具</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAdd(!showAdd)}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {showAdd ? "取消" : "+ 登记"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 登记表单 */}
        {showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="工具名（唯一，agent 可见）..."
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="工具描述（agent 判断何时调用）..."
              rows={2}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <textarea
              value={paramsJson}
              onChange={(e) => setParamsJson(e.target.value)}
              placeholder='参数定义 JSON 数组，如 [{"name":"query","type":"string"}]'
              rows={2}
              className="w-full bg-zinc-800 text-zinc-200 text-xs font-mono px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder={"工具代码：def run(args: dict) -> str\n  ..."}
              rows={5}
              className="w-full bg-zinc-800 text-zinc-200 text-xs font-mono px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              onClick={handleAdd}
              className="text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded"
            >
              登记（待人工批准）
            </button>
          </div>
        )}

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : tools.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无扩展工具</p>
          ) : (
            tools.map((tool) => (
              <div
                key={tool.id}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <h3 className="text-sm font-medium text-zinc-200 truncate">{tool.name}</h3>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded border ${
                        tool.status === "active"
                          ? "bg-green-500/20 text-green-400 border-green-500/30"
                          : "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                      }`}
                    >
                      {tool.status === "active" ? "已生效" : "待批准"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {tool.status === "draft" ? (
                      <button
                        onClick={() => approve(tool.id)}
                        className="text-xs px-2 py-1 bg-green-600/20 hover:bg-green-600/40 text-green-400 rounded"
                        title="人工批准生效"
                      >
                        批准
                      </button>
                    ) : (
                      <button
                        onClick={() => disable(tool.id)}
                        className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
                        title="停用（回待批准）"
                      >
                        停用
                      </button>
                    )}
                    <button
                      onClick={() => {
                        if (confirm(`确定删除工具「${tool.name}」？`)) remove(tool.id);
                      }}
                      className="text-xs px-2 py-1 text-zinc-500 hover:text-red-400 rounded"
                    >
                      删除
                    </button>
                  </div>
                </div>
                <p className="text-xs text-zinc-400 whitespace-pre-wrap">{tool.description}</p>
                {tool.code_preview && (
                  <pre className="text-[10px] font-mono text-zinc-500 bg-zinc-900/50 rounded p-2 overflow-x-auto">
                    {tool.code_preview}
                  </pre>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
