import { useState, useEffect } from "react";
import { listPlans, createPlan, updatePlan, deletePlan, type ChapterPlan } from "../api/plan";

const STATUS_OPTIONS = ["planned", "done"] as const;
const STATUS_LABELS: Record<string, string> = {
  planned: "待写",
  done: "已完成",
};
const STATUS_COLORS: Record<string, string> = {
  planned: "bg-zinc-700/50 text-zinc-400 border-zinc-600",
  done: "bg-green-500/20 text-green-400 border-green-500/30",
};

export default function PlanPanel() {
  const [plans, setPlans] = useState<ChapterPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /* 新增表单 */
  const [chapterOrder, setChapterOrder] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  /* 编辑表单 */
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editStatus, setEditStatus] = useState("");

  const fetchPlans = async () => {
    setLoading(true);
    try {
      const data = await listPlans();
      setPlans(data);
    } catch (e) {
      console.error("Failed to fetch plans:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPlans();
  }, []);

  const handleAdd = async () => {
    const order = parseInt(chapterOrder, 10);
    if (isNaN(order)) return;
    setError(null);
    try {
      await createPlan({ chapter_order: order, title: title.trim(), content: content.trim() });
      setChapterOrder("");
      setTitle("");
      setContent("");
      setShowAdd(false);
      await fetchPlans();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const startEdit = (p: ChapterPlan) => {
    setEditingId(p.id);
    setEditTitle(p.title);
    setEditContent(p.content);
    setEditStatus(p.status);
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    setError(null);
    try {
      await updatePlan(editingId, { title: editTitle.trim(), content: editContent.trim(), status: editStatus });
      setEditingId(null);
      await fetchPlans();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleStatusChange = async (p: ChapterPlan, newStatus: string) => {
    setError(null);
    try {
      await updatePlan(p.id, { status: newStatus });
      await fetchPlans();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDelete = async (id: string) => {
    setError(null);
    try {
      await deletePlan(id);
      await fetchPlans();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-zinc-200">章节计划</h2>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-[11px] px-2 py-1 bg-blue-600/40 hover:bg-blue-500/40 text-blue-300 rounded"
        >
          {showAdd ? "取消" : "+ 新增计划"}
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-2 mb-3 flex items-center justify-between">
          <p className="text-[11px] text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-xs">×</button>
        </div>
      )}

      {/* 新增表单 */}
      {showAdd && (
        <div className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 mb-4 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <label className="block space-y-0.5">
              <span className="text-[10px] text-zinc-500">章节序号</span>
              <input
                type="number"
                className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                value={chapterOrder}
                onChange={(e) => setChapterOrder(e.target.value)}
                placeholder="1"
                min="1"
              />
            </label>
            <label className="block space-y-0.5 col-span-2">
              <span className="text-[10px] text-zinc-500">标题</span>
              <input
                className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="章节标题"
              />
            </label>
          </div>
          <label className="block space-y-0.5">
            <span className="text-[10px] text-zinc-500">计划内容</span>
            <textarea
              className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 h-20 resize-none"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="本章计划推进的情节、角色、场景..."
            />
          </label>
          <div className="flex justify-end">
            <button onClick={handleAdd} className="text-[11px] px-3 py-1 bg-blue-600/60 hover:bg-blue-500/60 text-blue-200 rounded">
              创建
            </button>
          </div>
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <p className="text-zinc-600 text-sm text-center py-8">加载中...</p>
      ) : plans.length === 0 ? (
        <p className="text-zinc-600 text-sm text-center py-8">暂无章节计划</p>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          {plans.map((p) =>
            editingId === p.id ? (
              <div key={p.id} className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 space-y-2">
                <label className="block space-y-0.5">
                  <span className="text-[10px] text-zinc-500">标题</span>
                  <input
                    className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                  />
                </label>
                <label className="block space-y-0.5">
                  <span className="text-[10px] text-zinc-500">内容</span>
                  <textarea
                    className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 h-16 resize-none"
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                  />
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-500">状态</span>
                  {STATUS_OPTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => setEditStatus(s)}
                      className={`text-[10px] px-1.5 py-0.5 rounded border ${editStatus === s ? STATUS_COLORS[s] : "text-zinc-500 border-zinc-700"}`}
                    >
                      {STATUS_LABELS[s]}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setEditingId(null)} className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400">
                    取消
                  </button>
                  <button onClick={handleSaveEdit} className="text-[10px] px-2 py-0.5 rounded bg-blue-600/60 hover:bg-blue-500/60 text-blue-200">
                    保存
                  </button>
                </div>
              </div>
            ) : (
              <div key={p.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-zinc-500">第 {p.chapter_order} 章</span>
                    <h3 className="text-sm font-medium text-zinc-200">{p.title || "(无标题)"}</h3>
                  </div>
                  <div className="flex items-center gap-1">
                    {STATUS_OPTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => handleStatusChange(p, s)}
                        className={`text-[10px] px-1.5 py-0.5 rounded border ${p.status === s ? STATUS_COLORS[s] : "text-zinc-600 border-zinc-800 hover:text-zinc-400"}`}
                      >
                        {STATUS_LABELS[s]}
                      </button>
                    ))}
                    <button onClick={() => startEdit(p)} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 ml-1">
                      编辑
                    </button>
                    <button onClick={() => handleDelete(p.id)} className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/40 hover:bg-red-800/60 text-red-400">
                      删除
                    </button>
                  </div>
                </div>
                {p.content && <p className="text-xs text-zinc-400 line-clamp-3">{p.content}</p>}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
