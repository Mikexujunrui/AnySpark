import { useState, useEffect } from "react";
import { useGraphStore } from "../stores/graphStore";
import type { GraphEntity, GraphRelation, GraphEvent } from "../api/graph";

type Tab = "entities" | "relations" | "events";

const TAB_LABELS: Record<Tab, string> = {
  entities: "实体",
  relations: "关系",
  events: "事件",
};

interface GraphPanelProps {
  open: boolean;
  onClose: () => void;
}

/* ── 通用小组件 ── */

function FieldInput({
  label,
  value,
  onChange,
  placeholder,
  textarea,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
}) {
  const cls =
    "w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500";
  return (
    <label className="block space-y-0.5">
      <span className="text-[10px] text-zinc-500">{label}</span>
      {textarea ? (
        <textarea className={cls + " h-16 resize-none"} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      ) : (
        <input className={cls} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      )}
    </label>
  );
}

function ActionBtn({
  children,
  onClick,
  variant = "default",
}: {
  children: React.ReactNode;
  onClick: () => void;
  variant?: "default" | "danger" | "primary";
}) {
  const base = "text-[10px] px-2 py-0.5 rounded transition-colors";
  const styles = {
    default: "bg-zinc-800 hover:bg-zinc-700 text-zinc-400",
    danger: "bg-red-900/40 hover:bg-red-800/60 text-red-400",
    primary: "bg-blue-600/60 hover:bg-blue-500/60 text-blue-200",
  };
  return (
    <button onClick={onClick} className={`${base} ${styles[variant]}`}>
      {children}
    </button>
  );
}

/* ── 实体表单 ── */

