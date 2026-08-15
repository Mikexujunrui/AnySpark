import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useStoryStore } from "../stores/storyStore";
import { saveStoryLayout } from "../api/story";
import type { StoryNode } from "../api/story";
import ConfirmModal from "./ui/ConfirmModal";

/* ── 节点样式（按 kind 区分）── */
const KIND_STYLES: Record<
  StoryNode["kind"],
  { fill: string; stroke: string; label: string; text: string }
> = {
  root: { fill: "rgba(146,64,14,0.35)", stroke: "#d97706", label: "根", text: "#fcd34d" },
  main: { fill: "rgba(6,78,59,0.45)", stroke: "#10b981", label: "主线", text: "#6ee7b7" },
  anchor: { fill: "rgba(88,28,135,0.4)", stroke: "#a855f7", label: "锚点", text: "#d8b4fe" },
  candidate: { fill: "rgba(39,39,42,0.8)", stroke: "#71717a", label: "候选", text: "#a1a1aa" },
  subplot: { fill: "rgba(30,58,138,0.4)", stroke: "#3b82f6", label: "支线", text: "#93c5fd" },
  loop: { fill: "rgba(136,19,55,0.4)", stroke: "#f43f5e", label: "循环", text: "#fda4af" },
};

const NODE_W = 132;
const NODE_H = 52;
const LAYER_GAP = 210; // 层间距（x）
const ROW_GAP = 88; // 同层节点间距（y）

interface Pos {
  x: number;
  y: number;
}

