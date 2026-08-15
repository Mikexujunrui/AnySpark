import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./ui/Icon";
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

// S105 美术重做：对齐老版——渐变顶条卡片 / 空状态引导 / 彩色标签
const GRADIENTS = [
  "from-rose-600 to-orange-500",
  "from-violet-600 to-indigo-500",
  "from-emerald-600 to-teal-500",
  "from-amber-500 to-yellow-400",
  "from-cyan-500 to-blue-500",
  "from-fuchsia-600 to-pink-500",
];

function hashColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return GRADIENTS[h % GRADIENTS.length];
}

/**
 * 项目页「参考书」标签（S86）：全局书库 + 项目选参考书（AI 按需检索借鉴）。
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
    <div className="h-full flex flex-col min-h-0 overflow-y-auto">
      {/* 渐变横幅头部 */}
      <div className="relative overflow-hidden border-b border-zinc-800 bg-zinc-950 shrink-0">
        <div className="absolute -top-20 left-1/3 w-64 h-64 rounded-full bg-violet-600/15 blur-3xl pointer-events-none" />
        <div className="relative px-5 py-5 flex items-center justify-between">
          <div>
            <h2 className="font-semibold flex items-center gap-2">
              <span className="text-violet-400"><Icon name="book-open" size={18} /></span>
              参考书
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              仅作 AI 检索借鉴，不注入上下文——写作时可让 AI 按需翻书
            </p>
            <div className="flex gap-3 mt-1.5 text-[10px] text-zinc-500">
              <span className="flex items-center gap-1">
                <span className="px-1.5 py-0.5 rounded-full bg-sky-900/40 text-sky-300">书库·低级</span>
                仅原文片段检索
              </span>
              <span className="flex items-center gap-1">
                <span className="px-1.5 py-0.5 rounded-full bg-amber-900/40 text-amber-300">项目·高级</span>
                原文 + 图谱实体/关系 + 设定档条目（只读）
              </span>
            </div>
          </div>
          <button
            onClick={() => setShowPicker(!showPicker)}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-3 py-1.5 rounded-lg transition-colors text-xs font-medium flex items-center gap-1.5"
          >
            <Icon name="plus" size={13} /> {showPicker ? "收起" : "选择参考书"}
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* 已选参考书 */}
        <section>
          <h3 className="text-xs font-semibold text-zinc-400 mb-2 flex items-center gap-1.5">
            <Icon name="check-circle" size={13} className="text-emerald-400" /> 本项目参考书
          </h3>
          {refs.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-zinc-600 rounded-xl border border-dashed border-zinc-800">
              <Icon name="book-open" size={26} className="mb-2 text-zinc-700" />
              <p className="text-xs mb-3">未选参考书——点击"选择参考书"添加</p>
            </div>
          )}
          <div className="space-y-2">
            {refs.map((r) => (
              <div key={`${r.type}-${r.id}`} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors">
                <div className={`h-0.5 bg-gradient-to-r ${hashColor(r.name || r.id)}`} />
                <div className="p-3 flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <Icon name="book" size={14} className="text-zinc-500 shrink-0" />
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-zinc-200 truncate">{r.name || r.id}</div>
                      <div className="text-[10px] text-zinc-500">
                        {r.type === "library" ? `${r.chapters ?? 0} 章` : "工作区项目"}
                      </div>
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${
                      r.type === "library" ? "bg-sky-900/40 text-sky-300" : "bg-amber-900/40 text-amber-300"
                    }`}>
                      {r.type === "library" ? "书库·低级" : "项目·高级"}
                    </span>
                    <span
                      className="text-[10px] text-zinc-600 shrink-0"
                      title={r.type === "library" ? "低级参考书：仅原文片段检索" : "高级参考书：原文 + 图谱实体/关系 + 设定档条目（只读）"}
                    >
                      {r.type === "library" ? "仅原文" : "图谱+设定"}
                    </span>
                  </div>
                  <button
                    className="text-zinc-500 hover:text-red-400 p-1 rounded transition-colors"
                    onClick={() => toggleRef(r.type, r.id)}
                    title="移除参考书"
                  >
                    <Icon name="x" size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 选择器 */}
        {showPicker && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
            <div>
              <h4 className="text-xs font-semibold text-zinc-300 mb-2 flex items-center gap-1.5">
                <Icon name="book" size={12} className="text-sky-400" /> 书库的书
              </h4>
              <div className="space-y-1.5">
                {library.map((b) => {
                  const selected = refs.some((r) => r.type === "library" && r.id === b.id);
                  return (
                    <label key={b.id} className="flex items-center justify-between text-sm px-2 py-1.5 rounded-lg hover:bg-zinc-800/60 transition-colors cursor-pointer">
                      <span className="flex items-center gap-2 min-w-0">
                        <span className={`w-1.5 h-4 rounded-full bg-gradient-to-b ${hashColor(b.name)}`} />
                        <span className="truncate text-zinc-300">{b.name}</span>
                        <span className="text-[10px] text-zinc-500 shrink-0">{b.chapters} 章</span>
                      </span>
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleRef("library", b.id)}
                        className="accent-violet-500"
                      />
                    </label>
                  );
                })}
                {library.length === 0 && <div className="text-xs text-zinc-600 py-2">书库为空——去书架「书库」标签导入</div>}
              </div>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-zinc-300 mb-2 flex items-center gap-1.5">
                <Icon name="folder" size={12} className="text-amber-400" /> 工作区其他项目
              </h4>
              <div className="space-y-1.5">
                {projects.map((pid) => {
                  const selected = refs.some((r) => r.type === "project" && r.id === pid);
                  return (
                    <label key={pid} className="flex items-center justify-between text-sm px-2 py-1.5 rounded-lg hover:bg-zinc-800/60 transition-colors cursor-pointer">
                      <span className="text-zinc-300">{pid}</span>
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleRef("project", pid)}
                        className="accent-violet-500"
                      />
                    </label>
                  );
                })}
                {projects.length === 0 && <div className="text-xs text-zinc-600 py-2">无其他项目</div>}
              </div>
            </div>
          </section>
        )}

        {/* 全局书库管理 */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
            <Icon name="book" size={13} className="text-violet-400" /> 全局书库
          </h3>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500 transition-colors"
              placeholder="新书库书名"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onCreateBook()}
            />
            <button
              onClick={onCreateBook}
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors text-xs"
            >
              建书
            </button>
            <button
              onClick={() => fileRef.current?.click()}
              className="bg-gradient-to-r from-violet-600 to-indigo-500 hover:from-violet-500 hover:to-indigo-400 text-white px-3 py-1.5 rounded-lg transition-all text-xs font-medium flex items-center gap-1.5"
            >
              <Icon name="upload" size={12} /> 导入
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.markdown"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                // S158e：同名覆盖/独立建库（此前 library[0] 把新书内容塞进第一本）
                const title = f.name.replace(/\.[^.]+$/, "");
                let target = library.find((b) => b.name === title)?.id;
                if (!target) {
                  target = (await createLibraryBook(title)).id;
                }
                await onImportFile(target, f);
                e.target.value = "";
              }}
            />
          </div>
          {importOpen && (
            <div className="space-y-2">
              <textarea
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500"
                rows={5}
                placeholder="粘贴参考书文本（自动按章拆分）"
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
              <button
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg text-xs"
                onClick={() => {
                  importLibraryText(importOpen, importText);
                  setImportOpen(null);
                  setImportText("");
                }}
              >
                导入
              </button>
            </div>
          )}
          {loading ? (
            <div className="text-xs text-zinc-500 py-2 flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-zinc-700 border-t-violet-400 rounded-full animate-spin" />
              加载中…
            </div>
          ) : (
            <div className="space-y-1.5">
              {library.map((b) => (
                <div key={b.id} className="flex items-center justify-between text-sm px-2 py-1.5 rounded-lg hover:bg-zinc-800/60 transition-colors">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className={`w-1.5 h-4 rounded-full bg-gradient-to-b ${hashColor(b.name)}`} />
                    <span className="truncate text-zinc-300">{b.name}</span>
                    <span className="text-[10px] text-zinc-500 shrink-0">{b.chapters} 章</span>
                  </span>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setImportOpen(b.id)}
                      className="text-[10px] text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded transition-colors"
                    >
                      追加文本
                    </button>
                    <button
                      onClick={() => onDeleteBook(b.id)}
                      className="text-[10px] text-zinc-500 hover:text-red-400 px-2 py-1 rounded transition-colors"
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
              {library.length === 0 && <div className="text-xs text-zinc-600 py-2">书库为空——点「导入」上传 txt</div>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
