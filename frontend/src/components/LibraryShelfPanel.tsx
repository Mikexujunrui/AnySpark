import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./ui/Icon";
import {
  type LibraryBook,
  createLibraryBook,
  deleteLibraryBook,
  importLibraryText,
  listLibrary,
  refineLibrarySkill,
} from "../api/library";
import {
  type SkillDraft,
  deleteSkillDraft,
  listSkillDrafts,
  promoteSkillDraft,
} from "../api/skills";

/**
 * 书架级「书库」标签（S103）：全局参考书库管理 + 书库→技能提炼 + 草稿确认。
 * 全局功能放书架层（不依赖具体项目）——上传 txt → 提炼技能 → 确认转正全链路。
 */
export default function LibraryShelfPanel() {
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [drafts, setDrafts] = useState<SkillDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [refiningId, setRefiningId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [lib, dr] = await Promise.all([listLibrary(), listSkillDrafts()]);
      setBooks(lib);
      setDrafts(dr);
    } catch {
      setMsg("⚠️ 加载书库失败，请检查后端");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const onCreateBook = async () => {
    if (!newName.trim()) return;
    try {
      await createLibraryBook(newName.trim());
      setNewName("");
      loadData();
    } catch {
      setMsg("⚠️ 建书失败");
    }
  };

  const onImportFile = async (file: File) => {
    const text = await file.text();
    const title = file.name.replace(/\.[^.]+$/, "");
    // 无书时自动建一本（书名=文件名）
    let target = books[0]?.id;
    if (!target) {
      const b = await createLibraryBook(title);
      target = b.id;
    }
    try {
      const r = await importLibraryText(target, text, title);
      setMsg(`✅ 已导入《${title}》：拆成 ${r.chapters} 章`);
      loadData();
    } catch {
      setMsg("⚠️ 导入失败（文件过大或格式异常）");
    }
  };

  const onRefine = async (bookId: string, name: string) => {
    setRefiningId(bookId);
    setMsg("");
    try {
      const r = await refineLibrarySkill(bookId);
      setMsg(`✅ 已从《${name}》提炼技能草稿「${r.draft?.name || ""}」——确认后生效`);
      loadData();
    } catch (e: any) {
      const detail = String(e?.message || "");
      setMsg(`⚠️ 提炼失败：${detail.includes("409") ? "已存在同名草稿/技能，先确认或删除" : "请稍后重试"}`);
    } finally {
      setRefiningId(null);
    }
  };

  const onPromote = async (d: SkillDraft) => {
    try {
      await promoteSkillDraft(d.id);
      setMsg(`✅ 技能「${d.name}」已生效`);
      loadData();
    } catch {
      setMsg("⚠️ 确认失败");
    }
  };

  const onDeleteDraft = async (d: SkillDraft) => {
    if (!window.confirm(`删除草稿「${d.name}」？`)) return;
    try {
      await deleteSkillDraft(d.id);
      loadData();
    } catch {
      setMsg("⚠️ 删除失败");
    }
  };

  const onDeleteBook = async (b: LibraryBook) => {
    if (!window.confirm(`删除书库《${b.name}》？引用关系一并清理。`)) return;
    try {
      await deleteLibraryBook(b.id);
      loadData();
    } catch {
      setMsg("⚠️ 删除书失败");
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Icon name="book" size={28} /> 书库
          </h1>
          <p className="text-zinc-500 mt-1 text-sm">
            上传参考书 → 一键提炼成写作技能（拆书模式）→ 草稿确认生效。全链路在此完成
          </p>
        </div>
        <div className="flex gap-2">
          <input
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500"
            placeholder="新书库书名"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onCreateBook()}
          />
          <button
            onClick={onCreateBook}
            className="bg-zinc-800 hover:bg-zinc-700 active:scale-95 text-zinc-300 px-3 py-2 rounded-lg transition-all text-sm"
          >
            建书
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            className="bg-accent text-white px-3 py-2 rounded-lg hover:bg-accent-hover active:scale-95 transition-all text-sm flex items-center gap-2"
          >
            <Icon name="upload" size={14} /> 导入 txt
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.markdown"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              await onImportFile(f);
              e.target.value = "";
            }}
          />
        </div>
      </header>

      {msg && (
        <div className="mb-6 bg-zinc-800/60 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-300">
          {msg}
        </div>
      )}

      {/* 技能草稿区：确认转正 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Icon name="clipboard-list" size={18} /> 技能草稿
          <span className="text-xs text-zinc-500">（提炼后在此确认生效；AI 写作时按需调用）</span>
        </h2>
        {drafts.length === 0 ? (
          <div className="text-sm text-zinc-500 bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-6 text-center">
            暂无草稿——从下方书库点「提炼技能」，或对话让 AI 提炼
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {drafts.map((d) => (
              <div key={d.id} className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm text-zinc-200">{d.name}</span>
                  {d.source && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                      {d.source === "library" ? "书库提炼" : d.source}
                    </span>
                  )}
                  {d.target && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-900/40 text-sky-300">
                      {d.target}
                    </span>
                  )}
                </div>
                {d.description && (
                  <p className="text-xs text-zinc-400 mb-2 line-clamp-2">{d.description}</p>
                )}
                <p className="text-xs text-zinc-500 mb-3 line-clamp-3 whitespace-pre-wrap">{d.content}</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => onPromote(d)}
                    className="bg-emerald-800/60 text-emerald-300 border border-emerald-800 rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-emerald-800/80 transition-colors"
                  >
                    <Icon name="check" size={12} /> 确认生效
                  </button>
                  <button
                    onClick={() => onDeleteDraft(d)}
                    className="text-zinc-500 hover:text-red-400 px-2 py-1.5 text-xs rounded-lg transition-colors"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 全局书库 */}
      <section>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Icon name="book" size={18} /> 全局书库
          <span className="text-xs text-zinc-500">（{books.length} 本）</span>
        </h2>
        {loading ? (
          <div className="text-sm text-zinc-500">加载中…</div>
        ) : books.length === 0 ? (
          <div className="text-sm text-zinc-500 bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-6 text-center">
            书库为空——点「导入 txt」上传《斗破苍穹》这类参考书
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {books.map((b) => (
              <div key={b.id} className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col">
                <div className="font-medium text-sm text-zinc-200 mb-1">{b.name}</div>
                <div className="text-xs text-zinc-500 mb-3">
                  {b.chapters} 章{b.source ? ` · ${b.source}` : ""}
                </div>
                <div className="mt-auto flex gap-2">
                  <button
                    onClick={() => onRefine(b.id, b.name)}
                    disabled={refiningId === b.id}
                    className="bg-accent text-white rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-40 flex items-center gap-1"
                  >
                    {refiningId === b.id ? (
                      <Icon name="loader" size={12} />
                    ) : (
                      <Icon name="pen-tool" size={12} />
                    )}
                    {refiningId === b.id ? "提炼中…" : "提炼技能"}
                  </button>
                  <button
                    onClick={() => onDeleteBook(b)}
                    className="text-zinc-500 hover:text-red-400 px-2 py-1.5 text-xs rounded-lg transition-colors ml-auto"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
