import { useState, useEffect } from "react";
import { useManualStore } from "../stores/manualStore";
import { listManualNotices, type ManualNotice } from "../api/manual";

type Category = "collab" | "style" | "habit";

const CATEGORY_LABELS: Record<Category, string> = {
  collab: "协作",
  style: "文风",
  habit: "习惯",
};

const CATEGORY_COLORS: Record<Category, string> = {
  collab: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  style: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  habit: "bg-green-500/20 text-green-400 border-green-500/30",
};

interface ManualPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function ManualPanel({ open, onClose }: ManualPanelProps) {
  const entries = useManualStore((s) => s.entries);
  const loading = useManualStore((s) => s.loading);
  const filter = useManualStore((s) => s.filter);
  const fetchEntries = useManualStore((s) => s.fetchEntries);
  const addEntry = useManualStore((s) => s.addEntry);
  const editEntry = useManualStore((s) => s.editEntry);
  const removeEntry = useManualStore((s) => s.removeEntry);
  const setFilter = useManualStore((s) => s.setFilter);

  const [showAdd, setShowAdd] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newCategory, setNewCategory] = useState<Category>("collab");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [view, setView] = useState<"entries" | "notices">("entries");
  const [notices, setNotices] = useState<ManualNotice[]>([]);
  const [noticesLoading, setNoticesLoading] = useState(false);

  const loadNotices = async () => {
    setNoticesLoading(true);
    try {
      setNotices(await listManualNotices(50));
    } catch (e) {
      console.error("load notices failed", e);
    }
    setNoticesLoading(false);
  };

  useEffect(() => {
    if (open) fetchEntries();
  }, [open, fetchEntries]);

  useEffect(() => {
    if (open && view === "notices") loadNotices();
  }, [open, view]);

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    await addEntry(newContent.trim(), newCategory);
    setNewContent("");
    setShowAdd(false);
  };

  const handleEdit = async (id: string) => {
    if (!editContent.trim()) return;
    await editEntry(id, { content: editContent.trim() });
    setEditingId(null);
    setEditContent("");
  };

  const handleToggleLock = async (id: string, currentLocked: boolean) => {
    await editEntry(id, { locked: !currentLocked });
  };

  const handleDelete = async (id: string) => {
    if (confirm("确定删除这条心智条目？")) {
      await removeEntry(id);
    }
  };

  const filteredEntries = filter === "all" ? entries : entries.filter((e) => e.category === filter);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">心智</h2>
          <div className="flex items-center gap-2">
            <div className="flex rounded bg-zinc-800 p-0.5">
              {(["entries", "notices"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`px-2 py-0.5 rounded text-xs ${view === v ? "bg-zinc-600 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}
                >
                  {v === "entries" ? "条目" : "通知"}
                </button>
              ))}
            </div>
            {view === "entries" && (
              <button
                onClick={() => setShowAdd(!showAdd)}
                className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
              >
                {showAdd ? "取消" : "+ 新增"}
              </button>
            )}
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 新增表单 */}
        {view === "entries" && showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="输入心智条目内容..."
              rows={3}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <div className="flex items-center gap-2">
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as Category)}
                className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
              >
                <option value="collab">协作</option>
                <option value="style">文风</option>
                <option value="habit">习惯</option>
              </select>
              <button
                onClick={handleAdd}
                disabled={!newContent.trim()}
                className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
              >
                添加
              </button>
            </div>
          </div>
        )}

        {/* 筛选 */}
        {view === "entries" && (
        <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800">
          {(["all", "collab", "style", "habit"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2 py-1 rounded ${
                filter === f
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {f === "all" ? "全部" : CATEGORY_LABELS[f]}
            </button>
          ))}
        </div>
        )}

        {/* 内容 */}
        {view === "notices" ? (
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
            {noticesLoading ? (
              <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
            ) : notices.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无变更通知</p>
            ) : (
              notices.map((n) => (
                <div key={n.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300">
                      {{ add: "新增", update: "修改", delete: "删除" }[n.action] || n.action}
                    </span>
                    <span className="text-[10px] text-zinc-600">{n.source || ""}</span>
                  </div>
                  {n.old_content !== undefined && n.new_content !== undefined && (
                    <div className="text-[11px] space-y-1">
                      <p className="text-zinc-600 line-through">{n.old_content}</p>
                      <p className="text-zinc-300">→ {n.new_content}</p>
                    </div>
                  )}
                  {n.content && <p className="text-xs text-zinc-400">{n.content}</p>}
                  {n.created_at && <p className="text-[10px] text-zinc-600">{n.created_at}</p>}
                </div>
              ))
            )}
          </div>
        ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : filteredEntries.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无心智条目</p>
          ) : (
            filteredEntries.map((entry) => (
              <div
                key={entry.id}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2"
              >
                {/* 分类标签 + 操作 */}
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      CATEGORY_COLORS[entry.category]
                    }`}
                  >
                    {CATEGORY_LABELS[entry.category]}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleToggleLock(entry.id, !!entry.locked)}
                      className={`p-1 rounded ${
                        entry.locked
                          ? "text-yellow-500 hover:text-yellow-400"
                          : "text-zinc-600 hover:text-zinc-400"
                      }`}
                      title={entry.locked ? "已锁定" : "未锁定"}
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        {entry.locked ? (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        ) : (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
                        )}
                      </svg>
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(entry.id);
                        setEditContent(entry.content);
                      }}
                      className="p-1 text-zinc-600 hover:text-zinc-400 rounded"
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(entry.id)}
                      className="p-1 text-zinc-600 hover:text-red-400 rounded"
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* 内容 */}
                {editingId === entry.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={3}
                      className="w-full bg-zinc-900 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-600 focus:outline-none resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEdit(entry.id)}
                        className="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-300 whitespace-pre-wrap">{entry.content}</p>
                )}
              </div>
            ))
          )}
        </div>
        )}
      </div>
    </div>
  );
}