// S152：接收 bookId（项目隔离）——挂载/切项目时按当前项目拉树、写节点、存布局
export default function StoryTreeView({ bookId }: { bookId: string }) {
  const { nodes, threads, selectedNodeId, fetchTree, addNode, choose, anchor, removeNode, selectNode } =
    useStoryStore();
  const [showAddInput, setShowAddInput] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingRemoveId, setPendingRemoveId] = useState<string | null>(null);

  // 画布变换（缩放/平移）
  const [zoom, setZoom] = useState(0.9);
  const [pan, setPan] = useState<Pos>({ x: 24, y: 24 });
  // 节点手动拖拽位置（本地，不持久化）
  // 扩展点（DESIGN §12.37）：持久化时在此接入 —— 拖拽结束回调见 onNodePointerUp，
  // 数据即本 state（node_id → {x,y}）；方案：story_nodes 加 pos_x/pos_y 列 + PUT /api/story/layout 批量保存
  const [manualPos, setManualPos] = useState<Record<string, Pos>>({});

  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);
  const panRef = useRef<{ x0: number; y0: number; px: number; py: number } | null>(null);
  const layoutInitRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // S152：切项目时重置本地布局/选中态，再拉当前项目的树
  useEffect(() => {
    setManualPos({});
    layoutInitRef.current = false;
    selectNode(null);
    fetchTree(bookId);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [bookId, fetchTree]);

  // S76：首次拿到节点后应用持久化坐标（只初始化一次，后续拖拽由用户接管）
  useEffect(() => {
    if (nodes.length && !layoutInitRef.current) {
      const saved: Record<string, Pos> = {};
      for (const n of nodes) {
        if (n.pos && typeof n.pos.x === "number") saved[n.id] = { x: n.pos.x, y: n.pos.y };
      }
      setManualPos(saved);
      layoutInitRef.current = true;
    }
  }, [nodes]);

  // S76：拖拽结束后 debounce 批量保存（DESIGN §12.37：只存用户调整过的坐标）
  const scheduleSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      setManualPos((prev) => {
        const positions = Object.entries(prev).map(([node_id, p]) => ({
          node_id,
          x: Math.round(p.x * 100) / 100,
          y: Math.round(p.y * 100) / 100,
        }));
        if (positions.length) {
          saveStoryLayout(positions, bookId).catch((e) =>
            console.error("保存叙事树布局失败:", e)
          );
        }
        return prev;
      });
    }, 1200);
  }, [bookId]);

  /* ── 分层布局：root=0，子节点右移一层；同层按创建序纵向排 ── */
  const layout = useMemo(() => {
    const layer: Record<string, number> = {};
    const childrenOf: Record<string, string[]> = {};
    for (const n of nodes) {
      childrenOf[n.parent_id ?? "__root__"] = childrenOf[n.parent_id ?? "__root__"] ?? [];
      childrenOf[n.parent_id ?? "__root__"].push(n.id);
    }
    const rootIds = (childrenOf["__root__"] ?? []).filter((id) => nodes.some((n) => n.id === id && !n.parent_id));
    // BFS 分层
    const queue: { id: string; d: number }[] = rootIds.map((id) => ({ id, d: 0 }));
    for (const n of nodes) {
      if (n.parent_id && !layer[n.parent_id]) {
        queue.push({ id: n.id, d: 0 });
      }
    }
    const visited = new Set<string>();
    while (queue.length) {
      const cur = queue.shift()!;
      if (visited.has(cur.id)) continue;
      visited.add(cur.id);
      layer[cur.id] = Math.max(layer[cur.id] ?? 0, cur.d);
      for (const cid of childrenOf[cur.id] ?? []) queue.push({ id: cid, d: (layer[cur.id] ?? 0) + 1 });
    }
    // 同层分组 + 排序（root 优先、main 优先）
    const byLayer: Record<number, string[]> = {};
    for (const n of nodes) {
      const l = layer[n.id] ?? 0;
      byLayer[l] = byLayer[l] ?? [];
      byLayer[l].push(n.id);
    }
    const kindRank: Record<string, number> = { root: 0, main: 1, anchor: 2, subplot: 3, candidate: 4, loop: 5 };
    for (const l of Object.keys(byLayer)) {
      byLayer[+l].sort((a, b) => {
        const na = nodes.find((n) => n.id === a)!;
        const nb = nodes.find((n) => n.id === b)!;
        return (kindRank[na.kind] ?? 9) - (kindRank[nb.kind] ?? 9) || na.created_at.localeCompare(nb.created_at);
      });
    }
    // 坐标
    const pos: Record<string, Pos> = {};
    for (const l of Object.keys(byLayer)) {
      byLayer[+l].forEach((id, idx) => {
        pos[id] = { x: +l * LAYER_GAP, y: idx * ROW_GAP };
      });
    }
    return { pos, byLayer, layer };
  }, [nodes]);

  // 最终位置：手动拖拽优先，否则布局
  const finalPos = (id: string): Pos => manualPos[id] ?? layout.pos[id] ?? { x: 0, y: 0 };

  /* ── 交互：节点拖拽 ── */
  const onNodePointerDown = (e: React.PointerEvent, id: string) => {
    e.stopPropagation();
    const p = finalPos(id);
    dragRef.current = { id, dx: e.clientX - p.x * zoom, dy: e.clientY - p.y * zoom, moved: false };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onNodePointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const d = dragRef.current;
    d.moved = true;
    const nx = (e.clientX - d.dx) / zoom;
    const ny = (e.clientY - d.dy) / zoom;
    setManualPos((prev) => ({ ...prev, [d.id]: { x: nx, y: ny } }));
  };
  const onNodePointerUp = (e: React.PointerEvent) => {
    if (dragRef.current) {
      const d = dragRef.current;
      if (!d.moved) {
        selectNode(d.id); // 未移动 = 点击选中
      } else {
        scheduleSave(); // S76：拖拽结束 → 持久化坐标
      }
      dragRef.current = null;
    }
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  };

  /* ── 画布平移 ── */
  const onCanvasPointerDown = (e: React.PointerEvent) => {
    panRef.current = { x0: e.clientX, y0: e.clientY, px: pan.x, py: pan.y };
  };
  const onCanvasPointerMove = (e: React.PointerEvent) => {
    if (!panRef.current) return;
    const p = panRef.current;
    setPan({ x: p.px + (e.clientX - p.x0), y: p.py + (e.clientY - p.y0) });
  };
  const onCanvasPointerUp = () => (panRef.current = null);

  const onWheel = useCallback((e: React.WheelEvent) => {
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom((z) => Math.min(2.5, Math.max(0.3, z * factor)));
  }, []);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  const handleAdd = async () => {
    const content = newContent.trim();
    if (!content) return;
    try {
      await addNode(content, bookId, parentId || undefined);
      setNewContent("");
      setShowAddInput(false);
      setParentId(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleChoose = async (id: string) => {
    try {
      await choose(id);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const handleAnchor = async (id: string) => {
    try {
      await anchor(id);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const handleRemove = (id: string) => {
    setPendingRemoveId(id);
  };

  const confirmRemove = async () => {
    if (!pendingRemoveId) return;
    const id = pendingRemoveId;
    setPendingRemoveId(null);
    try {
      await removeNode(id);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  /* ── 连线（父→子 贝塞尔）── */
  const edgePath = (from: Pos, to: Pos) => {
    const x1 = from.x + NODE_W, y1 = from.y + NODE_H / 2;
    const x2 = to.x, y2 = to.y + NODE_H / 2;
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-2 shrink-0">
        <button
          onClick={() => {
            setShowAddInput(!showAddInput);
            setParentId(null);
          }}
          className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
            showAddInput ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          + 节点
        </button>
        <button
          onClick={() => {
            setManualPos({});
            setZoom(0.9);
            setPan({ x: 24, y: 24 });
          }}
          className="text-[11px] px-2 py-0.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
        >
          重置视图
        </button>
        <span className="text-[11px] text-zinc-600">|</span>
        <span className="text-[11px] text-zinc-500">
          {nodes.length} 节点 · {threads.filter((t) => t.status === "active").length} 线进行中 · 滚轮缩放 · 拖背景平移 · 拖节点移动
        </span>
        {error && <span className="text-[11px] text-red-400 ml-auto">{error}</span>}
      </div>

      {/* 添加输入条 */}
      {showAddInput && (
        <div className="px-3 py-2 bg-zinc-900/40 border-b border-zinc-800/50 flex items-center gap-2 shrink-0">
          <input
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            autoFocus
            placeholder={parentId ? "子节点内容（挂到所选父节点下）..." : "节点内容..."}
            className="flex-1 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
          <button
            onClick={handleAdd}
            className="text-[11px] px-2 py-1 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600"
          >
            添加
          </button>
          <button
            onClick={() => {
              setShowAddInput(false);
              setParentId(null);
            }}
            className="text-[11px] px-2 py-1 rounded text-zinc-500 hover:text-zinc-300"
          >
            取消
          </button>
        </div>
      )}

      {/* 画布 */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <div className="flex-1 overflow-hidden relative bg-zinc-950">
          <svg
            ref={svgRef}
            className="w-full h-full touch-none cursor-grab active:cursor-grabbing"
            onPointerDown={onCanvasPointerDown}
            onPointerMove={onCanvasPointerMove}
            onPointerUp={onCanvasPointerUp}
            onPointerLeave={onCanvasPointerUp}
            onWheel={onWheel}
          >
            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* 连线 */}
              {nodes
                .filter((n) => n.parent_id)
                .map((n) => {
                  const p = finalPos(n.parent_id!);
                  const c = finalPos(n.id);
                  return (
                    <path
                      key={`edge-${n.id}`}
                      d={edgePath(p, c)}
                      fill="none"
                      stroke="rgba(113,113,122,0.45)"
                      strokeWidth={1.6}
                    />
                  );
                })}
              {/* 节点 */}
              {nodes.map((n) => {
                const p = finalPos(n.id);
                const st = KIND_STYLES[n.kind];
                const selected = n.id === selectedNodeId;
                return (
                  <g
                    key={n.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    onPointerDown={(e) => onNodePointerDown(e, n.id)}
                    onPointerMove={onNodePointerMove}
                    onPointerUp={onNodePointerUp}
                    className="cursor-pointer"
                  >
                    {/* 选中高亮 */}
                    <rect
                      x={-4}
                      y={-4}
                      width={NODE_W + 8}
                      height={NODE_H + 8}
                      rx={8}
                      fill="none"
                      stroke={selected ? "#fbbf24" : "transparent"}
                      strokeWidth={selected ? 2 : 0}
                      strokeDasharray="4 3"
                    />
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill={st.fill}
                      stroke={st.stroke}
                      strokeWidth={1.5}
                    />
                    {/* kind 角标 */}
                    <rect x={NODE_W - 34} y={0} width={34} height={16} rx={4} fill={st.stroke} opacity={0.25} />
                    <text
                      x={NODE_W - 17}
                      y={11}
                      textAnchor="middle"
                      fontSize={9}
                      fill={st.text}
                    >
                      {st.label}
                    </text>
                    {/* 内容（截断） */}
                    <text
                      x={10}
                      y={NODE_H / 2 + 4}
                      fontSize={11}
                      fill="#e4e4e7"
                      style={{ pointerEvents: "none" }}
                    >
                      {n.content.length > 13 ? n.content.slice(0, 13) + "…" : n.content}
                    </text>
                    {/* chosen 标记 */}
                    {n.chosen && (
                      <circle cx={8} cy={NODE_H - 8} r={3.5} fill="#fbbf24" />
                    )}
                    {/* 操作小按钮（悬浮在节点右上） */}
                    <g
                      transform={`translate(${NODE_W - 20}, 20)`}
                      className="hover:opacity-100"
                      opacity={selected ? 1 : 0.25}
                    >
                      <circle
                        cx={0}
                        cy={0}
                        r={7}
                        fill="#27272a"
                        stroke="#52525b"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          setParentId(n.id);
                          setShowAddInput(true);
                        }}
                        aria-label="添加子节点"
                      />
                      <text x={0} y={3} textAnchor="middle" fontSize={9} fill="#a1a1aa">+</text>
                      <circle
                        cx={14}
                        cy={0}
                        r={7}
                        fill="#27272a"
                        stroke="#52525b"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleChoose(n.id);
                        }}
                        aria-label="选为主线"
                      />
                      <text x={14} y={3} textAnchor="middle" fontSize={9} fill="#34d399">✓</text>
                      <circle
                        cx={28}
                        cy={0}
                        r={7}
                        fill="#27272a"
                        stroke="#52525b"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemove(n.id);
                        }}
                        aria-label="删除（含后代）"
                      />
                      <text x={28} y={3} textAnchor="middle" fontSize={9} fill="#f87171">✕</text>
                    </g>
                  </g>
                );
              })}
              {/* 空态提示 */}
              {nodes.length === 0 && (
                <text x={20} y={30} fontSize={13} fill="#52525b">
                  叙事树为空——通过" + 节点"或探索来构建
                </text>
              )}
            </g>
          </svg>
        </div>

        {/* 右侧：详情面板 */}
        {selectedNode && (
          <div className="w-64 border-l border-zinc-800 bg-zinc-900/30 p-3 overflow-auto shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  KIND_STYLES[selectedNode.kind].stroke
                } text-[${KIND_STYLES[selectedNode.kind].text}] bg-zinc-900/50`}
              >
                {KIND_STYLES[selectedNode.kind].label}
              </span>
              <button onClick={() => selectNode(null)} className="text-zinc-600 hover:text-zinc-400 text-xs">
                ×
              </button>
            </div>
            <p className="text-sm text-zinc-200 mb-3 whitespace-pre-wrap">{selectedNode.content}</p>
            <div className="space-y-1.5">
              {selectedNode.kind !== "main" && (
                <button
                  onClick={() => handleChoose(selectedNode.id)}
                  className="w-full text-left text-xs px-2 py-1 rounded bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50 transition-colors"
                >
                  选为主线
                </button>
              )}
              {selectedNode.kind !== "anchor" && (
                <button
                  onClick={() => handleAnchor(selectedNode.id)}
                  className="w-full text-left text-xs px-2 py-1 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-colors"
                >
                  标为锚点
                </button>
              )}
              <button
                onClick={() => {
                  setParentId(selectedNode.id);
                  setShowAddInput(true);
                }}
                className="w-full text-left text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"
              >
                添加子节点
              </button>
              <button
                onClick={() => handleRemove(selectedNode.id)}
                className="w-full text-left text-xs px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40 transition-colors"
              >
                删除节点（含后代）
              </button>
            </div>
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <p className="text-[10px] text-zinc-600">创建：{new Date(selectedNode.created_at).toLocaleDateString()}</p>
              {selectedNode.chosen && <p className="text-[10px] text-emerald-500 mt-1">当前主线</p>}
            </div>
          </div>
        )}
      </div>

      <ConfirmModal
        open={!!pendingRemoveId}
        title="删除节点"
        message="确定删除该节点及其所有后代节点？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={confirmRemove}
        onCancel={() => setPendingRemoveId(null)}
      />
    </div>
  );
}
