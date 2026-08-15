import { useEffect, useMemo, useState } from "react";
import { useSkillStore } from "../stores/skillStore";
import Icon from "./ui/Icon";
import ConfirmModal from "./ui/ConfirmModal";

// S105→S130：书架技能库（全局能力库管理视角——与项目内「技巧」面板互补）
// S130（阶段 3）：按 type 分组（writing 写作技法 / main 类型指导 / plot 剧情模式 /
// both 通用）+ 书名包聚合视图（pack_id 非空子条归入包卡片，包名=方法论 skill）
const TARGET_LABELS: Record<string, string> = {
  writing: "写作技法",
  main: "类型指导",
  plot: "剧情模式",
  both: "通用",
};

// S186：草稿批量采纳/拒绝区（全选 + 批量按钮 + 每条 checkbox）
function DraftBulkSection({
  drafts,
  onApprove,
  onReject,
}: {
  drafts: { id: string; name: string; description?: string; target?: string }[];
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const allSelected = selected.size === drafts.length;
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(drafts.map((d) => d.id)));
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const bulk = async (kind: "approve" | "reject") => {
    if (selected.size === 0) return;
    setBusy(kind);
    const ids = [...selected];
    try {
      for (const id of ids) {
        await (kind === "approve" ? onApprove(id) : onReject(id));
      }
    } catch (e: unknown) {
      window.alert(`${kind === "approve" ? "采纳" : "拒绝"}失败：${(e as Error)?.message || String(e)}`);
    } finally {
      setBusy(null);
      setSelected(new Set());
    }
  };
  return (
    <div className="rounded-2xl border border-amber-700/40 bg-gradient-to-br from-amber-950/30 to-zinc-900/40 p-4 mb-6">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <label className="flex items-center gap-1.5 text-xs font-medium text-amber-400 cursor-pointer select-none">
          <input type="checkbox" checked={allSelected} onChange={toggleAll} className="accent-amber-500" />
          <Icon name="lightbulb" size={13} /> AI 生成的技能草稿（{drafts.length} 条）
        </label>
        {selected.size > 0 && (
          <>
            <span className="text-[10px] text-zinc-500">已选 {selected.size}</span>
            <button
              onClick={() => bulk("approve")}
              disabled={busy !== null}
              className="text-[11px] px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white rounded-lg flex items-center gap-1"
            >
              {busy === "approve" ? <Icon name="loader" size={11} className="animate-spin" /> : <Icon name="check" size={11} />}
              批量采纳 ({selected.size})
            </button>
            <button
              onClick={() => bulk("reject")}
              disabled={busy !== null}
              className="text-[11px] px-2.5 py-1 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-zinc-300 rounded-lg flex items-center gap-1"
            >
              {busy === "reject" ? <Icon name="loader" size={11} className="animate-spin" /> : <Icon name="x" size={11} />}
              批量拒绝 ({selected.size})
            </button>
          </>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {drafts.map((d) => {
          const checked = selected.has(d.id);
          return (
            <div key={d.id} className={`bg-zinc-900/70 rounded-xl px-3.5 py-3 border ${checked ? "border-amber-500/50 ring-1 ring-amber-500/30" : "border-zinc-800/70"}`}>
              <div className="flex items-start gap-2">
                <input type="checkbox" checked={checked} onChange={() => toggle(d.id)} className="accent-amber-500 mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200 font-medium truncate">{d.name}</p>
                  {d.description && <p className="text-[11px] text-zinc-500 mt-1 line-clamp-2">{d.description}</p>}
                  <div className="flex gap-2 mt-2.5">
                    <button
                      onClick={() => {
                        onApprove(d.id).catch((e: unknown) =>
                          window.alert(`确认失败：${(e as Error)?.message || String(e)}`)
                        )
                      }}
                      className="text-[11px] px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg"
                    >
                      采纳
                    </button>
                    <button
                      onClick={() => {
                        onReject(d.id).catch((e: unknown) =>
                          window.alert(`拒绝失败：${(e as Error)?.message || String(e)}`)
                        )
                      }}
                      className="text-[11px] px-2.5 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded-lg"
                    >
                      拒绝
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SkillCard({
  skill,
  onEdit,
  onDelete,
  onToggle,
}: {
  skill: { id: string; name: string; content: string; description?: string; tags?: string; type?: string; target?: string; pack_id?: string; enabled?: boolean };
  onEdit: (s: { id: string; name: string; content: string; description?: string; tags?: string; type?: string }) => void;
  onDelete: (id: string, name: string) => void;
  onToggle: (id: string, enabled: boolean) => void;
}) {
  const st = skill.type || skill.target || "";
  return (
    <div className={`rounded-xl border p-3.5 transition-colors ${skill.enabled === false ? "bg-zinc-900/30 border-zinc-800/60 opacity-60" : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-zinc-200 truncate">{skill.name}</h3>
            {st && TARGET_LABELS[st] && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${st === "main" ? "bg-purple-900/40 text-purple-300" : st === "plot" ? "bg-emerald-900/40 text-emerald-300" : "bg-sky-900/40 text-sky-300"}`}>
                {TARGET_LABELS[st]}
              </span>
            )}
            {skill.pack_id && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400 shrink-0">
                包：{skill.pack_id}
              </span>
            )}
          </div>
          {skill.tags && (
            <div className="flex gap-1 mt-1 flex-wrap">
              {skill.tags.split(/[,，]/).filter(Boolean).slice(0, 4).map((t) => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 bg-zinc-800 text-zinc-500 rounded">{t.trim()}</span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onToggle(skill.id, !skill.enabled)}
            title={skill.enabled === false ? "启用" : "停用"}
            className={`w-8 h-4.5 rounded-full transition-colors ${skill.enabled === false ? "bg-zinc-700" : "bg-emerald-600/70"}`}
          >
            <span className={`block w-3.5 h-3.5 rounded-full bg-white mx-0.5 transition-transform ${skill.enabled === false ? "" : "translate-x-3"}`} />
          </button>
          <button onClick={() => onEdit(skill)} className="text-zinc-600 hover:text-sky-400 p-1 rounded" title="编辑">
            <Icon name="edit" size={13} />
          </button>
          <button onClick={() => onDelete(skill.id, skill.name)} className="text-zinc-600 hover:text-red-400 p-1 rounded" title="删除">
            <Icon name="trash" size={13} />
          </button>
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mt-1.5 leading-relaxed line-clamp-3">{skill.description || "（无描述）"}</p>
    </div>
  );
}

export default function SkillsShelfPanel() {
  const skills = useSkillStore((s) => s.skills);
  const drafts = useSkillStore((s) => s.drafts);
  const loading = useSkillStore((s) => s.loading);
  const fetchSkills = useSkillStore((s) => s.fetchSkills);
  const fetchDrafts = useSkillStore((s) => s.fetchDrafts);
  const addSkill = useSkillStore((s) => s.addSkill);
  const editSkill = useSkillStore((s) => s.editSkill);
  const removeSkill = useSkillStore((s) => s.removeSkill);
  const approveDraft = useSkillStore((s) => s.approveDraft);
  const rejectDraft = useSkillStore((s) => s.rejectDraft);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", content: "", description: "", tags: "", target: "writing" });
  const [editing, setEditing] = useState<{ id: string; name: string; content: string; description?: string; tags?: string; target?: string } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    fetchSkills();
    fetchDrafts();
  }, [fetchSkills, fetchDrafts]);

  const groups = useMemo(() => {
    // S130：按 type 分组（writing/main/plot/both）；pack 子条仍归 type 组
    // （包视图：书名方法论 both 组内可见，子条带包徽标）
    const g: Record<string, typeof skills> = { writing: [], main: [], plot: [], both: [], other: [] };
    for (const s of skills) {
      const st = s.type || s.target || "";
      const key = st === "main" || st === "plot" || st === "both" ? st : st === "writing" ? "writing" : "other";
      g[key].push(s);
    }
    return g;
  }, [skills]);

  const enabledCount = skills.filter((s) => s.enabled !== false).length;

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.content.trim()) return;
    if (editing) {
      await editSkill(editing.id, {
        name: form.name.trim(),
        content: form.content.trim(),
        description: form.description.trim() || undefined,
        tags: form.tags.trim() || undefined,
        target: form.target,
      });
      setEditing(null);
    } else {
      await addSkill(form.name.trim(), form.content.trim(), form.description.trim() || undefined, form.target);
    }
    setForm({ name: "", content: "", description: "", tags: "", target: "writing" });
    setShowAdd(false);
  };

  const startEdit = (s: { id: string; name: string; content: string; description?: string; tags?: string; target?: string }) => {
    setEditing(s);
    setForm({ name: s.name, content: s.content, description: s.description || "", tags: s.tags || "", target: s.target || "writing" });
    setShowAdd(true);
  };

  const resetForm = () => {
    setForm({ name: "", content: "", description: "", tags: "", target: "writing" });
    setEditing(null);
    setShowAdd(false);
  };

  const groupTitle = (key: string): { label: string; desc: string } => {
    if (key === "main") return { label: "类型指导", desc: "结构/节奏/类型方法论——主循环决策用" };
    if (key === "plot") return { label: "剧情模式", desc: "跨章剧情模式模板——探索派生方向用" };
    if (key === "both") return { label: "通用", desc: "文风+结构兼顾——写作与主循环都注入" };
    if (key === "writing") return { label: "写作技法", desc: "文风/句法/表现手法——写作点名注入" };
    return { label: "其他", desc: "" };
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* 渐变横幅 */}
      <div className="rounded-2xl bg-gradient-to-br from-zinc-900 via-zinc-900/80 to-sky-950/40 border border-zinc-800 p-6 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2.5 text-zinc-100">
              <span className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500/30 to-purple-500/30 border border-sky-800/40 flex items-center justify-center">
                <Icon name="pen-tool" size={18} className="text-sky-400" />
              </span>
              技能库
            </h1>
            <p className="text-zinc-500 mt-1.5 text-sm">全局能力库——叙事技法与方法论，所有项目复用（跨书能力）</p>
          </div>
          <button
            onClick={() => (showAdd ? resetForm() : setShowAdd(true))}
            className="text-xs px-3.5 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium shrink-0"
          >
            {showAdd ? "取消" : "+ 新建技能"}
          </button>
        </div>
        {/* 统计 */}
        <div className="flex gap-6 mt-5">
          {[
            { label: "全部技能", value: skills.length, accent: "text-zinc-200" },
            { label: "启用中", value: enabledCount, accent: "text-emerald-400" },
            { label: "草稿待确认", value: drafts.length, accent: "text-amber-400" },
          ].map((s) => (
            <div key={s.label}>
              <p className={`text-2xl font-bold ${s.accent}`}>{s.value}</p>
              <p className="text-[11px] text-zinc-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 新建/编辑表单 */}
      {showAdd && (
        <div className="rounded-xl border border-sky-900/50 bg-zinc-900/60 p-4 mb-6 space-y-2.5">
          <p className="text-xs text-zinc-400 font-medium">{editing ? `编辑技能：${editing.name}` : "新建技能（内容自然语言，可增删改）"}</p>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="技能名（如：悬念三段式）" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-sky-600 placeholder-zinc-600" />
          <div className="flex gap-2">
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="一句话描述（索引注入用，重要）" className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-sky-600 placeholder-zinc-600" />
            <select value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} className="bg-zinc-800 text-zinc-300 text-xs px-2.5 py-2 rounded-lg border border-zinc-700">
              <option value="writing">写作技法</option>
              <option value="main">类型指导</option>
              <option value="plot">剧情模式</option>
              <option value="both">通用</option>
            </select>
          </div>
          <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="标签（逗号分隔，如：节奏,悬念）" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-sky-600 placeholder-zinc-600" />
          <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="技法全文（点名注入时的完整指导：名+技法+情形案例三段式）" rows={4} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-sky-600 placeholder-zinc-600 resize-none" />
          <div className="flex gap-2">
            <button onClick={handleSubmit} disabled={!form.name.trim() || !form.content.trim()} className="text-xs px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded-lg">
              {editing ? "保存修改" : "创建"}
            </button>
            <button onClick={resetForm} className="text-xs px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded-lg">取消</button>
          </div>
        </div>
      )}

      {/* 草稿待确认区 */}
      {drafts.length > 0 && (
        <DraftBulkSection drafts={drafts} onApprove={approveDraft} onReject={rejectDraft} />
      )}

      {/* 分组技能列表 */}
      {loading ? (
        <p className="text-zinc-600 text-sm text-center py-10">加载中...</p>
      ) : skills.length === 0 ? (
        <div className="text-center py-16 text-zinc-600 text-sm">
          <Icon name="pen-tool" size={32} className="mx-auto mb-3 text-zinc-700" />
          暂无技能——点「新建技能」手动创建，或让 AI 从参考书提炼（对话中说「借鉴某本书的写法」）
        </div>
      ) : (
        <div className="space-y-8">
          {/* S158e：补 plot/both——拆书提炼（S114 三层）生成的书名方法论(both)/剧情模式(plot)
              草稿确认后此前不显示（“确认了没动静”），漏组即隐形丢失 */}
          {(["writing", "main", "plot", "both", "other"] as const).map((key) => {
            const items = groups[key];
            if (items.length === 0) return null;
            const t = groupTitle(key);
            return (
              <section key={key}>
                <div className="flex items-baseline gap-2 mb-3">
                  <h2 className="text-sm font-semibold text-zinc-300">{t.label}</h2>
                  <span className="text-[11px] text-zinc-600">{t.desc}</span>
                  <span className="text-[11px] text-zinc-600 ml-auto">{items.length} 条</span>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {items.map((s) => (
                    <SkillCard key={s.id} skill={s} onEdit={startEdit} onDelete={(id, name) => setPendingDelete({ id, name })} onToggle={(id, enabled) => editSkill(id, { enabled })} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <ConfirmModal
        open={!!pendingDelete}
        title="删除技能"
        message={`确定删除「${pendingDelete?.name}」？此操作不可恢复。`}
        confirmText="删除"
        danger
        onConfirm={async () => {
          if (pendingDelete) await removeSkill(pendingDelete.id);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
