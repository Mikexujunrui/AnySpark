import { useEffect, useState } from "react";
import { useChapterStore } from "../stores/chapterStore";

export default function ChapterBar() {
  const { chapters, selectedId, loading, fetchChapters, selectChapter, addChapter } =
    useChapterStore();
  const [showInput, setShowInput] = useState(false);
  const [newTitle, setNewTitle] = useState("");

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
      // error handled in store
    }
  };

  const handleDelete = async (id: string, title: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除章节「${title}」？`)) return;
    try {
      await useChapterStore.getState().removeChapter(id);
    } catch {
      // error handled in store
    }
  };

  if (loading && chapters.length === 0) {
    return (
      <div className="h-9 bg-zinc-900 border-b border-zinc-800 flex items-center px-4">
        <span className="text-xs text-zinc-600">加载中...</span>
      </div>
    );
  }

  return (
    <div className="h-9 bg-zinc-900 border-b border-zinc-800 flex items-center shrink-0">
      {/* 章节横向滚动区 */}
      <div className="flex-1 flex items-center gap-1 px-3 overflow-x-auto scrollbar-thin">
        {chapters
          .sort((a, b) => a.order_index - b.order_index)
          .map((chapter) => (
            <div
              key={chapter.id}
              onClick={() => selectChapter(chapter.id)}
              className={`group flex items-center gap-1 px-2.5 py-1 rounded text-xs cursor-pointer whitespace-nowrap transition-colors ${
                selectedId === chapter.id
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
              }`}
            >
              <span>{chapter.title}</span>
              <button
                onClick={(e) => handleDelete(chapter.id, chapter.title, e)}
                className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 ml-0.5 text-[10px]"
                title="删除"
              >
                ×
              </button>
            </div>
          ))}

        {/* 新建按钮 */}
        {showInput ? (
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
                if (e.key === "Escape") { setShowInput(false); setNewTitle(""); }
              }}
              placeholder="章节标题..."
              className="w-24 bg-zinc-800 text-zinc-200 text-xs px-2 py-1 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              autoFocus
            />
            <button
              onClick={handleAdd}
              className="text-xs text-zinc-400 hover:text-zinc-200"
            >
              ✓
            </button>
            <button
              onClick={() => { setShowInput(false); setNewTitle(""); }}
              className="text-xs text-zinc-500 hover:text-zinc-400"
            >
              ×
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowInput(true)}
            className="px-2 py-1 text-xs text-zinc-600 hover:text-zinc-400 whitespace-nowrap"
          >
            + 章节
          </button>
        )}
      </div>
    </div>
  );
}
