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

// 老版美术：渐变配色轮换（顶部条/封面块取色）
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
 * 书架级「书库」标签（S103）：全局参考书库管理 + 书库→技能提炼 + 草稿确认。
 * S105 美术重做：对齐老版——渐变横幅 + 渐变顶条封面墙 + 拖拽导入 + 空状态引导。
 */
export default function LibraryShelfPanel() {
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [drafts, setDrafts] = useState<SkillDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [refiningId, setRefiningId] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const flash = (kind: "ok" | "err", text: string) => {
    setMsg({ kind, text });
    window.setTimeout(() => setMsg(null), 5000);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [lib, dr] = await Promise.all([listLibrary(), listSkillDrafts()]);
      setBooks(lib);
      setDrafts(dr);
    } catch {
      flash("err", "加载书库失败，请检查后端");
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
      flash("ok", `已建书《${newName.trim()}》——导入 txt 填充内容`);
      loadData();
    } catch {
      flash("err", "建书失败");
    }
  };

  const onImportFile = async (file: File) => {
    const text = await file.text();
    const title = file.name.replace(/\.[^.]+$/, "");
    let target = books[0]?.id;
    if (!target) {
      const b = await createLibraryBook(title);
      target = b.id;
    }
    try {
      const r = await importLibraryText(target, text, title);
      flash("ok", `《${title}》导入成功：拆成 ${r.chapters} 章`);
      loadData();
    } catch {
      flash("err", "导入失败（文件过大或格式异常）");
    }
  };

  const onRefine = async (bookId: string, name: string) => {
    setRefiningId(bookId);
    setMsg(null);
    try {
      const r = await refineLibrarySkill(bookId);
      flash("ok", `已从《${name}》提炼出技能「${r.draft?.name || ""}」——下方草稿区确认生效`);
      loadData();
    } catch (e: any) {
      const detail = String(e?.message || "");
      flash(
        "err",
        detail.includes("409") ? "已存在同名草稿/技能，先确认或删除旧的" : "提炼失败，请稍后重试"
      );
    } finally {
      setRefiningId(null);
    }
  };

  const onPromote = async (d: SkillDraft) => {
    try {
      await promoteSkillDraft(d.id);
      flash("ok", `技能「${d.name}」已生效——写作时 AI 按需调用`);
      loadData();
    } catch {
      flash("err", "确认失败");
    }
  };

  const onDeleteDraft = async (d: SkillDraft) => {
    if (!window.confirm(`删除草稿「${d.name}」？`)) return;
    try {
      await deleteSkillDraft(d.id);
      loadData();
    } catch {
      flash("err", "删除失败");
    }
  };

  const onDeleteBook = async (b: LibraryBook) => {
    if (!window.confirm(`删除书库《${b.name}》？引用关系一并清理。`)) return;
    try {
      await deleteLibraryBook(b.id);
      loadData();
    } catch {
      flash("err", "删除书失败");
    }
  };

  return (
    <div
      className="min-h-screen"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) void onImportFile(f);
      }}
    >
      {/* 渐变横幅头部 */}
      <div className="relative overflow-hidden bg-zinc-950 border-b border-zinc-800">
        <div className="absolute -top-32 left-1/4 w-96 h-96 rounded-full bg-violet-600/20 blur-3xl pointer-events-none" />
        <div className="absolute -top-24 right-1/4 w-80 h-80 rounded-full bg-sky-600/10 blur-3xl pointer-events-none" />
        <div className="relative max-w-6xl mx-auto px-6 py-10">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
                <span className="bg-gradient-to-r from-violet-400 to-sky-400 bg-clip-text text-transparent">
                  <Icon name="book" size={28} />
                </span>
                书库
              </h1>
              <p className="text-zinc-500 mt-1.5 text-sm">
                上传参考书 → 一键提炼成写作技能（拆书模式）→ 草稿确认生效。整条链路在此完成
              </p>
            </div>
            <div className="flex gap-2 items-center">
              <input
                className="bg-zinc-900/80 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500 transition-colors w-44"
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
                className="bg-gradient-to-r from-violet-600 to-indigo-500 hover:from-violet-500 hover:to-indigo-400 active:scale-95 text-white px-4 py-2 rounded-lg transition-all text-sm font-medium flex items-center gap-2 shadow-lg shadow-violet-900/30"
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
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* 消息条 */}
        {msg && (
          <div className={`mb-6 rounded-lg px-4 py-2.5 text-sm border flex items-center gap-2 ${
            msg.kind === "ok"
              ? "bg-emerald-950/40 border-emerald-800/50 text-emerald-300"
              : "bg-rose-950/40 border-rose-800/50 text-rose-300"
          }`}>
            <Icon name={msg.kind === "ok" ? "check-circle" : "alert-circle"} size={14} />
            {msg.text}
          </div>
        )}

        {/* 拖拽提示 */}
        {dragOver && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm pointer-events-none">
            <div className="border-2 border-dashed border-violet-500 rounded-2xl px-16 py-10 text-center bg-zinc-900/60">
              <Icon name="upload" size={36} className="text-violet-400 mx-auto mb-3" />
              <p className="text-violet-300 font-medium">松开导入 txt 到书库</p>
            </div>
          </div>
        )}

        {/* 技能草稿区 */}
        <section className="mb-12">
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <span className="text-violet-400"><Icon name="clipboard-list" size={18} /></span>
              技能草稿
            </h2>
            <span className="text-xs text-zinc-500">（提炼后在此确认生效；AI 写作时按需调用）</span>
            {drafts.length > 0 && (
              <span className="ml-auto text-xs bg-violet-900/40 text-violet-300 px-2 py-0.5 rounded-full">
                {drafts.length} 条待确认
              </span>
            )}
          </div>
          {drafts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-14 text-zinc-600 rounded-xl border border-dashed border-zinc-800">
              <Icon name="clipboard-list" size={32} className="mb-3 text-zinc-700" />
              <p className="text-sm mb-1">暂无技能草稿</p>
              <p className="text-xs text-zinc-600 mb-4">
                从下方书库点「提炼技能」，或对话里说"把《某书》提炼成技能"
              </p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {drafts.map((d) => (
                <div key={d.id} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors">
                  <div className={`h-1 bg-gradient-to-r ${hashColor(d.name)}`} />
                  <div className="p-4">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="font-medium text-sm text-zinc-200">{d.name}</span>
                      {d.source && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
                          {d.source === "library" ? "书库提炼" : d.source}
                        </span>
                      )}
                      {d.target && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                          d.target === "main" ? "bg-amber-900/40 text-amber-300"
                          : d.target === "both" ? "bg-violet-900/40 text-violet-300"
                          : "bg-sky-900/40 text-sky-300"
                        }`}>
                          {d.target === "main" ? "主循环" : d.target === "both" ? "双端" : "写作"}
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
                        className="bg-emerald-800/60 text-emerald-300 border border-emerald-800 rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-emerald-800/80 active:scale-95 transition-all flex items-center gap-1"
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
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 全局书库封面墙 */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <span className="text-sky-400"><Icon name="book" size={18} /></span>
              全局书库
            </h2>
            <span className="text-xs text-zinc-500">（{books.length} 本 · 拖拽文件到页面即导入）</span>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 text-zinc-500 text-sm py-10">
              <div className="w-5 h-5 border-2 border-zinc-700 border-t-violet-400 rounded-full animate-spin" role="status" />
              加载书库…
            </div>
          ) : books.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-zinc-600 rounded-xl border border-dashed border-zinc-800">
              <Icon name="book" size={36} className="mb-3 text-zinc-700" />
              <p className="text-sm mb-1">书库还是空的</p>
              <p className="text-xs text-zinc-600 mb-5">上传《斗破苍穹》这类参考书，一键提炼成写作技能</p>
              <button
                onClick={() => fileRef.current?.click()}
                className="bg-gradient-to-r from-violet-600 to-indigo-500 hover:from-violet-500 hover:to-indigo-400 active:scale-95 text-white px-4 py-2 rounded-lg transition-all text-sm font-medium flex items-center gap-2"
              >
                <Icon name="upload" size={14} /> 导入 txt
              </button>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {books.map((b) => (
                <div key={b.id} className="group bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 hover:shadow-xl hover:shadow-zinc-900/50 hover:-translate-y-0.5 transition-all">
                  <div className={`h-1 bg-gradient-to-r ${hashColor(b.name)}`} />
                  {/* 封面块 */}
                  <div className={`px-5 pt-5 pb-4 bg-gradient-to-br ${hashColor(b.name)}/20 relative overflow-hidden`}>
                    <div className="absolute -right-6 -top-6 w-24 h-24 rounded-full bg-white/5 blur-xl" />
                    <div className="text-3xl font-bold text-zinc-100/90">{b.name.slice(0, 1)}</div>
                    <div className="mt-2 text-sm font-semibold text-zinc-100 line-clamp-1">{b.name}</div>
                    <div className="flex gap-2 text-[10px] text-zinc-400 mt-1.5">
                      <span className="bg-zinc-900/60 rounded-full px-2 py-0.5">{b.chapters} 章</span>
                      {b.source && <span className="bg-zinc-900/60 rounded-full px-2 py-0.5">{b.source}</span>}
                    </div>
                  </div>
                  {/* 操作条 */}
                  <div className="flex items-center gap-2 p-3 bg-zinc-950/40">
                    <button
                      onClick={() => onRefine(b.id, b.name)}
                      disabled={refiningId === b.id}
                      className="flex-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 rounded-lg px-3 py-2 text-xs font-medium transition-all active:scale-95 flex items-center justify-center gap-1.5"
                    >
                      {refiningId === b.id ? (
                        <><span className="w-3.5 h-3.5 border-2 border-zinc-500 border-t-zinc-200 rounded-full animate-spin" /> 提炼中…</>
                      ) : (
                        <><Icon name="pen-tool" size={12} /> 提炼技能</>
                      )}
                    </button>
                    <button
                      onClick={() => onDeleteBook(b)}
                      className="text-zinc-600 hover:text-red-400 px-2 py-2 text-xs rounded-lg transition-colors"
                      title="删除此书"
                    >
                      <Icon name="x" size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
