import { useEffect, useRef, useState } from "react";
import { useBatchStore } from "../stores/batchStore";
import PanelHeader from "./ui/PanelHeader";
import { listChapters } from "../api/chapters";
import {
  approveTask,
  getWorkflowTask,
  listWorkflows,
  runWorkflow,
} from "../api/workflow";
import type { Chapter } from "../types";

interface BatchPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  done: "完成",
};

export default function BatchPanel({ open, onClose, embedded = false }: BatchPanelProps) {
  const batchId = useBatchStore((s) => s.batchId);
  const status = useBatchStore((s) => s.status);
  const done = useBatchStore((s) => s.done);
  const total = useBatchStore((s) => s.total);
  const results = useBatchStore((s) => s.results);
  const loading = useBatchStore((s) => s.loading);
  const error = useBatchStore((s) => s.error);
  const startRewrite = useBatchStore((s) => s.startRewrite);
  const startReview = useBatchStore((s) => s.startReview);

  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showRewrite, setShowRewrite] = useState(false);
  const [instruction, setInstruction] = useState("");

  // S133：工作流模式（W1-B 归一不降级）——批量改写/审读走预置 workflow 模板
  // （可断点恢复/失败重试/改写带人工确认闸门），与旧内存任务并存
  const [wfEnabled, setWfEnabled] = useState(false);
  const [wfTask, setWfTask] = useState<{
    id: string;
    status: string;
    current: string;
    error: string;
    done: number;
    total: number;
  } | null>(null);
  const [wfPendingApprove, setWfPendingApprove] = useState(false);
  const [wfBusy, setWfBusy] = useState(false);
  const [wfTemplates, setWfTemplates] = useState<{ rewrite: string; review: string }>({
    rewrite: "",
    review: "",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 打开时拉取章节 + 预置工作流模板 id
  useEffect(() => {
    if (!open) return;
    listChapters()
      .then((list) => setChapters(list))
      .catch((e) => console.error("Failed to load chapters:", e));
    listWorkflows()
      .then((wfs) => {
        setWfTemplates({
          rewrite: wfs.find((w) => w.name === "批量改写")?.id ?? "",
          review: wfs.find((w) => w.name === "批量审读")?.id ?? "",
        });
      })
      .catch((e) => console.error("Failed to load workflows:", e));
  }, [open]);

  // 工作流任务轮询（进度 + 批准闸门检测）
  const stopWfPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startWfPoll = (taskId: string) => {
    stopWfPoll();
    const poll = async () => {
      try {
        const t = await getWorkflowTask(taskId);
        const states = t.node_states ?? [];
        const done = states.filter((s) => s.status === "done").length;
        const total = states.length || 0;
        setWfTask({
          id: taskId,
          status: t.status,
          current: t.current_node_id ?? "",
          error: t.error ?? "",
          done,
          total,
        });
        if (t.status === "waiting_approval") {
          setWfPendingApprove(true);
          stopWfPoll();
        } else if (t.status === "done" || t.status === "failed" || t.status === "cancelled") {
          stopWfPoll();
          setWfBusy(false);
        }
      } catch (e) {
        console.error("workflow poll error", e);
        stopWfPoll();
        setWfBusy(false);
      }
    };
    void poll();
    pollRef.current = setInterval(poll, 1500);
  };

  // 关闭时停止轮询
  useEffect(() => {
    if (!open) {
      stopWfPoll();
      setWfTask(null);
      setWfPendingApprove(false);
      setWfBusy(false);
    }
  }, [open]);

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

  const handleReview = async () => {
    if (selected.size === 0) return;
    if (wfEnabled && wfTemplates.review) {
      setWfBusy(true);
      try {
        const r = await runWorkflow(wfTemplates.review, "main", {
          chapter_ids: JSON.stringify([...selected]),
        });
        startWfPoll(r.task_id);
      } catch (e) {
        console.error(e);
        setWfBusy(false);
      }
      return;
    }
    await startReview([...selected]);
  };

  // S133：工作流模式执行改写（模板 loop 前带人工确认闸门）
  const handleRewriteWorkflow = async () => {
    if (selected.size === 0 || !instruction.trim() || !wfTemplates.rewrite) return;
    setWfBusy(true);
    setShowRewrite(false);
    try {
      const r = await runWorkflow(wfTemplates.rewrite, "main", {
        chapter_ids: JSON.stringify([...selected]),
        instruction: instruction.trim(),
      });
      startWfPoll(r.task_id);
    } catch (e) {
      console.error(e);
      setWfBusy(false);
    }
    setInstruction("");
  };

  const handleRewrite = async () => {
    if (selected.size === 0 || !instruction.trim()) return;
    if (wfEnabled && wfTemplates.rewrite) {
      await handleRewriteWorkflow();
      return;
    }
    await startRewrite([...selected], instruction.trim());
    setShowRewrite(false);
    setInstruction("");
  };

  const handleWfApprove = async (decision: "ok" | "reject") => {
    if (!wfTask) return;
    setWfPendingApprove(false);
    try {
      await approveTask(wfTask.id, decision);
      startWfPoll(wfTask.id);
    } catch (e) {
      console.error(e);
      setWfBusy(false);
    }
  };

  const handleWfCancel = () => {
    stopWfPoll();
    setWfTask(null);
    setWfBusy(false);
  };

  if (!open) return null;

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <PanelHeader
          compact
          maxW={false}
          icon="layers"
          iconClass="text-emerald-400"
          title="批量操作"
          desc="多章统一改写 / 审读"
          actions={
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800 transition-colors" title="关闭">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          }
        />

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

          {/* S133：工作流模式开关（归一不降级：可断点/带确认闸门，与旧内存任务并存） */}
          <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={wfEnabled}
              onChange={(e) => setWfEnabled(e.target.checked)}
              className="accent-emerald-500"
            />
            工作流模式（可断点恢复；改写带确认闸门）
          </label>

          {/* 工作流任务进度/状态 */}
          {wfTask && (
            <div className="bg-emerald-900/20 border border-emerald-700/40 rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-emerald-400">
                  {wfTask.status === "waiting_approval"
                    ? "等待确认"
                    : STATUS_LABELS[wfTask.status] || wfTask.status}
                </span>
                <span className="text-zinc-500">
                  {wfTask.done}/{wfTask.total || "?"}
                </span>
              </div>
              {wfTask.status === "running" && wfTask.total > 0 && (
                <div className="w-full h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 transition-all"
                    style={{ width: `${(wfTask.done / wfTask.total) * 100}%` }}
                  />
                </div>
              )}
              {wfTask.error && (
                <p className="text-red-400/80 text-[11px]">{wfTask.error}</p>
              )}
              {(wfTask.status === "done" || wfTask.status === "failed") && (
                <button
                  onClick={handleWfCancel}
                  className="text-[11px] text-zinc-400 hover:text-zinc-200"
                >
                  ✓ 已结束（关闭进度）
                </button>
              )}
            </div>
          )}

          {/* S133：approval 闸门确认弹窗（批量改写覆盖原稿前人工把关） */}
          {wfPendingApprove && wfTask && (
            <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-3 space-y-2">
              <p className="text-xs text-amber-300">
                批量改写将覆盖所选章节（旧版进版本历史），确认执行？
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleWfApprove("ok")}
                  className="flex-1 text-xs px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded"
                >
                  确认覆盖
                </button>
                <button
                  onClick={() => handleWfApprove("reject")}
                  className="flex-1 text-xs px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
                >
                  取消
                </button>
              </div>
            </div>
          )}

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
                  disabled={selected.size === 0 || !instruction.trim() || loading || wfBusy}
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
                disabled={selected.size === 0 || loading || wfBusy}
                className="flex-1 text-xs px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
              >
                批量改写
              </button>
              <button
                onClick={handleReview}
                disabled={selected.size === 0 || loading || wfBusy}
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
