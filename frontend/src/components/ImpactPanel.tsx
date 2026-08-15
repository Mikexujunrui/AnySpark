import { useEffect, useState } from "react";
import PanelHeader from "./ui/PanelHeader";
import { useImpactStore } from "../stores/impactStore";

interface ImpactPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
  initialOrder?: number;
  bookId?: string; // S152：项目隔离（缺省 main 兼容旧调用）
}

export default function ImpactPanel({ open, onClose, embedded = false, initialOrder, bookId = "main" }: ImpactPanelProps) {
  const chapters = useImpactStore((s) => s.chapters);
  const impacted = useImpactStore((s) => s.impacted);
  const count = useImpactStore((s) => s.count);
  const loading = useImpactStore((s) => s.loading);
  const error = useImpactStore((s) => s.error);
  const fetchChapters = useImpactStore((s) => s.fetchChapters);
  const analyze = useImpactStore((s) => s.analyze);

  // 按 order_index 排序后的章节；未写序号也保留
  const sortedChapters = [...chapters].sort((a, b) => a.order_index - b.order_index);
  const [selectedOrder, setSelectedOrder] = useState<number>(0);
  const [entitiesText, setEntitiesText] = useState("");

  useEffect(() => {
    if (open) {
      fetchChapters(bookId);
      setEntitiesText("");
      // 预选当前编辑章节（写作时按需触发）
      if (initialOrder != null) {
        setSelectedOrder(initialOrder);
      } else {
        setSelectedOrder(0);
      }
    }
  }, [open, fetchChapters, initialOrder]);

  if (!open) return null;

  // 选中章节变化时重置结果
  const handleSelect = (order: number) => {
    setSelectedOrder(order);
    setEntitiesText("");
  };

  const handleAnalyze = async () => {
    const entities = entitiesText
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    await analyze(selectedOrder, entities.length ? entities : undefined, bookId);
  };

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-[560px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <PanelHeader
          compact
          maxW={false}
          icon="activity"
          iconClass="text-amber-400"
          title="影响分析"
          desc="修改本章涉及的下游影响"
          actions={
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 p-1 rounded-lg hover:bg-zinc-800 transition-colors" title="关闭">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          }
        />

        {/* 分析表单 */}
        <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
          <div className="flex items-center gap-2">
            <select
              value={selectedOrder}
              onChange={(e) => handleSelect(Number(e.target.value))}
              className="flex-1 bg-zinc-800 text-zinc-200 text-sm px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            >
              <option value={0}>-- 选择要改的章节 --</option>
              {sortedChapters.map((c) => (
                <option key={c.id} value={c.order_index}>
                  #{c.order_index} {c.title}
                </option>
              ))}
            </select>
            <button
              onClick={handleAnalyze}
              disabled={!selectedOrder || loading}
              className="text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded shrink-0"
            >
              {loading ? "分析中..." : "分析影响"}
            </button>
          </div>
          <input
            type="text"
            value={entitiesText}
            onChange={(e) => setEntitiesText(e.target.value)}
            placeholder="涉及实体（可选，逗号分隔；缺省自动取该章图谱实体）"
            className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* 结果区 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {error && (
            <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded">
              {error}
            </div>
          )}

          {selectedOrder > 0 && !loading && (
            <p className="text-[11px] text-zinc-500">
              修改第 <span className="text-zinc-300">{selectedOrder}</span> 章 → 受影响下游章节{" "}
              <span className="text-zinc-300">{count}</span> 章
            </p>
          )}

          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">分析中...</p>
          ) : impacted.length === 0 ? (
            selectedOrder > 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">未发现受影响的下游章节</p>
            ) : (
              <p className="text-zinc-600 text-sm text-center py-4">选择章节后分析影响范围</p>
            )
          ) : (
            impacted.map((hit) => (
              <div
                key={hit.chapter_ref}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm text-zinc-200 font-medium">
                    #{hit.chapter_order} {hit.chapter_ref}
                  </p>
                  <div className="flex items-center gap-1">
                    {hit.entities.map((e) => (
                      <span
                        key={e}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-400"
                      >
                        {e}
                      </span>
                    ))}
                  </div>
                </div>
                {hit.events.length > 0 && (
                  <ul className="space-y-1">
                    {hit.events.map((ev, i) => (
                      <li key={i} className="text-xs text-zinc-400 flex gap-1.5">
                        <span className="text-zinc-600">·</span>
                        {ev}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
