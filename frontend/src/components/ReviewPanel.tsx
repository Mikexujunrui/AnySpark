import { useEffect, useState } from "react";
import { useReviewStore } from "../stores/reviewStore";
import { listChapters } from "../api/chapters";
import type { Chapter } from "../types";

interface ReviewPanelProps {
  open: boolean;
  onClose: () => void;
}

// S65 拟人化评审团：并发评审 + 主席汇总裁决报告
export default function ReviewPanel({ open, onClose }: ReviewPanelProps) {
  const reviewers = useReviewStore((s) => s.reviewers);
  const result = useReviewStore((s) => s.result);
  const loading = useReviewStore((s) => s.loading);
  const error = useReviewStore((s) => s.error);
  const fetchReviewers = useReviewStore((s) => s.fetchReviewers);
  const runReview = useReviewStore((s) => s.runReview);

  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [useChapter, setUseChapter] = useState(true);
  const [chapterRef, setChapterRef] = useState("");
  const [text, setText] = useState("");
  const [selectedReviewers, setSelectedReviewers] = useState<string[]>([]);
  const [withCheck, setWithCheck] = useState(true);
  const [withForeshadow, setWithForeshadow] = useState(true);
  const [showMarkdown, setShowMarkdown] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetchReviewers();
    listChapters()
      .then((cs) => {
        setChapters(cs);
        if (cs.length > 0) setChapterRef(cs[0].title);
      })
      .catch((e) => console.error("Failed to load chapters:", e));
  }, [open, fetchReviewers]);

  // 初始选中全部激活评审员
  useEffect(() => {
    if (open && reviewers.length > 0) {
      setSelectedReviewers((prev) =>
        prev.length > 0 ? prev : reviewers.filter((r) => r.active).map((r) => r.id)
      );
    }
  }, [open, reviewers]);

  if (!open) return null;

  const toggleReviewer = (id: string) => {
    setSelectedReviewers((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleRun = () => {
    runReview({
      chapter_ref: useChapter && chapterRef ? chapterRef : undefined,
      text: useChapter ? undefined : text,
      reviewer_ids: selectedReviewers,
      with_check: withCheck,
      with_foreshadow: withForeshadow,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">评审团</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {/* 评审对象：章节 or 贴文本 */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              {(
                [
                  [true, "选章节"],
                  [false, "贴文本"],
                ] as const
              ).map(([v, label]) => (
                <button
                  key={String(v)}
                  onClick={() => setUseChapter(v)}
                  className={`text-xs px-2 py-1 rounded ${
                    useChapter === v
                      ? "bg-zinc-700 text-zinc-200"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {useChapter ? (
              <select
                value={chapterRef}
                onChange={(e) => setChapterRef(e.target.value)}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-2 py-2 rounded border border-zinc-700 focus:outline-none"
              >
                {chapters.map((c) => (
                  <option key={c.id} value={c.title}>
                    {c.title}
                  </option>
                ))}
              </select>
            ) : (
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="粘贴待评审文本..."
                rows={6}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
              />
            )}
          </div>

          {/* 评审员选择 */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-500">评审员（可多选）</p>
            <div className="flex flex-wrap gap-1">
              {reviewers.map((r) => (
                <button
                  key={r.id}
                  onClick={() => toggleReviewer(r.id)}
                  className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                    selectedReviewers.includes(r.id)
                      ? "bg-blue-600/30 text-blue-300 border-blue-500/40"
                      : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-500"
                  }`}
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>

          {/* 注入上下文开关 */}
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={withCheck}
                onChange={(e) => setWithCheck(e.target.checked)}
                className="accent-blue-600"
              />
              硬伤清单
            </label>
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={withForeshadow}
                onChange={(e) => setWithForeshadow(e.target.checked)}
                className="accent-blue-600"
              />
              关键点图谱
            </label>
          </div>

          <button
            onClick={handleRun}
            disabled={loading || (!useChapter && !text.trim())}
            className="w-full text-xs px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
          >
            {loading ? "评审中..." : "开始评审"}
          </button>

          {error && <p className="text-xs text-red-400">{error}</p>}

          {/* 评审结果 */}
          {result && !loading && (
            <div className="space-y-3">
              <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 flex items-center gap-3">
                <div className="text-3xl font-bold text-blue-400">
                  {result.overall_score}
                </div>
                <div className="text-xs text-zinc-500">
                  综合分 / 10（{result.valid_count}/{result.reviewer_count} 评审员有效）
                </div>
              </div>

              {result.summary && (
                <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                  <p className="text-xs text-zinc-500 mb-1">总结</p>
                  <p className="text-sm text-zinc-200 whitespace-pre-wrap">{result.summary}</p>
                </div>
              )}

              {result.consensus.length > 0 && (
                <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1">
                  <p className="text-xs text-zinc-500 mb-1">共识</p>
                  {result.consensus.map((c, i) => (
                    <p key={i} className="text-sm text-zinc-300">
                      · {c}
                    </p>
                  ))}
                </div>
              )}

              {result.divergences.length > 0 && (
                <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1">
                  <p className="text-xs text-zinc-500 mb-1">分歧</p>
                  {result.divergences.map((d, i) => (
                    <p key={i} className="text-sm text-zinc-300">
                      · {d}
                    </p>
                  ))}
                </div>
              )}

              {result.top_suggestions.length > 0 && (
                <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1">
                  <p className="text-xs text-zinc-500 mb-1">首要建议</p>
                  {result.top_suggestions.map((s, i) => (
                    <p key={i} className="text-sm text-zinc-300">
                      · {s}
                    </p>
                  ))}
                </div>
              )}

              {result.errors.length > 0 && (
                <div className="bg-red-900/20 border border-red-700/40 rounded-lg p-3 space-y-1">
                  <p className="text-xs text-red-400 mb-1">错误</p>
                  {result.errors.map((e, i) => (
                    <p key={i} className="text-xs text-red-300">
                      · {e}
                    </p>
                  ))}
                </div>
              )}

              <button
                onClick={() => setShowMarkdown(!showMarkdown)}
                className="text-xs text-zinc-500 hover:text-zinc-300"
              >
                {showMarkdown ? "收起完整报告" : "展开完整报告"}
              </button>
              {showMarkdown && result.markdown && (
                <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-400 whitespace-pre-wrap overflow-x-auto">
                  {result.markdown}
                </pre>
              )}
            </div>
          )}
          {!result && !loading && !error && (
            <p className="text-zinc-600 text-sm text-center py-4">
              选择评审对象与评审员后开始
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
