import { useEffect, useState } from "react";
import { useBatchStore } from "../stores/batchStore";
import { listChapters } from "../api/chapters";
import type { Chapter } from "../types";

interface BatchPanelProps {
  open: boolean;
  onClose: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  done: "完成",
};

export default function BatchPanel({ open, onClose }: BatchPanelProps) {
  const batchId = useBatchStore((s) => s.batchId);
  const status = useBatchStore((s) => s.status);
  const done = useBatchStore((s) => s.done);
  const total = useBatchStore((s) => s.total);
  const results = useBatchStore((s) => s.results);
  const loading = useBatchStore((s) => s.loading);
  const error = useBatchStore((s) => s.error);
  const startRewrite = useBatchStore((s) => s.startRewrite);
  const startReview = useBatchStore((s) => s.startReview);
  const stopPolling = useBatchStore((s) => s.stopPolling);

  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showRewrite, setShowRewrite] = useState(false);
  const [instruction, setInstruction] = useState("");

  // 打开时拉取章节列表
  useEffect(() => {
    if (!open) return;
    listChapters()
      .then((list) => setChapters(list))
      .catch((e) => console.error("Failed to load chapters:", e));
  }, [open]);

  // 关闭时停止轮询
  useEffect(() => {
    if (!open) stopPolling();
  }, [open, stopPolling]);

  const toggleChapter = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === chapters.length ? new Set() : new Set(chapters.map((c) => c.id))
    );
  };

  const handleRewrite = async () => {
    if (selected.size === 0 || !instruction.trim()) return;
    await startRewrite([...selected], instruction.trim());
    setShowRewrite(false);
    setInstruction("");
  };

  const handleReview = async () => {
    if (selected.size === 0) return;
    await startReview([...selected]);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">批量操作</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 章节选择 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-zinc-500">已选 {selected.size} 章</span>
            <button
              onClick={toggleAll}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {selected.size === chapters.length && chapters.length > 0 ? "全不选" : "全选"}
            </button>
          </div>
          {chapters.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无章节</p>
          ) : (
            chapters.map((ch) => (
              <label
                key={ch.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-zinc-800/60 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.has(ch.id)}
                  onChange={() => toggleChapter(ch.id)}
                  className="accent-blue-500"
                />
                <span className="text-sm text-zinc-300 truncate">
                  {ch.order_index != null ? `${ch.order_index}. ` : ""}
                  {ch.title}
                </span>
              </label>
            ))
          )}
        </div>

        {/* 底部操作区 */}
        <div className="px-4 py-3 border-t border-zinc-800 space-y-2">
          {error && <p className="text-xs text-red-400">{error}</p>}

          {/* 进度显示 */}
          {batchId && status && (
            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-400">
                  {STATUS_LABELS[status] || status}
                </span>
                <span className="text-zinc-500">
                  {done}/{total}
                </span>
              </div>
              <div className="w-full h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all"
                  style={{ width: total > 0 ? `${(done / total) * 100}%` : "0%" }}
                />
              </div>
            </div>
          )}

          {/* 结果列表 */}
          {results.length > 0 && (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {results.map((r) => (
                <div
                  key={r.id}
                  className="text-xs px-2 py-1.5 rounded bg-zinc-800/50 border border-zinc-700/50"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-300 truncate">
                      {r.title || r.id}
                    </span>
                    {r.ok ? (
                      <span className="text-green-500 shrink-0 ml-2">
                        {r.chars != null ? `✓ ${r.chars}字` : r.hard != null ? `✓ ${r.hard}处硬伤` : "✓"}
                      </span>
                    ) : (
                      <span className="text-red-400 shrink-0 ml-2">✗</span>
                    )}
                  </div>
                  {!r.ok && r.error && (
                    <p className="text-red-400/80 mt-0.5 truncate">{r.error}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 改写指令输入 */}
          {showRewrite && (
            <div className="space-y-2">
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="输入改写指令，如：整体文风更冷峻克制，保留剧情走向..."
                rows={3}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRewrite}
                  disabled={selected.size === 0 || !instruction.trim() || loading}
                  className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
                >
                  执行
                </button>
                <button
                  onClick={() => setShowRewrite(false)}
                  className="text-xs px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
                >
                  取消
                </button>
              </div>
            </div>
          )}

          {/* 操作按钮 */}
          {!showRewrite && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowRewrite(true)}
                disabled={selected.size === 0 || loading}
                className="flex-1 text-xs px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
              >
                批量改写
              </button>
              <button
                onClick={handleReview}
                disabled={selected.size === 0 || loading}
                className="flex-1 text-xs px-3 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
              >
                批量审读
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
