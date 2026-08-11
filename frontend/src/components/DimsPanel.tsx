import { useEffect, useState } from "react";
import { useDimStore } from "../stores/dimStore";

interface DimsPanelProps {
  open: boolean;
  onClose: () => void;
}

// S50 探索维度管理：探索该从哪些维度发散取决于用户与作品（可增删改/开关）
export default function DimsPanel({ open, onClose }: DimsPanelProps) {
  const dims = useDimStore((s) => s.dims);
  const loading = useDimStore((s) => s.loading);
  const error = useDimStore((s) => s.error);
  const fetchDims = useDimStore((s) => s.fetchDims);
  const add = useDimStore((s) => s.add);
  const toggle = useDimStore((s) => s.toggle);
  const remove = useDimStore((s) => s.remove);

  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    if (open) fetchDims();
  }, [open, fetchDims]);

  if (!open) return null;

  const handleAdd = async () => {
    if (!newName.trim()) return;
    try {
      await add(newName.trim());
      setNewName("");
      setShowAdd(false);
    } catch (e) {
      alert(String(e));
    }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await toggle(id, !enabled);
    } catch (e) {
      alert(String(e));
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm("确定删除这个探索维度？")) {
      try {
        await remove(id);
      } catch (e) {
        alert(String(e));
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">探索维度</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAdd(!showAdd)}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {showAdd ? "取消" : "+ 新增"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 新增表单 */}
        {showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="新探索维度名（如：科技、魔法体系）"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <button
              onClick={handleAdd}
              disabled={!newName.trim()}
              className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
            >
              添加
            </button>
          </div>
        )}

        {error && <p className="px-4 pt-2 text-xs text-red-400">{error}</p>}

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : dims.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无探索维度</p>
          ) : (
            dims.map((d) => (
              <div
                key={d.id}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(d.id, d.enabled === 1)}
                    className={`relative w-8 h-4 rounded-full transition-colors ${
                      d.enabled === 1 ? "bg-blue-600" : "bg-zinc-700"
                    }`}
                    title={d.enabled === 1 ? "已启用" : "已停用"}
                  >
                    <span
                      className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
                        d.enabled === 1 ? "left-4" : "left-0.5"
                      }`}
                    />
                  </button>
                  <span
                    className={`text-sm ${
                      d.enabled === 1 ? "text-zinc-200" : "text-zinc-500"
                    }`}
                  >
                    {d.name}
                  </span>
                </div>
                <button
                  onClick={() => handleDelete(d.id)}
                  className="p-1 text-zinc-600 hover:text-red-400 rounded"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
