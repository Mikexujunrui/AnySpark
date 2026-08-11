import { useState, useEffect } from "react";
import { listPlots, addPlotItem, updatePlot, deletePlot, generatePlot, type PlotPoint } from "../api/plot";

const STATUS_COLORS: Record<string, string> = {
  open: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  resolved: "bg-green-500/20 text-green-400 border-green-500/30",
};

const PRIORITY_COLORS: Record<string, string> = {
  must: "bg-red-500/20 text-red-400 border-red-500/30",
  soft: "bg-zinc-700/50 text-zinc-400 border-zinc-600",
};

export default function PlotPanel() {
  const [plots, setPlots] = useState<PlotPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* 新增表单 */
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("伏笔");
  const [chapterRef, setChapterRef] = useState("");
  const [priority, setPriority] = useState("soft");

  const fetchPlots = async () => {
    setLoading(true);
    try {
      const data = await listPlots();
      setPlots(data);
    } catch (e) {
      console.error("Failed to fetch plots:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPlots();
  }, []);

  const handleAdd = async () => {
    if (!content.trim()) return;
    setError(null);
    try {
      await addPlotItem({ content: content.trim(), category, chapter_ref: chapterRef.trim(), priority });
      setContent("");
      setChapterRef("");
      setShowAdd(false);
      await fetchPlots();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generatePlot();
      await fetchPlots();
    } catch (e) {
      console.error("Failed to generate plot:", e);
    }
    setGenerating(false);
  };

  const handleStatusToggle = async (p: PlotPoint) => {
    const newStatus = p.status === "open" ? "resolved" : "open";
    setError(null);
    try {
      await updatePlot(p.id, { status: newStatus });
      await fetchPlots();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handlePriorityToggle = async (p: PlotPoint) => {
    const newPriority = p.priority === "must" ? "soft" : "must";
    setError(null);
    try {
      await updatePlot(p.id, { priority: newPriority });
      await fetchPlots();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDelete = async (id: string) => {
    setError(null);
    try {
      await deletePlot(id);
      await fetchPlots();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-zinc-200">关键点图谱 / 伏笔管理</h2>
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="text-[11px] px-2 py-1 bg-purple-600/40 hover:bg-purple-500/40 text-purple-300 rounded disabled:opacity-50"
          >
            {generating ? "生成中..." : "AI 生成"}
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="text-[11px] px-2 py-1 bg-blue-600/40 hover:bg-blue-500/40 text-blue-300 rounded"
          >
            {showAdd ? "取消" : "+ 登记伏笔"}
          </button>
        </div>
      </div>

      {/* 新增表单 */}
      {showAdd && (
        <div className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 mb-4 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-0.5">
              <span className="text-[10px] text-zinc-500">内容</span>
              <textarea
                className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 h-16 resize-none"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="伏笔/关键点内容"
              />
            </label>
            <div className="space-y-2">
              <label className="block space-y-0.5">
                <span className="text-[10px] text-zinc-500">分类</span>
                <select
                  className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option>伏笔</option>
                  <option>线索</option>
                  <option>悬念</option>
                  <option>转折</option>
                </select>
              </label>
              <label className="block space-y-0.5">
                <span className="text-[10px] text-zinc-500">章节</span>
                <input
                  className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                  value={chapterRef}
                  onChange={(e) => setChapterRef(e.target.value)}
                  placeholder="第N章"
                />
              </label>
              <label className="block space-y-0.5">
                <span className="text-[10px] text-zinc-500">优先级</span>
                <select
                  className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  <option value="soft">soft（细节线索）</option>
                  <option value="must">must（剧情钩子）</option>
                </select>
              </label>
            </div>
          </div>
          <div className="flex justify-end">
            <button onClick={handleAdd} className="text-[11px] px-3 py-1 bg-blue-600/60 hover:bg-blue-500/60 text-blue-200 rounded">
              登记
            </button>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-2 mb-3 flex items-center justify-between">
          <p className="text-[11px] text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-xs">×</button>
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <p className="text-zinc-600 text-sm text-center py-8">加载中...</p>
      ) : plots.length === 0 ? (
        <p className="text-zinc-600 text-sm text-center py-8">暂无关键点/伏笔。可手动登记或 AI 生成。</p>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          {plots.map((p) => (
            <div key={p.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-zinc-200 flex-1">{p.content}</p>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleStatusToggle(p)}
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_COLORS[p.status] || STATUS_COLORS.open}`}
                  >
                    {p.status === "open" ? "开放" : "已回收"}
                  </button>
                  <button
                    onClick={() => handlePriorityToggle(p)}
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${PRIORITY_COLORS[p.priority] || PRIORITY_COLORS.soft}`}
                  >
                    {p.priority === "must" ? "必须" : "可选"}
                  </button>
                  <button
                    onClick={() => handleDelete(p.id)}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/40 hover:bg-red-800/60 text-red-400"
                  >
                    删除
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-3 mt-1.5 text-[10px] text-zinc-500">
                <span className="px-1.5 py-0.5 bg-zinc-700/50 rounded">{p.category}</span>
                {p.chapter_ref && <span>章节: {p.chapter_ref}</span>}
                {p.planted_order > 0 && <span>登记序: {p.planted_order}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
