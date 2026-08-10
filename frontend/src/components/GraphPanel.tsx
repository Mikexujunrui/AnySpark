import { useState, useEffect } from "react";
import { useGraphStore } from "../stores/graphStore";

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

  const [searchInput, setSearchInput] = useState("");

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
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
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
              onClick={() => setTab(t)}
              className={`text-xs px-3 py-1 rounded ${
                tab === t
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
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
              <button
                onClick={handleSearch}
                className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded"
              >
                搜索
              </button>
            </div>
            {types.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => handleTypeFilter("")}
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    !typeFilter
                      ? "bg-zinc-700 text-zinc-200 border-zinc-600"
                      : "text-zinc-500 border-zinc-700 hover:text-zinc-300"
                  }`}
                >
                  全部
                </button>
                {types.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleTypeFilter(t.name)}
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      typeFilter === t.name
                        ? "bg-zinc-700 text-zinc-200 border-zinc-600"
                        : "text-zinc-500 border-zinc-700 hover:text-zinc-300"
                    }`}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
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
                {entities.map((entity) => (
                  <div
                    key={entity.id}
                    className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-medium text-zinc-200">{entity.name}</h3>
                      <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded">
                        {entity.entity_type}
                      </span>
                    </div>
                    {entity.description && (
                      <p className="text-xs text-zinc-400 line-clamp-2">{entity.description}</p>
                    )}
                    {entity.aliases && entity.aliases.length > 0 && (
                      <p className="text-[10px] text-zinc-500 mt-1">
                        别名: {entity.aliases.join(", ")}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )
          ) : tab === "relations" ? (
            relations.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无关系</p>
            ) : (
              <div className="space-y-2">
                {relations.map((rel) => (
                  <div
                    key={rel.id}
                    className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3"
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-zinc-300">{rel.source_id.slice(0, 8)}</span>
                      <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded">
                        {rel.relation_type}
                      </span>
                      <span className="text-zinc-300">{rel.target_id.slice(0, 8)}</span>
                    </div>
                    {rel.description && (
                      <p className="text-xs text-zinc-500 mt-1">{rel.description}</p>
                    )}
                  </div>
                ))}
              </div>
            )
          ) : (
            events.length === 0 ? (
              <p className="text-zinc-600 text-sm text-center py-4">暂无事件</p>
            ) : (
              <div className="space-y-2">
                {events.map((event) => (
                  <div
                    key={event.id}
                    className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-sm font-medium text-zinc-200">{event.name}</h3>
                      {event.event_type && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-green-500/20 text-green-400 border border-green-500/30 rounded">
                          {event.event_type}
                        </span>
                      )}
                    </div>
                    {event.description && (
                      <p className="text-xs text-zinc-400 line-clamp-2">{event.description}</p>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