function EntityForm({
  initial,
  types,
  onSubmit,
  onCancel,
}: {
  initial?: GraphEntity;
  types: { name: string }[];
  onSubmit: (data: { name: string; entity_type: string; aliases: string[]; description: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [entityType, setEntityType] = useState(initial?.entity_type ?? types[0]?.name ?? "角色");
  const [aliases, setAliases] = useState(initial?.aliases?.join(", ") ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  return (
    <div className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 space-y-2">
      <FieldInput label="名称" value={name} onChange={setName} placeholder="实体名称" />
      <FieldInput label="类型" value={entityType} onChange={setEntityType} placeholder="角色/地点/事件/物件/设定" />
      <FieldInput label="别名（逗号分隔）" value={aliases} onChange={setAliases} placeholder="别名1, 别名2" />
      <FieldInput label="描述" value={description} onChange={setDescription} placeholder="描述" textarea />
      <div className="flex gap-2 justify-end">
        <ActionBtn onClick={onCancel}>取消</ActionBtn>
        <ActionBtn
          variant="primary"
          onClick={() => {
            if (!name.trim()) return;
            onSubmit({
              name: name.trim(),
              entity_type: entityType.trim(),
              aliases: aliases
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
              description: description.trim(),
            });
          }}
        >
          {initial ? "保存" : "创建"}
        </ActionBtn>
      </div>
    </div>
  );
}

/* ── 关系表单 ── */

function RelationForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: GraphRelation;
  onSubmit: (data: { from_name: string; to_name: string; rel_type: string; description: string }) => void;
  onCancel: () => void;
}) {
  const [fromName, setFromName] = useState(initial?.from_name ?? "");
  const [toName, setToName] = useState(initial?.to_name ?? "");
  const [relType, setRelType] = useState(initial?.rel_type ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  return (
    <div className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <FieldInput label="源实体" value={fromName} onChange={setFromName} placeholder="角色A" />
        <FieldInput label="目标实体" value={toName} onChange={setToName} placeholder="角色B" />
      </div>
      <FieldInput label="关系类型" value={relType} onChange={setRelType} placeholder="认识/兄妹/师徒" />
      <FieldInput label="描述" value={description} onChange={setDescription} placeholder="关系说明" textarea />
      <div className="flex gap-2 justify-end">
        <ActionBtn onClick={onCancel}>取消</ActionBtn>
        <ActionBtn
          variant="primary"
          onClick={() => {
            if (!fromName.trim() || !toName.trim() || !relType.trim()) return;
            onSubmit({ from_name: fromName.trim(), to_name: toName.trim(), rel_type: relType.trim(), description: description.trim() });
          }}
        >
          {initial ? "保存" : "创建"}
        </ActionBtn>
      </div>
    </div>
  );
}

/* ── 事件表单 ── */

function EventForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: GraphEvent;
  onSubmit: (data: { label: string; time_point: string; description: string; involved: string[] }) => void;
  onCancel: () => void;
}) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [timePoint, setTimePoint] = useState(initial?.time_point ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [involved, setInvolved] = useState(initial?.involved?.join(", ") ?? "");

  return (
    <div className="bg-zinc-800/80 border border-zinc-700 rounded-lg p-3 space-y-2">
      <FieldInput label="事件名称" value={label} onChange={setLabel} placeholder="事件名称" />
      <FieldInput label="时间点" value={timePoint} onChange={setTimePoint} placeholder="第3章" />
      <FieldInput label="涉及实体（逗号分隔）" value={involved} onChange={setInvolved} placeholder="角色A, 角色B" />
      <FieldInput label="描述" value={description} onChange={setDescription} placeholder="事件说明" textarea />
      <div className="flex gap-2 justify-end">
        <ActionBtn onClick={onCancel}>取消</ActionBtn>
        <ActionBtn
          variant="primary"
          onClick={() => {
            if (!label.trim()) return;
            onSubmit({
              label: label.trim(),
              time_point: timePoint.trim(),
              description: description.trim(),
              involved: involved
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            });
          }}
        >
          {initial ? "保存" : "创建"}
        </ActionBtn>
      </div>
    </div>
  );
}

/* ── 主面板 ── */

export default function GraphPanel({ open, onClose }: GraphPanelProps) {
  const entities = useGraphStore((s) => s.entities);
  const relations = useGraphStore((s) => s.relations);
  const events = useGraphStore((s) => s.events);
  const types = useGraphStore((s) => s.types);
  const loading = useGraphStore((s) => s.loading);
  const tab = useGraphStore((s) => s.tab);
  const typeFilter = useGraphStore((s) => s.typeFilter);
  const fetchAll = useGraphStore((s) => s.fetchAll);
  const setTab = useGraphStore((s) => s.setTab);
  const setSearchQuery = useGraphStore((s) => s.setSearchQuery);
  const setTypeFilter = useGraphStore((s) => s.setTypeFilter);
  const addEntity = useGraphStore((s) => s.addEntity);
  const editEntity = useGraphStore((s) => s.editEntity);
  const removeEntity = useGraphStore((s) => s.removeEntity);
  const addRelation = useGraphStore((s) => s.addRelation);
  const editRelation = useGraphStore((s) => s.editRelation);
  const removeRelation = useGraphStore((s) => s.removeRelation);
  const addEvent = useGraphStore((s) => s.addEvent);
  const editEvent = useGraphStore((s) => s.editEvent);
  const removeEvent = useGraphStore((s) => s.removeEvent);

  const [searchInput, setSearchInput] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    if (open) fetchAll();
  }, [open, fetchAll]);

  const handleSearch = () => {
    setSearchQuery(searchInput);
    fetchAll();
  };

  const handleTypeFilter = (t: string) => {
    setTypeFilter(t);
    fetchAll();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div className="relative ml-auto w-[520px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">图谱</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tab 切换 */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800">
          {(["entities", "relations", "events"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => {
                setTab(t);
                setShowCreate(false);
                setEditingId(null);
              }}
              className={`text-xs px-3 py-1 rounded ${tab === t ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
          <div className="ml-auto">
            <ActionBtn variant="primary" onClick={() => { setShowCreate(!showCreate); setEditingId(null); }}>
              {showCreate ? "取消" : "+ 新增"}
            </ActionBtn>
          </div>
        </div>

        {/* 搜索 + 筛选（仅实体 Tab） */}
        {tab === "entities" && (
          <div className="px-4 py-2 border-b border-zinc-800 space-y-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="搜索实体..."
                className="flex-1 bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              />
              <button onClick={handleSearch} className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded">
                搜索
              </button>
            </div>
            {types.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => handleTypeFilter("")}
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${!typeFilter ? "bg-zinc-700 text-zinc-200 border-zinc-600" : "text-zinc-500 border-zinc-700 hover:text-zinc-300"}`}
                >
                  全部
                </button>
                {types.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleTypeFilter(t.name)}
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${typeFilter === t.name ? "bg-zinc-700 text-zinc-200 border-zinc-600" : "text-zinc-500 border-zinc-700 hover:text-zinc-300"}`}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 创建表单 */}
        {showCreate && (
          <div className="px-4 py-2 border-b border-zinc-800">
            {tab === "entities" && (
              <EntityForm
                types={types}
                onSubmit={async (data) => {
                  await addEntity(data);
                  setShowCreate(false);
                }}
                onCancel={() => setShowCreate(false)}
              />
            )}
            {tab === "relations" && (
              <RelationForm
                onSubmit={async (data) => {
                  await addRelation(data);
                  setShowCreate(false);
                }}
                onCancel={() => setShowCreate(false)}
              />
            )}
            {tab === "events" && (
              <EventForm
                onSubmit={async (data) => {
                  await addEvent(data);
                  setShowCreate(false);
                }}
                onCancel={() => setShowCreate(false)}
              />
            )}
          </div>
        )}

        {/* 列表内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : tab === "entities" ? (
            entities.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无实体</p>
            ) : (
              <div className="space-y-2">
                {entities.map((entity) =>
                  editingId === entity.id ? (
                    <EntityForm
                      key={entity.id}
                      initial={entity}
                      types={types}
                      onSubmit={async (data) => {
                        await editEntity(entity.id, data);
                        setEditingId(null);
                      }}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <div key={entity.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <h3 className="text-sm font-medium text-zinc-200">{entity.name}</h3>
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded">
                            {entity.entity_type}
                          </span>
                          <ActionBtn onClick={() => { setEditingId(entity.id); setShowCreate(false); }}>编辑</ActionBtn>
                          <ActionBtn variant="danger" onClick={() => removeEntity(entity.id)}>删除</ActionBtn>
                        </div>
                      </div>
                      {entity.description && <p className="text-xs text-zinc-400 line-clamp-2">{entity.description}</p>}
                      {entity.state && <p className="text-[10px] text-zinc-500 mt-1">状态: {entity.state}</p>}
                      {entity.aliases?.length > 0 && (
                        <p className="text-[10px] text-zinc-500 mt-1">别名: {entity.aliases.join(", ")}</p>
                      )}
                    </div>
                  )
                )}
              </div>
            )
          ) : tab === "relations" ? (
            relations.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无关系</p>
            ) : (
              <div className="space-y-2">
                {relations.map((rel) =>
                  editingId === rel.id ? (
                    <RelationForm
                      key={rel.id}
                      initial={rel}
                      onSubmit={async (data) => {
                        await editRelation(rel.id, data);
                        setEditingId(null);
                      }}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <div key={rel.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="text-zinc-300">{rel.from_name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded">
                            {rel.rel_type}
                          </span>
                          <span className="text-zinc-300">{rel.to_name}</span>
                        </div>
                        <div className="flex gap-1">
                          <ActionBtn onClick={() => { setEditingId(rel.id); setShowCreate(false); }}>编辑</ActionBtn>
                          <ActionBtn variant="danger" onClick={() => removeRelation(rel.id)}>删除</ActionBtn>
                        </div>
                      </div>
                      {rel.description && <p className="text-xs text-zinc-500 mt-1">{rel.description}</p>}
                    </div>
                  )
                )}
              </div>
            )
          ) : events.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无事件</p>
          ) : (
            <div className="space-y-2">
              {events.map((event) =>
                editingId === event.id ? (
                  <EventForm
                    key={event.id}
                    initial={event}
                    onSubmit={async (data) => {
                      await editEvent(event.id, data);
                      setEditingId(null);
                    }}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <div key={event.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-medium text-zinc-200">{event.label}</h3>
                      <div className="flex items-center gap-1">
                        {event.time_point && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-green-500/20 text-green-400 border border-green-500/30 rounded">
                            {event.time_point}
                          </span>
                        )}
                        <ActionBtn onClick={() => { setEditingId(event.id); setShowCreate(false); }}>编辑</ActionBtn>
                        <ActionBtn variant="danger" onClick={() => removeEvent(event.id)}>删除</ActionBtn>
                      </div>
                    </div>
                    {event.description && <p className="text-xs text-zinc-400 line-clamp-2">{event.description}</p>}
                    {event.involved?.length > 0 && (
                      <p className="text-[10px] text-zinc-500 mt-1">涉及: {event.involved.join(", ")}</p>
                    )}
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
