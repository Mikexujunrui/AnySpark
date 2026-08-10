import { useState } from "react";
import { chapterWrapup, type WrapupResult } from "../api/plan";
import { useChapterStore } from "../stores/chapterStore";

interface ChapterWrapupProps {
  open: boolean;
  onClose: () => void;
}

export default function ChapterWrapup({ open, onClose }: ChapterWrapupProps) {
  const selectedId = useChapterStore((s) => s.selectedId);
  const selectedChapter = useChapterStore((s) => s.selectedChapter);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WrapupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleWrapup = async () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await chapterWrapup(selectedId);
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
    }
    setLoading(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div className="relative w-[500px] max-h-[80vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl flex flex-col overflow-hidden">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">
            一章收尾{selectedChapter ? ` — ${selectedChapter.title}` : ""}
          </h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!selectedId ? (
            <p className="text-zinc-500 text-sm text-center py-4">请先选择一个章节</p>
          ) : (
            <>
              {/* 操作按钮 */}
              <div className="flex justify-center">
                <button
                  onClick={handleWrapup}
                  disabled={loading}
                  className="text-xs px-4 py-2 bg-blue-600/60 hover:bg-blue-500/60 text-blue-200 rounded-lg disabled:opacity-50"
                >
                  {loading ? "生成中..." : result ? "重新生成" : "生成收尾分析"}
                </button>
              </div>

              {error && (
                <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-3">
                  <p className="text-xs text-red-400">{error}</p>
                </div>
              )}

              {result && (
                <div className="space-y-3">
                  {/* 摘要 */}
                  <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                    <h3 className="text-[10px] text-zinc-500 mb-1">一致性摘要</h3>
                    <p className="text-sm text-zinc-200">{result.summary}</p>
                  </div>

                  {/* 下一章提示 */}
                  {result.next_hint && (
                    <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                      <h3 className="text-[10px] text-zinc-500 mb-1">下一章衔接提示</h3>
                      <p className="text-sm text-zinc-200">{result.next_hint}</p>
                    </div>
                  )}

                  {/* 涉及实体 */}
                  {result.graph_entities.length > 0 && (
                    <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                      <h3 className="text-[10px] text-zinc-500 mb-1">涉及图谱实体</h3>
                      <div className="flex flex-wrap gap-1">
                        {result.graph_entities.map((name) => (
                          <span
                            key={name}
                            className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded"
                          >
                            {name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 未回收钩子 */}
                  {result.open_hooks.length > 0 && (
                    <div className="bg-zinc-800/50 border border-yellow-700/30 rounded-lg p-3">
                      <h3 className="text-[10px] text-yellow-500 mb-1">未回收的主线钩子</h3>
                      <div className="space-y-1.5">
                        {result.open_hooks.map((hook, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-yellow-500 shrink-0">!</span>
                            <div>
                              <span className="text-zinc-300">{hook.content}</span>
                              <span className="text-zinc-500 ml-2">
                                ({hook.category}
                                {hook.open_since != null ? ` · 已开放 ${hook.open_since} 章` : ""}
                                {hook.chapter_ref ? ` · ${hook.chapter_ref}` : ""})
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
