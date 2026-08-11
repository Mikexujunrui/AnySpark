import { useCallback, useEffect, useRef, useState } from "react";
import {
  type LibraryBook,
  type RefItem,
  createLibraryBook,
  deleteLibraryBook,
  getReferences,
  importLibraryText,
  listLibrary,
  setReferences,
} from "../api/library";

/**
 * 参考书标签页（S86）：全局书库 + 项目选参考书。
 * 参考书不注入任何信息，仅供智能体按需检索（reference_lookup 工具）。
 */
export default function LibraryPanel({ bookId }: { bookId: string }) {
  const [library, setLibrary] = useState<LibraryBook[]>([]);
  const [refs, setRefs] = useState<RefItem[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPicker, setShowPicker] = useState(false);
  const [newName, setNewName] = useState("");
  const [importOpen, setImportOpen] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [libRes, refRes] = await Promise.all([listLibrary(), getReferences(bookId)]);
      setLibrary(libRes);
      setRefs(refRes);
      // 工作区其他项目（书架）
      try {
        const { apiGet } = await import("../api/client");
        const books = await apiGet<{ id: string; title: string }[]>("/api/books");
        setProjects((Array.isArray(books) ? books : []).map((b) => b.id).filter((id) => id !== bookId));
      } catch {
        setProjects([]);
      }
    } finally {
      setLoading(false);
    }
  }, [bookId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const saveRefs = async (next: { type: "library" | "project"; id: string }[]) => {
    const r = await setReferences(bookId, next);
    setRefs(r.refs);
  };

  const toggleRef = (type: "library" | "project", id: string) => {
    const exists = refs.some((r) => r.type === type && r.id === id);
    if (exists) {
      saveRefs(refs.filter((r) => !(r.type === type && r.id === id)).map((r) => ({ type: r.type, id: r.id })));
    } else {
      saveRefs([...refs.map((r) => ({ type: r.type, id: r.id })), { type, id }]);
    }
  };

  const onCreateBook = async () => {
    if (!newName.trim()) return;
    await createLibraryBook(newName.trim());
    setNewName("");
    loadData();
  };

  const onImportFile = async (bookId2: string, file: File) => {
    const text = await file.text();
    const r = await importLibraryText(bookId2, text, file.name.replace(/\.[^.]+$/, ""));
    setImportOpen(null);
    setImportText("");
    loadData();
    return r;
  };

  const onDeleteBook = async (bookId2: string) => {
    if (!window.confirm(`删除书库《${bookId2}》？引用关系一并清理。`)) return;
    await deleteLibraryBook(bookId2);
    loadData();
  };

  return (
    <div className="h-full flex flex-col min-h-0 p-4 space-y-4 overflow-y-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">参考书</h2>
          <p className="text-sm opacity-60">
            仅作智能体检索借鉴，不注入上下文——写作时可让 AI 按需翻书
          </p>
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => setShowPicker(!showPicker)}>
          {showPicker ? "收起" : "选择参考书"}
        </button>
      </div>

      {/* 已选参考书 */}
      <div className="space-y-2">
        {refs.length === 0 && (
          <div className="text-sm opacity-50 text-center py-6">未选参考书——点击"选择参考书"添加</div>
        )}
        {refs.map((r) => (
          <div key={`${r.type}-${r.id}`} className="card p-3 flex items-center justify-between">
            <div>
              <div className="font-medium">
                {r.name || r.id}
                <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-base-300">
                  {r.type === "library" ? "书库" : "项目"}
                </span>
              </div>
              <div className="text-xs opacity-50">
                {r.type === "library" ? `${r.chapters ?? 0} 章` : "工作区项目"}
              </div>
            </div>
            <button
              className="btn btn-xs btn-ghost text-error"
              onClick={() => toggleRef(r.type, r.id)}
            >
              移除
            </button>
          </div>
        ))}
      </div>

      {/* 选择器 */}
      {showPicker && (
        <div className="card p-4 space-y-4">
          <div>
            <h3 className="font-semibold mb-2">书库的书</h3>
            <div className="space-y-1.5">
              {library.map((b) => {
                const selected = refs.some((r) => r.type === "library" && r.id === b.id);
                return (
                  <label key={b.id} className="flex items-center justify-between text-sm">
                    <span>
                      {b.name}
                      <span className="ml-2 text-xs opacity-50">{b.chapters} 章</span>
                    </span>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleRef("library", b.id)}
                    />
                  </label>
                );
              })}
              {library.length === 0 && <div className="text-xs opacity-50">书库为空——先建书/导书</div>}
            </div>
          </div>
          <div>
            <h3 className="font-semibold mb-2">工作区其他项目</h3>
            <div className="space-y-1.5">
              {projects.map((pid) => {
                const selected = refs.some((r) => r.type === "project" && r.id === pid);
                return (
                  <label key={pid} className="flex items-center justify-between text-sm">
                    <span>{pid}</span>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleRef("project", pid)}
                    />
                  </label>
                );
              })}
              {projects.length === 0 && <div className="text-xs opacity-50">无其他项目</div>}
            </div>
          </div>
        </div>
      )}

      {/* 书库管理 */}
      <div className="card p-4 space-y-3">
        <h3 className="font-semibold">全局书库</h3>
        <div className="flex gap-2">
          <input
            className="input input-sm flex-1"
            placeholder="新书库书名"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onCreateBook()}
          />
          <button className="btn btn-sm" onClick={onCreateBook}>
            建书
          </button>
          <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>
            导入
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.markdown"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              // 无目标书时先建一本（书名=文件名）
              const target = library[0]?.id || (await createLibraryBook(f.name.replace(/\.[^.]+$/, ""))).id;
              await onImportFile(target, f);
              e.target.value = "";
            }}
          />
        </div>
        {importOpen && (
          <div className="space-y-2">
            <textarea
              className="textarea textarea-sm w-full"
              rows={5}
              placeholder="粘贴参考书文本（自动按章拆分）"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
            />
            <button className="btn btn-sm btn-primary" onClick={() => {
              importLibraryText(importOpen, importText);
              setImportOpen(null);
              setImportText("");
            }}>
              导入
            </button>
          </div>
        )}
        <div className="space-y-1.5">
          {library.map((b) => (
            <div key={b.id} className="flex items-center justify-between text-sm">
              <span>
                {b.name}
                <span className="ml-2 text-xs opacity-50">{b.chapters} 章</span>
              </span>
              <button className="btn btn-xs btn-ghost" onClick={() => setImportOpen(b.id)}>
                追加文本
              </button>
              <button className="btn btn-xs btn-ghost text-error" onClick={() => onDeleteBook(b.id)}>
                删除
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
