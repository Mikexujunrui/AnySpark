import { useState, useEffect } from "react";
import { useTemplateStore } from "../stores/templateStore";

interface TemplatePanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
}

const EMPTY_FORM = {
  name: "",
  description: "",
  granularity: "章",
  position: "发展",
  function: "主线",
  params: "",
};

export default function TemplatePanel({ open, onClose, embedded = false }: TemplatePanelProps) {
  const templates = useTemplateStore((s) => s.templates);
  const loading = useTemplateStore((s) => s.loading);
  const fetchTemplates = useTemplateStore((s) => s.fetchTemplates);
  const addTemplate = useTemplateStore((s) => s.addTemplate);
  const removeTemplate = useTemplateStore((s) => s.removeTemplate);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) fetchTemplates();
  }, [open, fetchTemplates]);

  const handleAdd = async () => {
    if (!form.name.trim() || !form.description.trim()) return;
    setError("");
    try {
      await addTemplate({
        name: form.name.trim(),
        description: form.description.trim(),
        granularity: form.granularity.trim() || "章",
        position: form.position.trim() || "发展",
        function: form.function.trim() || "主线",
        params: form.params
          .split(/[,，]/)
          .map((p) => p.trim())
          .filter(Boolean),
      });
      setForm(EMPTY_FORM);
      setShowAdd(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败");
    }
  };

  const handleDelete = async (name: string, layer?: string) => {
    // L2 默认库不可删（后端仅删 external）
    if (layer === "default") return;
    if (confirm(`确定删除模板「${name}」？`)) {
      await removeTemplate(name);
    }
  };

  if (!open) return null;

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">模板库</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowAdd(!showAdd);
                setError("");
              }}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {showAdd ? "取消" : "+ 导入"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 导入表单 */}
        {showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="模板名 *"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="模板描述 *（怎么用，能变出什么）"
              rows={2}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <div className="flex gap-2">
              <select
                value={form.granularity}
                onChange={(e) => setForm({ ...form, granularity: e.target.value })}
                className="flex-1 bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
                title="粒度"
              >
                <option value="章">章</option>
                <option value="段落">段落</option>
                <option value="全书">全书</option>
              </select>
              <select
                value={form.position}
                onChange={(e) => setForm({ ...form, position: e.target.value })}
                className="flex-1 bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
                title="位置"
              >
                <option value="发展">发展</option>
                <option value="开局">开局</option>
                <option value="高潮">高潮</option>
                <option value="收尾">收尾</option>
              </select>
              <select
                value={form.function}
                onChange={(e) => setForm({ ...form, function: e.target.value })}
                className="flex-1 bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
                title="功能"
              >
                <option value="主线">主线</option>
                <option value="支线">支线</option>
                <option value="伏笔">伏笔</option>
                <option value="情绪">情绪</option>
              </select>
            </div>
            <input
              value={form.params}
              onChange={(e) => setForm({ ...form, params: e.target.value })}
              placeholder="可变参数（逗号分隔，如：反派身份,时间限制）"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              onClick={handleAdd}
              disabled={!form.name.trim() || !form.description.trim()}
              className="w-full text-xs px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
            >
              导入模板
            </button>
          </div>
        )}

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : templates.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无模板</p>
          ) : (
            templates.map((t) => (
              <div
                key={t.name}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-200 truncate">{t.name}</p>
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-blue-500/30 text-blue-400 bg-blue-500/20">
                        {t.granularity}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-400 bg-purple-500/20">
                        {t.position}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-green-500/30 text-green-400 bg-green-500/20">
                        {t.function}
                      </span>
                      {t.layer === "default" && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border border-zinc-600 text-zinc-500 bg-zinc-700/30">
                          默认
                        </span>
                      )}
                    </div>
                  </div>
                  {t.layer !== "default" && (
                    <button
                      onClick={() => handleDelete(t.name, t.layer)}
                      className="p-1 text-zinc-600 hover:text-red-400 rounded shrink-0"
                      title="删除"
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </div>
                <p className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">
                  {t.description}
                </p>
                {t.params && t.params.length > 0 && (
                  <div className="flex items-center gap-1 flex-wrap">
                    {t.params.map((p) => (
                      <span
                        key={p}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700/50 text-zinc-400"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
