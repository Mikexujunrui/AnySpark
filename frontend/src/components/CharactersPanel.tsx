// S152f：人物面板——图谱角色实体 + 角色卡文件 合并入口
// 设计：不做新机制，纯已有数据组合（图谱 entity_type=角色/人物 类实体 + 卡片/角色卡-*.md）
// 闭环：列表 → 详情（图谱字段编辑 + 角色卡内容保存）→ 新建/删除
import { useCallback, useEffect, useMemo, useState } from "react";
import { getSummary, createEntity, updateEntity, deleteEntity } from "../api/knowledge";
import { listWorkspace } from "../api/upload";
import { getCard, saveRoleCard } from "../api/role";
import { isPersonType } from "../lib/entityTypes";
import FullGraphView from "./FullGraphView";

interface V4Entity {
  id: string;
  name: string;
  entity_type?: string;
  aliases?: string[];
  description?: string;
  state?: string;
  first_chapter?: string;
  last_chapter?: string;
  [k: string]: unknown;
}

interface PersonItem {
  name: string;
  entity: V4Entity | null;
  hasCard: boolean;
}

export default function CharactersPanel({ bookId }: { bookId: string }) {
  const [entities, setEntities] = useState<V4Entity[]>([]);
  const [cardNames, setCardNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("全部");
  // S155：视图模式——列表（档案管理）/ 关系网（角色图谱，复用 FullGraphView 角色预设）
  const [viewMode, setViewMode] = useState<"list" | "graph">("list");
  const [showAdd, setShowAdd] = useState(false);
  const [addName, setAddName] = useState("");
  const [addType, setAddType] = useState("角色");
  const [saving, setSaving] = useState(false);
  // 角色卡编辑
  const [cardContent, setCardContent] = useState("");
  const [cardLoaded, setCardLoaded] = useState(false);
  const [cardDirty, setCardDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summary, ws] = await Promise.all([getSummary(bookId), listWorkspace(bookId)]);
      setEntities((summary.entities as V4Entity[]) ?? []);
      setCardNames(
        (ws.cards ?? [])
          .filter((c) => c.filename.startsWith("角色卡-") && c.filename.endsWith(".md"))
          .map((c) => c.filename.replace(/^角色卡-/, "").replace(/\.md$/, ""))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载人物失败");
    }
    setLoading(false);
  }, [bookId]);

  useEffect(() => {
    load();
    setSelectedName(null);
    setCardLoaded(false);
    setCardContent("");
  }, [load]);

  // 人物类型列表（图谱里出现的人物类型）
  const personTypes = useMemo(() => {
    const set = new Set<string>();
    for (const e of entities) {
      if (e.entity_type && isPersonType(e.entity_type)) set.add(e.entity_type);
    }
    // 默认"角色"存在时放最前
    return [...set].sort((a, b) => (a === "角色" ? -1 : b === "角色" ? 1 : 0));
  }, [entities]);

  // 人物列表（图谱实体 + 角色卡文件合并，名字去重）
  const people = useMemo<PersonItem[]>(() => {
    const byName = new Map<string, PersonItem>();
    for (const e of entities) {
      if (!e.entity_type || !isPersonType(e.entity_type)) continue;
      byName.set(e.name, { name: e.name, entity: e, hasCard: false });
    }
    for (const n of cardNames) {
      const cur = byName.get(n);
      if (cur) cur.hasCard = true;
      else byName.set(n, { name: n, entity: null, hasCard: true });
    }
    let list = [...byName.values()];
    if (typeFilter !== "全部") {
      list = list.filter((p) => !p.entity || p.entity.entity_type === typeFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.entity?.aliases ?? []).some((a) => a.toLowerCase().includes(q)) ||
          (p.entity?.description ?? "").toLowerCase().includes(q)
      );
    }
    return list.sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }, [entities, cardNames, typeFilter, searchQuery]);

  const selectedPerson = people.find((p) => p.name === selectedName) ?? null;

  // 选中人物时懒加载角色卡内容
  useEffect(() => {
    setCardLoaded(false);
    setCardContent("");
    setCardDirty(false);
    if (!selectedName) return;
    getCard("角色卡", selectedName, bookId)
      .then((r) => {
        setCardContent(r.content ?? "");
        setCardLoaded(true);
      })
      .catch(() => setCardLoaded(true));
  }, [selectedName, bookId]);

  const handleAdd = async () => {
    if (!addName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createEntity({
        name: addName.trim(),
        entity_type: addType.trim() || "角色",
        book_id: bookId,
      });
      setAddName("");
      setShowAdd(false);
      await load();
      setSelectedName(addName.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "新建失败");
    }
    setSaving(false);
  };

  const handleSaveEntity = async (patch: Partial<V4Entity>) => {
    if (!selectedPerson?.entity) return;
    setSaving(true);
    setError(null);
    try {
      await updateEntity(bookId, selectedPerson.entity.id, patch);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    }
    setSaving(false);
  };

  const handleSaveCard = async () => {
    if (!selectedName) return;
    setSaving(true);
    setError(null);
    try {
      await saveRoleCard(selectedName, cardContent, bookId);
      setCardDirty(false);
      setCardLoaded(true);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存角色卡失败");
    }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!selectedPerson?.entity) return;
    setSaving(true);
    setError(null);
    try {
      await deleteEntity(bookId, selectedPerson.entity.id);
      setSelectedName(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
    setSaving(false);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-2 shrink-0">
        <span className="text-[11px] text-zinc-400 font-medium">人物</span>
        {/* S155：列表 / 关系网视图切换 */}
        <div className="flex gap-0.5 border border-zinc-800 rounded overflow-hidden shrink-0">
          <button
            onClick={() => setViewMode("list")}
            className={`px-2 py-0.5 text-[10px] ${viewMode === "list" ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}
            title="人物列表档案"
          >列表</button>
          <button
            onClick={() => setViewMode("graph")}
            className={`px-2 py-0.5 text-[10px] flex items-center gap-1 ${viewMode === "graph" ? "bg-blue-600 text-white" : "text-zinc-500 hover:text-zinc-300"}`}
            title="角色关系网（角色图谱）"
          ><span className="inline-block">◈</span>关系网</button>
        </div>
        {viewMode === "list" && (
          <>
        <span className="text-[11px] text-zinc-600">|</span>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="text-[11px] bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-zinc-300 outline-none"
        >
          <option value="全部">全部人物类型</option>
          {personTypes.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="搜索人物 / 别名…"
          className="w-40 text-[11px] bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-zinc-300 outline-none focus:border-zinc-500"
        />
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="ml-auto text-[11px] px-2 py-0.5 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600"
        >
          + 新建人物
        </button>
        {error && <span className="text-[11px] text-red-400">{error}</span>}
          </>
        )}
      </div>

      {/* 新建输入条 */}
      {showAdd && (
        <div className="px-3 py-2 bg-zinc-900/40 border-b border-zinc-800/50 flex items-center gap-2 shrink-0">
          <input
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            autoFocus
            placeholder="人物名…"
            className="flex-1 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
          <select
            value={addType}
            onChange={(e) => setAddType(e.target.value)}
            className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 outline-none"
          >
            <option value="角色">角色</option>
            {personTypes.filter((t) => t !== "角色").map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            <option value="人物">人物</option>
          </select>
          <button
            onClick={handleAdd}
            disabled={saving}
            className="text-[11px] px-2 py-1 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600 disabled:opacity-50"
          >
            添加
          </button>
          <button
            onClick={() => setShowAdd(false)}
            className="text-[11px] px-2 py-1 rounded text-zinc-500 hover:text-zinc-300"
          >
            取消
          </button>
        </div>
      )}

      {viewMode === "graph" ? (
        /* S155：角色关系网（角色图谱）——复用 FullGraphView 角色预设，风格与知识库图谱统一 */
        <FullGraphView bookId={bookId} preset="person" title="角色关系网" />
      ) : (
      <div className="flex-1 min-h-0 flex">
        {/* 左栏：人物列表 */}
        <div className="w-52 shrink-0 border-r border-zinc-800 overflow-auto bg-zinc-900/20">
          {loading ? (
            <p className="text-[11px] text-zinc-600 px-3 py-3">加载中...</p>
          ) : people.length === 0 ? (
            <p className="text-[11px] text-zinc-700 px-3 py-3">暂无人物——图谱抽取会自动生成「角色」实体，也可点「+ 新建人物」</p>
          ) : (
            people.map((p) => (
              <button
                key={p.name}
                onClick={() => setSelectedName(p.name)}
                className={`w-full text-left px-3 py-2 rounded-none text-xs transition-colors border-b border-zinc-800/50 ${
                  selectedName === p.name ? "bg-zinc-700/50 text-zinc-100" : "text-zinc-400 hover:bg-zinc-800/60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate">{p.name}</span>
                  <span className="flex gap-1 shrink-0">
                    {p.hasCard && <span className="text-[9px] px-1 rounded bg-amber-900/40 text-amber-400">卡</span>}
                    {!p.entity && <span className="text-[9px] px-1 rounded bg-zinc-800 text-zinc-500">仅卡</span>}
                  </span>
                </div>
                {p.entity?.state && (
                  <p className="text-[10px] text-zinc-600 truncate">{p.entity.state}</p>
                )}
              </button>
            ))
          )}
        </div>

        {/* 右栏：人物详情 */}
        <div className="flex-1 min-w-0 overflow-auto p-4">
          {!selectedPerson ? (
            <p className="text-sm text-zinc-600 text-center py-10">
              选择左侧人物查看详情，或「+ 新建人物」
            </p>
          ) : (
            <div className="max-w-2xl mx-auto space-y-4">
              {/* 头部：名字 + 类型 */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-medium text-zinc-100">{selectedPerson.name}</h3>
                  <p className="text-xs text-zinc-500">
                    类型：{selectedPerson.entity?.entity_type ?? "（仅角色卡，无图谱实体）"}
                  </p>
                </div>
                <div className="flex gap-2">
                  {selectedPerson.entity && (
                    <button
                      onClick={handleDelete}
                      disabled={saving}
                      className="text-[11px] px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40 disabled:opacity-50"
                    >
                      删除实体
                    </button>
                  )}
                </div>
              </div>

              {/* 图谱字段 */}
              {selectedPerson.entity ? (
                <EntityEditor
                  key={selectedPerson.entity.id}
                  entity={selectedPerson.entity}
                  onSave={handleSaveEntity}
                  saving={saving}
                />
              ) : (
                <div className="text-[11px] text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded p-3">
                  此人目前只有角色卡文件，图谱中无实体。图谱抽取（写章节后自动）或手动新建实体后可编辑结构化字段。
                </div>
              )}

              {/* 角色卡 */}
              <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-zinc-400 font-medium">角色卡（人物档案，md）</span>
                  <div className="flex gap-2">
                    {cardDirty && (
                      <button
                        onClick={handleSaveCard}
                        disabled={saving}
                        className="text-[11px] px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-400 hover:bg-emerald-900/60 disabled:opacity-50"
                      >
                        保存角色卡
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setCardDirty(false);
                        if (!selectedName) return;
                        getCard("角色卡", selectedName, bookId).then((r) => setCardContent(r.content ?? ""));
                      }}
                      className="text-[11px] px-2 py-0.5 rounded text-zinc-500 hover:text-zinc-300"
                    >
                      放弃修改
                    </button>
                  </div>
                </div>
                {!cardLoaded ? (
                  <p className="text-[11px] text-zinc-600">加载中...</p>
                ) : (
                  <>
                    <textarea
                      value={cardContent}
                      onChange={(e) => {
                        setCardContent(e.target.value);
                        setCardDirty(true);
                      }}
                      placeholder={"人物档案（自然语言，自由格式）——\n例如：\n- 身份/职业\n- 外貌特征\n- 性格与动机\n- 人物弧光/成长线\n- 与关键人物的关系"}
                      className="w-full h-52 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-zinc-200 outline-none focus:border-zinc-500 font-mono resize-none"
                    />
                    {!selectedPerson.hasCard && cardContent.trim() && (
                      <p className="text-[10px] text-amber-500 mt-1">写入后将生成「角色卡-{selectedPerson.name}.md」</p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}

/* 图谱实体字段编辑 */
function EntityEditor({
  entity,
  onSave,
  saving,
}: {
  entity: V4Entity;
  onSave: (patch: Partial<V4Entity>) => Promise<void>;
  saving: boolean;
}) {
  const [form, setForm] = useState({
    entity_type: entity.entity_type ?? "角色",
    aliases: (entity.aliases ?? []).join("、"),
    description: entity.description ?? "",
    state: entity.state ?? "",
  });
  const [dirty, setDirty] = useState(false);

  const set = (k: keyof typeof form, v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setDirty(true);
  };

  return (
    <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400 font-medium">图谱档案</span>
        {dirty && (
          <button
            onClick={async () => {
              await onSave({
                entity_type: form.entity_type.trim() || "角色",
                aliases: form.aliases.split(/[、,，\s]+/).map((a) => a.trim()).filter(Boolean),
                description: form.description,
                state: form.state,
              });
              setDirty(false);
            }}
            disabled={saving}
            className="text-[11px] px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-400 hover:bg-emerald-900/60 disabled:opacity-50"
          >
            保存档案
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        <label className="block">
          <span className="text-[10px] text-zinc-500">类型</span>
          <input
            value={form.entity_type}
            onChange={(e) => set("entity_type", e.target.value)}
            className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
        </label>
        <label className="block">
          <span className="text-[10px] text-zinc-500">别名（、分隔）</span>
          <input
            value={form.aliases}
            onChange={(e) => set("aliases", e.target.value)}
            className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
        </label>
        <label className="block col-span-2">
          <span className="text-[10px] text-zinc-500">当前状态</span>
          <input
            value={form.state}
            onChange={(e) => set("state", e.target.value)}
            placeholder="如：重伤昏迷 / 已入狱 / 失忆中"
            className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
        </label>
        <label className="block col-span-2">
          <span className="text-[10px] text-zinc-500">描述</span>
          <textarea
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            rows={3}
            className="w-full text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 resize-none"
          />
        </label>
      </div>
      <div className="flex gap-4 text-[10px] text-zinc-600">
        {entity.first_chapter && <span>首次出场：{entity.first_chapter}</span>}
        {entity.last_chapter && <span>最近出场：{entity.last_chapter}</span>}
      </div>
    </div>
  );
}
