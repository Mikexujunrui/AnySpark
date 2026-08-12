import { useState, useEffect } from "react";
import PanelHeader from "./ui/PanelHeader";
import { useBiasStore } from "../stores/biasStore";
import ConfirmModal from "./ui/ConfirmModal";
import Icon from "./ui/Icon";

interface BiasPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
}

type Source = "ai" | "user";
type MindView = "bias" | "memory";

interface ManualEntry { id: string; content: string; category?: string; locked?: boolean; activity?: string; created_at?: string }

const SOURCE_LABELS: Record<Source, string> = {
  ai: "AI 自述",
  user: "用户修正",
};

const SOURCE_COLORS: Record<Source, string> = {
  ai: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  user: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

// AI 倾向档案面板（双向黑盒：用户应能看到 AI 的倾向）
export default function BiasPanel({ open, onClose, embedded = false }: BiasPanelProps) {
  const items = useBiasStore((s) => s.items);
  const loading = useBiasStore((s) => s.loading);
  const fetchBias = useBiasStore((s) => s.fetchBias);
  const add = useBiasStore((s) => s.add);
  const update = useBiasStore((s) => s.update);
  const remove = useBiasStore((s) => s.remove);

  const [showAdd, setShowAdd] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newSource, setNewSource] = useState<Source>("ai");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  // S102：人类手动编辑（内联编辑态：条目 id + 草稿）
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editSource, setEditSource] = useState<Source>("ai");
  // 记忆视图（心智条目，与倾向互为对立：记忆=AI 学到的，倾向=AI 自述的）
  const [view, setView] = useState<MindView>("bias");
  const [manual, setManual] = useState<ManualEntry[]>([]);
  const [manualLoading, setManualLoading] = useState(false);
  // S103：说明书式目录——分类章节折叠状态
  const [collapsedCats, setCollapsedCats] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (open) fetchBias();
  }, [open, fetchBias]);

  const loadManual = async () => {
    setManualLoading(true)
    try {
      const res = await fetch("/api/manual")
      const d = await res.json()
      setManual(Array.isArray(d) ? d : [])
    } catch { /* 静默 */ }
    setManualLoading(false)
  }

  useEffect(() => {
    if (open && view === "memory") loadManual()
  }, [open, view]);

  const toggleLock = async (id: string, locked: boolean) => {
    try {
      await fetch(`/api/manual/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ locked: !locked }) })
      setManual(prev => prev.map(m => m.id === id ? { ...m, locked: !locked } : m))
    } catch { /* 静默 */ }
  }

  // S103/S104：说明书式目录——**动态分组**（数据里有几类就显示几章，
  // 未来 AI 提炼新类别自动出现新章节，契合「条目/类别非常多的说明书」设想）
  const CATEGORY_META: Record<string, { label: string; icon: string; color: string; desc: string }> = {
    style: { label: "文风", icon: "pen-tool", color: "text-purple-400", desc: "写作风格偏好" },
    habit: { label: "习惯", icon: "zap", color: "text-amber-400", desc: "写作习惯/雷区" },
    collab: { label: "协作", icon: "users", color: "text-sky-400", desc: "协作方式约定" },
  };
  // 稳定排序：collab/style/habit 在前，未知类别按出现顺序在后
  const CATEGORY_ORDER = ["collab", "style", "habit"];
  const seenCats = [...new Set(manual.map(m => m.category || "style"))];
  const catalog = seenCats
    .sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a);
      const ib = CATEGORY_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    })
    .map(cat => {
      const meta = CATEGORY_META[cat] || { label: cat, icon: "folder", color: "text-zinc-400", desc: "" };
      const items = manual.filter(m => (m.category || "style") === cat);
      return { key: cat, ...meta, items, count: items.length };
    });

  if (!open) return null;

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    try {
      await add(newContent.trim(), newSource);
      setNewContent("");
      setShowAdd(false);
    } catch {
      // 失败保留输入，提示由 console 输出
    }
  };

  const handleDelete = async (id: string) => {
    setPendingDelete(id);
  };

  const handleDeleteConfirm = async () => {
    if (!pendingDelete) return;
    await remove(pendingDelete);
    setPendingDelete(null);
  };

  // S102：进入编辑态（回填草稿）
  const startEdit = (entry: { id: string; content: string; source: string }) => {
    setEditingId(entry.id);
    setEditContent(entry.content);
    setEditSource((entry.source as Source) || "ai");
  };

  const saveEdit = async () => {
    if (!editingId || !editContent.trim()) return;
    try {
      await update(editingId, editContent.trim(), editSource);
      setEditingId(null);
    } catch {
      // 保存失败保留编辑态，提示由 console 输出
    }
  };

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <PanelHeader
          compact
          maxW={false}
          icon="brain"
          iconClass="text-violet-400"
          title="心智"
          desc="AI 倾向 · 心智记忆"
          actions={{ 
            <div className="flex items-center gap-2">
            <div className="flex bg-zinc-800 rounded-lg p-0.5">
              {(["bias", "memory"] as MindView[]).map(v => (
                <button key={v} onClick={() => setView(v)} className={`px-2 py-0.5 rounded text-[11px] ${view === v ? "bg-zinc-600 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
                  {v === "bias" ? "AI 倾向" : "心智记忆"}
                </button>
              ))}
            </div>
            {view === "bias" && (
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
          }}
        />

        {/* 新增表单（倾向视图） */}
        {view === "bias" && showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="输入倾向自述（如：我写对话偏克制、善用环境烘托）..."
              rows={3}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <div className="flex items-center gap-2">
              <select
                value={newSource}
                onChange={(e) => setNewSource(e.target.value as Source)}
                className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
              >
                <option value="ai">AI 自述</option>
                <option value="user">用户修正</option>
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

        {/* 列表：双视图 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {view === "memory" ? (
            /* ── 心智记忆（AI 学到的偏好，用户主权）── */
            manualLoading ? (
              <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
            ) : manual.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无记忆条目——AI 从你的写作反馈中学习</p>
            ) : (
              /* S103：说明书式目录——章节=分类，条目=内容 */
              <div className="space-y-3">
                {catalog.map(section => {
                  const collapsed = collapsedCats[section.key]
                  return (
                    <div key={section.key}>
                      {/* 章节标题（可折叠） */}
                      <button
                        onClick={() => setCollapsedCats(prev => ({ ...prev, [section.key]: !prev[section.key] }))}
                        className="w-full flex items-center gap-2 px-1 py-1.5 group"
                      >
                        <Icon name={collapsed ? "chevron-right" : "chevron-down"} size={11} className="text-zinc-600 group-hover:text-zinc-400 shrink-0" />
                        <Icon name={section.icon} size={13} className={`${section.color} shrink-0`} />
                        <span className="text-xs font-semibold text-zinc-300">{section.label}</span>
                        <span className="text-[10px] text-zinc-600">{section.desc}</span>
                        <span className="ml-auto text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded-full shrink-0">{section.count} 条</span>
                      </button>
                      {!collapsed && (
                        <div className="space-y-2 mt-1.5 pl-4">
                          {section.items.length === 0 ? (
                            <p className="text-[11px] text-zinc-700 italic pl-1">暂无条目</p>
                          ) : section.items.map((entry) => (
                            <div key={entry.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1.5">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                    entry.category === "collab" ? "bg-blue-500/20 text-blue-400 border-blue-500/30"
                                    : entry.category === "style" ? "bg-purple-500/20 text-purple-400 border-purple-500/30"
                                    : entry.category === "habit" ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
                                    : "bg-zinc-600/20 text-zinc-400 border-zinc-600/30"
                                  }`}>
                                    {(CATEGORY_META[entry.category as string] || {}).label ?? entry.category}
                                  </span>
                                  {entry.locked && <Icon name="lock" size={10} className="text-yellow-500" />}
                                </div>
                                <button onClick={() => toggleLock(entry.id, !!entry.locked)} className={`p-1 rounded ${entry.locked ? "text-yellow-500" : "text-zinc-600 hover:text-zinc-400"}`} title={entry.locked ? "已锁定" : "锁定（用户主权）"}>
                                  <Icon name="lock" size={12} />
                                </button>
                              </div>
                              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{entry.content}</p>
                              <p className="text-[10px] text-zinc-600">
                                {entry.activity ? `活跃度: ${entry.activity}` : ""}
                                {entry.created_at ? ` · ${new Date(entry.created_at).toLocaleDateString()}` : ""}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          ) : loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : items.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无倾向条目</p>
          ) : (
            items.map((entry) => (
              <div
                key={entry.id}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      SOURCE_COLORS[entry.source as Source] ?? SOURCE_COLORS.ai
                    }`}
                  >
                    {SOURCE_LABELS[entry.source as Source] ?? SOURCE_LABELS.ai}
                  </span>
                  <div className="flex items-center gap-1">
                    {/* S102：人类手动编辑 */}
                    <button
                      onClick={() => startEdit(entry)}
                      className="p-1 text-zinc-600 hover:text-sky-400 rounded"
                      title="编辑此倾向"
                    >
                      <Icon name="edit" size={12} />
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
                {editingId === entry.id ? (
                  /* ── 内联编辑态（S102）── */
                  <div className="space-y-2">
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={3}
                      className="w-full bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-600 focus:outline-none focus:border-sky-500 resize-none"
                      autoFocus
                    />
                    <div className="flex items-center gap-2">
                      <select
                        value={editSource}
                        onChange={(e) => setEditSource(e.target.value as Source)}
                        className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
                      >
                        <option value="ai">AI 自述</option>
                        <option value="user">用户修正</option>
                      </select>
                      <button
                        onClick={saveEdit}
                        disabled={!editContent.trim()}
                        className="text-xs px-2.5 py-1 bg-sky-600 hover:bg-sky-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-300 whitespace-pre-wrap">{entry.content}</p>
                )}
                <p className="text-[10px] text-zinc-600">
                  {entry.created_at ? new Date(entry.created_at).toLocaleString() : ""}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 删除确认 */}
      <ConfirmModal
        open={!!pendingDelete}
        title="删除倾向条目"
        message="确定删除这条倾向条目？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={handleDeleteConfirm}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
