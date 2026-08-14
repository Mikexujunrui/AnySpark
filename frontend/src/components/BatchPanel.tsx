import { useEffect, useRef, useState } from "react";
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
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showRewrite, setShowRewrite] = useState(false);
  const [instruction, setInstruction] = useState("");

  // S133/S140：批量改写/审读统一走预置 workflow 模板（归一不降级）——
  // 断点恢复/失败重试/改写人工确认闸门/批级回滚（S138）由 workflow 提供；
  // 旧内存 /api/batch/* 已收编移除（S140 阶段 D）。
  const [wfTask, setWfTask] = useState<{
    id: string;
    status: string;
    current: string;
    error: string;
    done: number;
    total: number;
  } | null>(null);
  // S145b：任务结果明细（loop 迭代累积——每章审读/改写输出）
  const [wfItems, setWfItems] = useState<Record<string, string>[]>([]);
  // S147b：旧引擎任务 fallback——loop 无 items 时展示顶层结果（至少最后一章可见）
  const [wfResults, setWfResults] = useState<Record<string, unknown> | null>(null);
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
          // S145b：done 后从 loop 节点 output 解析每迭代明细（每章结果可看）
          const loop = (t.node_states ?? []).find((s: any) => s.node_id === "loop")
          try {
            const parsed = loop && loop.output ? JSON.parse(loop.output) : null
            setWfItems(Array.isArray(parsed?.items) ? parsed.items : [])
          } catch {
            setWfItems([])
          }
          // S147b：顶层 results 兜底（旧引擎任务无 items → 至少展示最后一章结果）
          setWfResults((t.results as Record<string, unknown> | undefined) ?? null)
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
    if (!wfTemplates.review) return;
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
  };

  // 工作流模式执行改写（模板 loop 前带人工确认闸门）
  const handleRewrite = async () => {
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
              {/* S145b：任务结果明细（loop 每迭代输出——批量审读=每章报告，批量改写=每章写回） */}
              {wfTask.status === "done" && wfItems.length > 0 && (
                <div className="border-t border-emerald-800/40 pt-2 mt-1 space-y-1 max-h-48 overflow-y-auto">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wide">结果（{wfItems.length} 项）</p>
                  {wfItems.map((it, i) => (
                    <details key={i} className="text-[11px]">
                      <summary className="cursor-pointer text-emerald-300/90 hover:text-emerald-200">
                        第 {i + 1} 项{it.title ? ` · ${String(it.title).slice(0, 20)}` : ""}
                      </summary>
                      {Object.entries(it).filter(([k]) => k !== "iter").map(([k, v]) => (
                        <pre key={k} className="mt-1 text-zinc-400 whitespace-pre-wrap leading-relaxed bg-zinc-900/50 rounded p-2 max-h-32 overflow-y-auto">
                          {String(v)}
                        </pre>
                      ))}
                    </details>
                  ))}
                </div>
              )}
              {/* S147b：旧引擎任务 fallback——无迭代明细时展示顶层结果（至少最后一章） */}
              {wfTask.status === "done" && wfItems.length === 0 && wfResults && (() => {
                const keys = ["review_report", "review", "report", "rewritten", "fixed", "saved"]
                const hit = keys.find((k) => wfResults[k] != null && String(wfResults[k]).trim())
                return hit ? (
                  <div className="border-t border-emerald-800/40 pt-2 mt-1 space-y-1">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wide">结果（旧引擎任务，仅最后迭代）</p>
                    <details className="text-[11px]" open>
                      <summary className="cursor-pointer text-emerald-300/90 hover:text-emerald-200">最后结果</summary>
                      <pre className="mt-1 text-zinc-400 whitespace-pre-wrap leading-relaxed bg-zinc-900/50 rounded p-2 max-h-48 overflow-y-auto">
                        {String(wfResults[hit]).slice(0, 3000)}
                      </pre>
                    </details>
                  </div>
                ) : null
              })()}
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
                  disabled={selected.size === 0 || !instruction.trim() || wfBusy}
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
                disabled={selected.size === 0 || wfBusy}
                className="flex-1 text-xs px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
              >
                批量改写
              </button>
              <button
                onClick={handleReview}
                disabled={selected.size === 0 || wfBusy}
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
