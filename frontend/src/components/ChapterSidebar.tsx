import { useEffect, useState } from "react";
import { useChapterStore } from "../stores/chapterStore";

export default function ChapterSidebar() {
  const { chapters, selectedId, loading, fetchChapters, selectChapter, addChapter, removeChapter } =
    useChapterStore();
  const [newTitle, setNewTitle] = useState("");
  const [showInput, setShowInput] = useState(false);

  // 初始加载章节列表
  useEffect(() => {
    fetchChapters();
  }, [fetchChapters]);

  const handleAdd = async () => {
    const title = newTitle.trim();
    if (!title) return;
    try {
      await addChapter(title);
      setNewTitle("");
      setShowInput(false);
    } catch {
      // 错误已在 store 中处理
    }
  };

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`确定删除章节「${title}」？`)) return;
    try {
      await removeChapter(id);
    } catch {
      // 错误已在 store 中处理
    }
  };

  return (
    <div className="w-[220px] bg-zinc-900 border-r border-zinc-800 flex flex-col h-full">
      {/* 标题栏 */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-300">章节</h3>
        <button
          onClick={() => setShowInput(!showInput)}
          className="text-zinc-500 hover:text-zinc-300 text-lg leading-none"
          title="新建章节"
        >
          +
        </button>
      </div>

      {/* 新建输入框 */}
      {showInput && (
        <div className="px-3 py-2 border-b border-zinc-800">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="章节标题..."
            className="w-full bg-zinc-800 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            autoFocus
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={handleAdd}
              className="flex-1 text-xs bg-zinc-700 hover:bg-zinc-600 text-zinc-300 py-1 rounded"
            >
              确定
            </button>
            <button
              onClick={() => { setShowInput(false); setNewTitle(""); }}
              className="flex-1 text-xs text-zinc-500 hover:text-zinc-400 py-1"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 章节列表 */}
      <div className="flex-1 overflow-y-auto">
        {loading && chapters.length === 0 && (
          <p className="text-zinc-600 text-xs px-4 py-3">加载中...</p>
        )}

        {!loading && chapters.length === 0 && (
          <p className="text-zinc-600 text-xs px-4 py-3">暂无章节</p>
        )}

        {chapters
          .sort((a, b) => a.order_index - b.order_index)
          .map((chapter) => (
            <div
              key={chapter.id}
              className={`group flex items-center px-4 py-2 cursor-pointer border-b border-zinc-800/50 ${
                selectedId === chapter.id
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
              onClick={() => selectChapter(chapter.id)}
            >
              <span className="flex-1 text-sm truncate">{chapter.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(chapter.id, chapter.title);
                }}
                className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 text-xs ml-2"
                title="删除"
              >
                x
              </button>
            </div>
          ))}
      </div>
    </div>
  );
}
