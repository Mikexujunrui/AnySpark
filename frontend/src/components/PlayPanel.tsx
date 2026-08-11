import { useState, useEffect } from "react";
import { usePlayStore } from "../stores/playStore";
import { playExport } from "../api/play";

interface PlayPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function PlayPanel({ open, onClose }: PlayPanelProps) {
  const sessions = usePlayStore((s) => s.sessions);
  const session = usePlayStore((s) => s.session);
  const node = usePlayStore((s) => s.node);
  const path = usePlayStore((s) => s.path);
  const loading = usePlayStore((s) => s.loading);
  const listSessions = usePlayStore((s) => s.listSessions);
  const create = usePlayStore((s) => s.create);
  const get = usePlayStore((s) => s.get);
  const choose = usePlayStore((s) => s.choose);
  const branch = usePlayStore((s) => s.branch);
  const stop = usePlayStore((s) => s.stop);

  const [showCreate, setShowCreate] = useState(false);
  const [role, setRole] = useState("");
  const [seed, setSeed] = useState("");
  const [title, setTitle] = useState("");
  const [customText, setCustomText] = useState("");
  const [exportMd, setExportMd] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) listSessions();
  }, [open, listSessions]);

  const handleCreate = async () => {
    setError("");
    if (!role.trim() || !seed.trim()) {
      setError("角色和种子场景必填");
      return;
    }
    try {
      await create(role.trim(), seed.trim(), title.trim());
      setRole("");
      setSeed("");
      setTitle("");
      setShowCreate(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    }
  };

  const handleExport = async () => {
    if (!session) return;
    setError("");
    try {
      const result = await playExport(session.id);
      setExportMd(result.markdown);
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出失败");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-[560px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">互动推演</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {showCreate ? "取消" : "+ 新建推演"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 新建表单 */}
        {showCreate && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="扮演角色（须有角色卡）..."
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <textarea
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="切入场景（自然语言）..."
              rows={3}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="标题（可选）..."
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              onClick={handleCreate}
              className="text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded"
            >
              创建并推演
            </button>
          </div>
        )}

        {/* 主体：会话列表 + 推演区 */}
        <div className="flex-1 flex min-h-0">
          {/* 左侧：会话列表 */}
          <div className="w-44 shrink-0 border-r border-zinc-800 overflow-y-auto p-2 space-y-1">
            {loading && sessions.length === 0 ? (
              <p className="text-xs text-zinc-600 text-center py-3">加载中...</p>
            ) : sessions.length === 0 ? (
              <p className="text-xs text-zinc-600 text-center py-3">暂无推演会话</p>
            ) : (
              sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => get(s.id)}
                  className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                    session?.id === s.id
                      ? "bg-zinc-700 text-zinc-200"
                      : "text-zinc-400 hover:bg-zinc-800"
                  }`}
                >
                  <div className="truncate">{s.title || s.role || s.id}</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="text-[10px] text-zinc-600 truncate">{s.role}</span>
                    <span
                      className={`text-[9px] px-1 rounded ${
                        s.status === "running"
                          ? "bg-green-500/20 text-green-400"
                          : "bg-zinc-700 text-zinc-500"
                      }`}
                    >
                      {s.status === "running" ? "进行中" : "已结束"}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>

          {/* 右侧：推演区 */}
          <div className="flex-1 min-w-0 overflow-y-auto p-4 space-y-3">
            {!session ? (
              <p className="text-sm text-zinc-600 text-center py-6">选择一个推演会话，或新建一个</p>
            ) : (
              <>
                {/* 会话信息 */}
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <h3 className="text-sm font-medium text-zinc-200 truncate">
                      {session.title || session.role}
                    </h3>
                    <p className="text-xs text-zinc-500">扮演：{session.role}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={handleExport}
                      className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
                    >
                      导出
                    </button>
                    {session.status === "running" && (
                      <button
                        onClick={() => {
                          if (confirm("确定终止该推演会话？")) stop(session.id);
                        }}
                        className="text-xs px-2 py-1 text-zinc-500 hover:text-red-400 rounded"
                      >
                        终止
                      </button>
                    )}
                  </div>
                </div>

                {/* 路径 */}
                {path.length > 0 && (
                  <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-2 space-y-1">
                    {path.map((step, i) => (
                      <div key={i} className="text-[11px]">
                        {i > 0 && step.chosen_label && (
                          <span className="text-blue-400">▸ {step.chosen_label}</span>
                        )}
                        {Boolean(step.node.scene) && (
                          <span className="text-zinc-500 block truncate">
                            {String(step.node.scene).slice(0, 60)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* 当前场景 */}
                {node && (
                  <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                    <p className="text-xs text-zinc-500 mb-1">
                      {node.chosen_label ? `选择「${node.chosen_label}」后` : "起始场景"}
                    </p>
                    <p className="text-sm text-zinc-200 whitespace-pre-wrap">{node.scene}</p>
                  </div>
                )}

                {/* 候选行动 */}
                {node && session.status === "running" && node.options.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs text-zinc-400">下一步行动：</p>
                    {node.options.map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => choose(opt.id)}
                        className="w-full text-left text-xs px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 transition-colors"
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* 自定义行动 */}
                {session.status === "running" && (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={customText}
                      onChange={(e) => setCustomText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && customText.trim()) {
                          choose(undefined, customText.trim());
                          setCustomText("");
                        }
                      }}
                      placeholder="自定义行动（回车提交）..."
                      className="w-full bg-zinc-800 text-zinc-200 text-xs px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                )}

                {/* 回溯分叉 */}
                {session.status === "running" && path.length > 1 && (
                  <div className="pt-2 border-t border-zinc-800">
                    <p className="text-xs text-zinc-500 mb-1">回溯分叉（回到历史节点重来）：</p>
                    <div className="flex flex-wrap gap-1">
                      {path.slice(0, -1).map((step, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            if (confirm(`回到第 ${i + 1} 步重新推演？`)) branch(String(step.node.id));
                          }}
                          className="text-[11px] px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded"
                          title={String(step.node.scene ?? "").slice(0, 40)}
                        >
                          第 {i + 1} 步
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* 导出 md 预览 */}
                {exportMd && (
                  <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-xs text-zinc-400">导出灵感卡</p>
                      <button
                        onClick={() => setExportMd("")}
                        className="text-xs text-zinc-500 hover:text-zinc-300"
                      >
                        关闭
                      </button>
                    </div>
                    <pre className="text-[11px] font-mono text-zinc-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {exportMd}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
