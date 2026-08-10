import { useState, useEffect } from "react";
import { useMaterialStore } from "../stores/materialStore";
import type { Material } from "../api/materials";

interface MaterialPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function MaterialPanel({ open, onClose }: MaterialPanelProps) {
  const materials = useMaterialStore((s) => s.materials);
  const loading = useMaterialStore((s) => s.loading);
  const fetchAll = useMaterialStore((s) => s.fetchAll);
  const add = useMaterialStore((s) => s.add);

  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState<Material | null>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState<"style" | "fact" | "both">("fact");

  useEffect(() => {
    if (open) fetchAll();
  }, [open, fetchAll]);

  const handleAdd = async () => {
    if (!text.trim()) return;
    await add({ text: text.trim(), title: title.trim(), purpose });
    setText("");
    setTitle("");
    setPurpose("fact");
    setShowAdd(false);
  };

  const handleSelect = (m: Material) => {
    setSelected(m);
    setShowAdd(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div className="relative ml-auto w-[560px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">资料库</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setShowAdd(!showAdd); setSelected(null); }}
              className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
            >
              {showAdd ? "取消" : "+ 添加"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {showAdd ? (
            <div className="space-y-3">
              <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">添加资料</h3>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="标题（可选）"
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              />
              <select
                value={purpose}
                onChange={(e) => setPurpose(e.target.value as "style" | "fact" | "both")}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              >
                <option value="fact">事实资料</option>
                <option value="style">风格参考</option>
                <option value="both">两者兼有</option>
              </select>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="粘贴或输入资料内容..."
                rows={10}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
              />
              <button
                onClick={handleAdd}
                disabled={!text.trim()}
                className="w-full text-sm px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed"
              >
                入库
              </button>
            </div>
          ) : selected ? (
            <div className="space-y-3">
              <button
                onClick={() => setSelected(null)}
                className="text-xs text-zinc-500 hover:text-zinc-300"
              >
                ← 返回列表
              </button>
              <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-sm font-medium text-zinc-200">{selected.title || "无标题"}</h3>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    selected.purpose === "style" ? "bg-purple-500/20 text-purple-400" :
                    selected.purpose === "both" ? "bg-green-500/20 text-green-400" :
                    "bg-blue-500/20 text-blue-400"
                  }`}>
                    {selected.purpose === "style" ? "风格" : selected.purpose === "both" ? "混合" : "事实"}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mb-3">主题：{selected.topic}</p>

                {selected.key_points.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-zinc-400 mb-1">要点</h4>
                    <ul className="list-disc list-inside text-xs text-zinc-300 space-y-0.5">
                      {selected.key_points.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </div>
                )}

                {selected.key_settings.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-zinc-400 mb-1">关键设定</h4>
                    <ul className="list-disc list-inside text-xs text-zinc-300 space-y-0.5">
                      {selected.key_settings.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}

                {selected.characters.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-zinc-400 mb-1">涉及角色</h4>
                    <div className="flex flex-wrap gap-1">
                      {selected.characters.map((c, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 bg-zinc-700 text-zinc-300 rounded">{c}</span>
                      ))}
                    </div>
                  </div>
                )}

                {selected.terms.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-zinc-400 mb-1">术语</h4>
                    <div className="flex flex-wrap gap-1">
                      {selected.terms.map((t, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 bg-zinc-700 text-zinc-300 rounded">{t}</span>
                      ))}
                    </div>
                  </div>
                )}

                {selected.source_text && (
                  <div className="mt-4 pt-4 border-t border-zinc-700">
                    <h4 className="text-xs text-zinc-400 mb-2">原文</h4>
                    <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-sans bg-zinc-800/50 p-3 rounded max-h-60 overflow-y-auto">
                      {selected.source_text}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              {loading ? (
                <p className="text-xs text-zinc-600 py-4 text-center">加载中...</p>
              ) : materials.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-sm text-zinc-500 mb-2">暂无资料</p>
                  <p className="text-xs text-zinc-600">点击右上角"+ 添加"入库资料</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {materials.map((m) => (
                    <div
                      key={m.id}
                      onClick={() => handleSelect(m)}
                      className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 cursor-pointer hover:bg-zinc-800 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <h4 className="text-sm font-medium text-zinc-200 truncate">{m.title || "无标题"}</h4>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 ${
                          m.purpose === "style" ? "bg-purple-500/20 text-purple-400" :
                          m.purpose === "both" ? "bg-green-500/20 text-green-400" :
                          "bg-blue-500/20 text-blue-400"
                        }`}>
                          {m.purpose === "style" ? "风格" : m.purpose === "both" ? "混合" : "事实"}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-500 truncate">主题：{m.topic}</p>
                      <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
                        <span>{m.key_points.length} 要点</span>
                        <span>{m.characters.length} 角色</span>
                        <span>{new Date(m.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
