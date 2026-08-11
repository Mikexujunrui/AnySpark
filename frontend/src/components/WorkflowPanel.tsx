import { useEffect, useMemo, useRef, useState } from "react";
import { useWorkflowStore } from "../stores/workflowStore";
import type {
  WorkflowDef,
  WorkflowNode,
  WorkflowEdge,
  WorkflowNodeKind,
  WorkflowTask,
} from "../api/workflow";

/* ── 节点样式 ── */
const KIND_META: Record<
  WorkflowNodeKind,
  { stroke: string; fill: string; text: string; shape: "rect" | "diamond" | "hex" }
> = {
  agent: { stroke: "#3b82f6", fill: "rgba(30,64,175,0.3)", text: "#93c5fd", shape: "rect" },
  script: { stroke: "#06b6d4", fill: "rgba(8,145,178,0.3)", text: "#67e8f9", shape: "rect" },
  approval: { stroke: "#a855f7", fill: "rgba(88,28,135,0.35)", text: "#d8b4fe", shape: "diamond" },
  gate: { stroke: "#f59e0b", fill: "rgba(146,64,14,0.3)", text: "#fcd34d", shape: "diamond" },
  loop: { stroke: "#f43f5e", fill: "rgba(136,19,55,0.35)", text: "#fda4af", shape: "rect" },
};
const KIND_LABEL: Record<WorkflowNodeKind, string> = {
  agent: "AI 节点",
  script: "脚本",
  approval: "审批",
  gate: "条件",
  loop: "循环",
};
const NODE_W = 148;
const NODE_H = 56;
const LAYER_GAP = 230;
const ROW_GAP = 96;

interface Pos {
  x: number;
  y: number;
}

interface State {
  task_id: string;
  node_id: string;
  status: string;
  output?: string;
  error?: string;
}

export default function WorkflowPanel() {
  const { templates, drafts, tasks, loading, fetchAll, openWorkflow, saveWorkflow, removeWorkflow, aiGenerate, promote, discardDraft, startRun, refreshTask, decide, setError } =
    useWorkflowStore();

  // 编辑中的定义（本地草稿态）
  const [draft, setDraft] = useState<WorkflowDef | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [placeKind, setPlaceKind] = useState<WorkflowNodeKind | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<string | null>(null);
  const [manualPos, setManualPos] = useState<Record<string, Pos>>({});
  const [zoom, setZoom] = useState(0.85);
  const [pan, setPan] = useState<Pos>({ x: 20, y: 20 });
  const [goalInput, setGoalInput] = useState("");
  const [showGenerate, setShowGenerate] = useState(false);
  const [dirty, setDirty] = useState(false);

  // 运行状态
  const [runningTask, setRunningTask] = useState<WorkflowTask | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);
  const panRef = useRef<{ x0: number; y0: number; px: number; py: number } | null>(null);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // 轮询清理
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  /* ── 布局：迭代最长路径分层 ── */
  const layout = useMemo(() => {
    const pos: Record<string, Pos> = {};
    if (!draft) return pos;
    const layer: Record<string, number> = {};
    for (const n of draft.nodes) layer[n.id] = 0;
    // 迭代：target 层 = max(所有入边 source 层 + 1)，最多 60 轮收敛
    for (let iter = 0; iter < 60; iter++) {
      let changed = false;
      for (const e of draft.edges) {
        const src = layer[e.source] ?? 0;
        const tgt = layer[e.target] ?? 0;
        if (tgt < src + 1) {
          layer[e.target] = src + 1;
          changed = true;
        }
      }
      if (!changed) break;
    }
    // 同层分组（按节点在数组中的顺序）
    const byLayer: Record<number, string[]> = {};
    for (const n of draft.nodes) {
      const l = layer[n.id] ?? 0;
      byLayer[l] = byLayer[l] ?? [];
      byLayer[l].push(n.id);
    }
    for (const l of Object.keys(byLayer)) {
      byLayer[+l].forEach((id, idx) => {
        pos[id] = { x: +l * LAYER_GAP, y: idx * ROW_GAP };
      });
    }
    return pos;
  }, [draft]);

  const finalPos = (id: string): Pos => manualPos[id] ?? layout[id] ?? { x: 0, y: 0 };

  // 节点运行状态（任务叠加）
  const nodeStateMap = useMemo(() => {
    const m: Record<string, State> = {};
    for (const s of runningTask?.node_states ?? []) m[s.node_id] = s;
    return m;
  }, [runningTask]);

  const nodeStroke = (n: WorkflowNode): string => {
    const st = nodeStateMap[n.id];
    if (runningTask) {
      if (st?.status === "done") return "#10b981";
      if (st?.status === "failed") return "#ef4444";
      if (st?.status === "running" || runningTask.current_node_id === n.id) return "#facc15";
    }
    return KIND_META[n.kind].stroke;
  };

  /* ── 编辑操作 ── */
  const patchDraft = (fn: (d: WorkflowDef) => WorkflowDef) => {
    if (!draft) return;
    setDraft(fn(structuredClone(draft)));
    setDirty(true);
  };

  const genId = (p: string) => `${p}-${Math.random().toString(36).slice(2, 8)}`;

  const addNodeAt = (kind: WorkflowNodeKind, x: number, y: number) => {
    patchDraft((d) => {
      const node: WorkflowNode = {
        id: genId("n"),
        kind,
        label: KIND_LABEL[kind],
        params: {},
        fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false },
      };
      d.nodes.push(node);
      setManualPos((prev) => ({ ...prev, [node.id]: { x, y } }));
      setSelectedNodeId(node.id);
      setSelectedEdgeId(null);
      return d;
    });
    setPlaceKind(null);
  };

  const removeNode = (id: string) => {
    patchDraft((d) => ({
      ...d,
      nodes: d.nodes.filter((n) => n.id !== id),
      edges: d.edges.filter((e) => e.source !== id && e.target !== id),
    }));
    setSelectedNodeId(null);
  };

  const addEdge = (source: string, target: string) => {
    if (source === target) return;
    patchDraft((d) => {
      // 去重：同 source→target 已存在则跳过
      if (d.edges.some((e) => e.source === source && e.target === target)) return d;
      d.edges.push({
        id: genId("e"),
        source,
        target,
        condition: null,
        label: "",
      });
      return d;
    });
  };

  const removeEdge = (id: string) => {
    patchDraft((d) => ({ ...d, edges: d.edges.filter((e) => e.id !== id) }));
    setSelectedEdgeId(null);
  };

  const updateNode = (id: string, fn: (n: WorkflowNode) => WorkflowNode) => {
    patchDraft((d) => ({
      ...d,
      nodes: d.nodes.map((n) => (n.id === id ? fn(structuredClone(n)) : n)),
    }));
  };

  const updateEdge = (id: string, fn: (e: WorkflowEdge) => WorkflowEdge) => {
    patchDraft((d) => ({
      ...d,
      edges: d.edges.map((e) => (e.id === id ? fn(structuredClone(e)) : e)),
    }));
  };

  /* ── 画布交互 ── */
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
    setManualPos((prev) => ({
      ...prev,
      [d.id]: { x: (e.clientX - d.dx) / zoom, y: (e.clientY - d.dy) / zoom },
    }));
  };
  const onNodePointerUp = (e: React.PointerEvent, id: string) => {
    if (dragRef.current) {
      if (!dragRef.current.moved) {
        setSelectedNodeId(id);
        setSelectedEdgeId(null);
        setPlaceKind(null);
        setConnectingFrom(null);
      }
      dragRef.current = null;
    }
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  };

  const onCanvasPointerDown = (e: React.PointerEvent) => {
    panRef.current = { x0: e.clientX, y0: e.clientY, px: pan.x, py: pan.y };
  };
  const onCanvasPointerMove = (e: React.PointerEvent) => {
    if (!panRef.current) return;
    const p = panRef.current;
    setPan({ x: p.px + (e.clientX - p.x0), y: p.py + (e.clientY - p.y0) });
  };
  const onCanvasPointerUp = () => (panRef.current = null);

  const onCanvasClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      // 点空白：取消选中；放置模式下放置节点
      if (placeKind) {
        const svg = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
        const x = (e.clientX - svg.left - pan.x) / zoom;
        const y = (e.clientY - svg.top - pan.y) / zoom;
        addNodeAt(placeKind, x, y);
      } else {
        setSelectedNodeId(null);
        setSelectedEdgeId(null);
      }
    }
  };

  const onWheel = (e: React.WheelEvent) => {
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom((z) => Math.min(2, Math.max(0.3, z * factor)));
  };

  const edgePath = (from: Pos, to: Pos, diamond = false) => {
    const w = diamond ? NODE_W * 0.85 : NODE_W;
    const x1 = from.x + w, y1 = from.y + NODE_H / 2;
    const x2 = to.x, y2 = to.y + NODE_H / 2;
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  };

  const condText = (e: WorkflowEdge): string => {
    if (e.condition?.label) return e.condition.label;
    if (e.condition?.type === "rule") return e.condition.expression ?? "";
    if (e.condition?.type === "model") return e.condition.prompt ?? "";
    return "";
  };

  const selectedNode = draft?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedEdge = draft?.edges.find((e) => e.id === selectedEdgeId) ?? null;
  const nodesById = useMemo(() => {
    const m: Record<string, WorkflowNode> = {};
    for (const n of draft?.nodes ?? []) m[n.id] = n;
    return m;
  }, [draft]);

  /* ── 运行 ── */
  const handleRun = async (id: string) => {
    try {
      setError(null);
      const taskId = await startRun(id);
      const task = await refreshTask(taskId);
      setRunningTask(task);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const t = await refreshTask(taskId);
          setRunningTask(t);
          if (t.status === "done" || t.status === "failed" || t.status === "cancelled") {
            if (pollRef.current) clearInterval(pollRef.current);
            fetchAll();
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "运行失败");
    }
  };

  const handleDecide = async (decision: "ok" | "reject") => {
    if (!runningTask) return;
    try {
      await decide(runningTask.id, decision);
      const t = await refreshTask(runningTask.id);
      setRunningTask(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "审批失败");
    }
  };

  /* ── 节点/边形状渲染 ── */
  const renderShape = (n: WorkflowNode, x: number, y: number, selected: boolean, stroke: string) => {
    const meta = KIND_META[n.kind];
    const w = NODE_W, h = NODE_H;
    const common = {
      stroke,
      strokeWidth: selected ? 2.5 : 1.5,
      fill: meta.fill,
    };
    if (meta.shape === "diamond") {
      return (
        <polygon
          points={`${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}`}
          {...common}
        />
      );
    }
    return <rect x={x} y={y} width={w} height={h} rx={8} {...common} />;
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-2 shrink-0">
        <span className="text-[11px] text-zinc-400 font-medium">工作流</span>
        <span className="text-[11px] text-zinc-600">|</span>
        {/* 节点类型放置 */}
        {(Object.keys(KIND_META) as WorkflowNodeKind[]).map((k) => (
          <button
            key={k}
            onClick={() => {
              setPlaceKind(placeKind === k ? null : k);
              setConnectingFrom(null);
            }}
            className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
              placeKind === k
                ? "bg-zinc-700 text-zinc-200"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }`}
            style={placeKind === k ? { border: `1px solid ${KIND_META[k].stroke}` } : undefined}
          >
            +{KIND_LABEL[k]}
          </button>
        ))}
        <span className="text-[11px] text-zinc-600">|</span>
        <button
          onClick={() => setShowGenerate(!showGenerate)}
          className="text-[11px] px-2 py-0.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
        >
          AI 生成
        </button>
        {dirty && draft && (
          <button
            onClick={async () => {
              try {
                await saveWorkflow(draft);
                setDirty(false);
                fetchAll();
              } catch (e) {
                setError(e instanceof Error ? e.message : "保存失败");
              }
            }}
            className="text-[11px] px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-400 hover:bg-emerald-900/60"
          >
            保存模板
          </button>
        )}
        <span className="ml-auto text-[11px] text-zinc-600">
          {runningTask ? `运行中任务: ${runningTask.status}` : "滚轮缩放 · 拖背景平移 · 拖节点移动 · 点节点右侧◎连线"}
        </span>
      </div>

      {/* AI 生成输入条 */}
      {showGenerate && (
        <div className="px-3 py-2 bg-zinc-900/40 border-b border-zinc-800/50 flex items-center gap-2 shrink-0">
          <input
            value={goalInput}
            onChange={(e) => setGoalInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && goalInput.trim() && aiGenerate(goalInput.trim())}
            autoFocus
            placeholder="描述工作流目标，如：审读章节，有硬伤则改写并复检，最后作者确认"
            className="flex-1 text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          />
          <button
            onClick={() => goalInput.trim() && aiGenerate(goalInput.trim())}
            className="text-[11px] px-2 py-1 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600"
          >
            生成草稿
          </button>
          <button
            onClick={() => setShowGenerate(false)}
            className="text-[11px] px-2 py-1 rounded text-zinc-500 hover:text-zinc-300"
          >
            取消
          </button>
        </div>
      )}

      <div className="flex-1 min-h-0 flex">
        {/* 左侧：模板/草稿/任务 */}
        <div className="w-60 shrink-0 border-r border-zinc-800 overflow-auto bg-zinc-900/20">
          <div className="p-2 space-y-4">
            {/* 模板 */}
            <div>
              <div className="flex items-center justify-between px-1 mb-1">
                <span className="text-[10px] text-zinc-500 font-medium">模板（{templates.length}）</span>
                <button
                  onClick={() => {
                    const wf: WorkflowDef = {
                      id: "",
                      name: "未命名工作流",
                      description: "",
                      nodes: [],
                      edges: [],
                    };
                    setDraft(wf);
                    setDirty(true);
                    setSelectedNodeId(null);
                  }}
                  className="text-[10px] text-zinc-500 hover:text-zinc-300"
                >
                  + 新建
                </button>
              </div>
              {loading && templates.length === 0 ? (
                <p className="text-[11px] text-zinc-600 px-1">加载中...</p>
              ) : templates.length === 0 ? (
                <p className="text-[11px] text-zinc-700 px-1">暂无模板</p>
              ) : (
                templates.map((t) => (
                  <div
                    key={t.id}
                    onClick={() => openWorkflow(t.id).then(() => {
                      setDirty(false);
                      setRunningTask(null);
                      setSelectedNodeId(null);
                    })}
                    className={`px-2 py-1.5 rounded mb-0.5 cursor-pointer text-xs ${
                      draft?.id === t.id
                        ? "bg-zinc-700/60 text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-800/60"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate">{t.name}</span>
                      <span className="text-[10px] text-zinc-600">模板</span>
                    </div>
                    {t.description && (
                      <p className="text-[10px] text-zinc-600 truncate mt-0.5">{t.description}</p>
                    )}
                    <div className="flex gap-2 mt-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRun(t.id);
                        }}
                        className="text-[10px] text-emerald-500 hover:text-emerald-400"
                      >
                        ▶ 运行
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(`删除模板「${t.name}」？`)) removeWorkflow(t.id);
                        }}
                        className="text-[10px] text-red-500 hover:text-red-400"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* 草稿 */}
            {drafts.length > 0 && (
              <div>
                <span className="text-[10px] text-zinc-500 font-medium px-1">AI 草稿（待确认）</span>
                {drafts.map((d) => (
                  <div key={d.id} className="px-2 py-1.5 rounded mb-0.5 bg-amber-900/10 border border-amber-900/30">
                    <p className="text-xs text-amber-200 truncate">{d.name}</p>
                    <div className="flex gap-2 mt-1">
                      <button
                        onClick={() => promote(d.id)}
                        className="text-[10px] text-emerald-500 hover:text-emerald-400"
                      >
                        转正
                      </button>
                      <button
                        onClick={() => discardDraft(d.id)}
                        className="text-[10px] text-zinc-500 hover:text-zinc-300"
                      >
                        丢弃
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 任务 */}
            <div>
              <span className="text-[10px] text-zinc-500 font-medium px-1">任务（{tasks.length}）</span>
              {tasks.map((t) => (
                <div key={t.id} className="px-2 py-1.5 rounded mb-0.5 bg-zinc-900/40 border border-zinc-800">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-zinc-400 truncate">{t.name}</span>
                    <span
                      className={`text-[10px] ${
                        t.status === "done" ? "text-emerald-500" :
                        t.status === "failed" ? "text-red-500" :
                        t.status === "waiting_approval" ? "text-purple-400" :
                        t.status === "running" ? "text-yellow-500" : "text-zinc-500"
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                  {t.status === "waiting_approval" && (
                    <div className="flex gap-2 mt-1">
                      <button
                        onClick={() => handleDecide("ok")}
                        className="text-[10px] text-emerald-500 hover:text-emerald-400"
                      >
                        通过 ✓
                      </button>
                      <button
                        onClick={() => handleDecide("reject")}
                        className="text-[10px] text-red-500 hover:text-red-400"
                      >
                        拒绝 ✗
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右侧：画布 */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {draft ? (
            <>
              {/* 画布区 */}
              <div className="flex-1 min-h-0 overflow-hidden relative bg-zinc-950">
                <svg
                  className="w-full h-full touch-none cursor-grab active:cursor-grabbing"
                  onPointerDown={onCanvasPointerDown}
                  onPointerMove={onCanvasPointerMove}
                  onPointerUp={onCanvasPointerUp}
                  onPointerLeave={onCanvasPointerUp}
                  onWheel={onWheel}
                  onClick={onCanvasClick}
                >
                  <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                    {/* 边 */}
                    {draft.edges.map((e) => {
                      const from = finalPos(e.source);
                      const to = finalPos(e.target);
                      const fromNode = nodesById[e.source];
                      const toNode = nodesById[e.target];
                      const sel = e.id === selectedEdgeId;
                      const diamond = (fromNode?.kind === "gate" || fromNode?.kind === "approval") ||
                        (toNode?.kind === "gate" || toNode?.kind === "approval");
                      const d = edgePath(from, to, diamond);
                      const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
                      const label = condText(e);
                      return (
                        <g key={e.id} className="cursor-pointer">
                          <path
                            d={d}
                            fill="none"
                            stroke={sel ? "#fbbf24" : "rgba(113,113,122,0.55)"}
                            strokeWidth={sel ? 2.5 : 1.5}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              setSelectedEdgeId(e.id);
                              setSelectedNodeId(null);
                            }}
                          />
                          {label && (
                            <g
                              onClick={(ev) => {
                                ev.stopPropagation();
                                setSelectedEdgeId(e.id);
                                setSelectedNodeId(null);
                              }}
                            >
                              <rect
                                x={mid.x - label.length * 3.2 - 6}
                                y={mid.y - 10}
                                width={label.length * 6.4 + 12}
                                height={16}
                                rx={4}
                                fill="#18181b"
                                stroke="#3f3f46"
                              />
                              <text
                                x={mid.x}
                                y={mid.y + 2}
                                textAnchor="middle"
                                fontSize={9}
                                fill="#d4d4d8"
                              >
                                {label.length > 14 ? label.slice(0, 14) + "…" : label}
                              </text>
                            </g>
                          )}
                          {/* 边删除按钮 */}
                          {sel && (
                            <g
                              transform={`translate(${mid.x}, ${mid.y + 18})`}
                              onClick={(ev) => {
                                ev.stopPropagation();
                                removeEdge(e.id);
                              }}
                              className="cursor-pointer"
                            >
                              <circle r={8} fill="#27272a" stroke="#ef4444" />
                              <text x={0} y={3} textAnchor="middle" fontSize={9} fill="#f87171">✕</text>
                            </g>
                          )}
                        </g>
                      );
                    })}

                    {/* 连接中提示线 */}
                    {connectingFrom && (
                      <line
                        x1={finalPos(connectingFrom).x + NODE_W}
                        y1={finalPos(connectingFrom).y + NODE_H / 2}
                        x2={finalPos(connectingFrom).x + NODE_W + 80}
                        y2={finalPos(connectingFrom).y + NODE_H / 2}
                        stroke="#fbbf24"
                        strokeWidth={2}
                        strokeDasharray="4 3"
                      />
                    )}

                    {/* 节点 */}
                    {draft.nodes.map((n) => {
                      const p = finalPos(n.id);
                      const sel = n.id === selectedNodeId;
                      const stroke = nodeStroke(n);
                      const meta = KIND_META[n.kind];
                      const st = nodeStateMap[n.id];
                      return (
                        <g
                          key={n.id}
                          transform={`translate(${p.x}, ${p.y})`}
                          className="cursor-pointer"
                          onPointerDown={(e) => onNodePointerDown(e, n.id)}
                          onPointerMove={onNodePointerMove}
                          onPointerUp={(e) => onNodePointerUp(e, n.id)}
                        >
                          {/* 连线出口（右侧手柄） */}
                          <circle
                            cx={NODE_W + 6}
                            cy={NODE_H / 2}
                            r={7}
                            fill="#3f3f46"
                            stroke={connectingFrom === n.id ? "#fbbf24" : "#71717a"}
                            strokeWidth={1.5}
                            onPointerDown={(e) => {
                              e.stopPropagation();
                              setConnectingFrom(n.id);
                              setSelectedNodeId(n.id);
                              setSelectedEdgeId(null);
                            }}
                            onPointerUp={(e) => {
                              e.stopPropagation();
                              if (connectingFrom === n.id) {
                                setConnectingFrom(null);
                              }
                            }}
                            onMouseEnter={() => {
                              if (connectingFrom && connectingFrom !== n.id) {
                                addEdge(connectingFrom, n.id);
                                setConnectingFrom(null);
                              }
                            }}
                            aria-label="连线出口"
                          />
                          {renderShape(n, 0, 0, sel, stroke)}
                          {/* 标签 */}
                          <text
                            x={NODE_W / 2}
                            y={NODE_H / 2 + 2}
                            textAnchor="middle"
                            fontSize={11}
                            fontWeight={600}
                            fill={meta.text}
                            style={{ pointerEvents: "none" }}
                          >
                            {n.label && n.label.length > 10 ? n.label.slice(0, 10) + "…" : n.label || n.id}
                          </text>
                          <text
                            x={NODE_W / 2}
                            y={NODE_H / 2 + 16}
                            textAnchor="middle"
                            fontSize={8.5}
                            fill="rgba(212,212,216,0.6)"
                            style={{ pointerEvents: "none" }}
                          >
                            {KIND_LABEL[n.kind]}
                          </text>
                          {/* 运行状态角标 */}
                          {st && (
                            <g transform={`translate(${NODE_W / 2}, -10)`}>
                              <rect x={-22} y={-7} width={44} height={14} rx={4} fill="#18181b" stroke={stroke} strokeWidth={1} />
                              <text x={0} y={3} textAnchor="middle" fontSize={8} fill={st.status === "done" ? "#6ee7b7" : st.status === "failed" ? "#fca5a5" : "#fde047"}>
                                {st.status === "done" ? "完成" : st.status === "failed" ? "失败" : st.status === "running" ? "运行中" : st.status}
                              </text>
                            </g>
                          )}
                          {/* 删除按钮（选中时） */}
                          {sel && (
                            <g
                              transform={`translate(${NODE_W + 6}, -14)`}
                              onClick={(e) => {
                                e.stopPropagation();
                                removeNode(n.id);
                              }}
                              className="cursor-pointer"
                            >
                              <circle r={8} fill="#27272a" stroke="#ef4444" />
                              <text x={0} y={3} textAnchor="middle" fontSize={9} fill="#f87171">✕</text>
                            </g>
                          )}
                        </g>
                      );
                    })}

                    {/* 放置提示 */}
                    {placeKind && (
                      <text x={12} y={-12} fontSize={12} fill={KIND_META[placeKind].stroke}>
                        点击空白处放置 {KIND_LABEL[placeKind]} 节点
                      </text>
                    )}
                  </g>
                </svg>
              </div>

              {/* 底部：属性编辑 */}
              <div className="h-44 shrink-0 border-t border-zinc-800 bg-zinc-900/40 overflow-auto">
                {selectedNode ? (
                  <NodeEditor node={selectedNode} onChange={(n) => updateNode(selectedNode.id, () => n)} onDelete={() => removeNode(selectedNode.id)} />
                ) : selectedEdge ? (
                  <EdgeEditor edge={selectedEdge} onChange={(e) => updateEdge(selectedEdge.id, () => e)} onDelete={() => removeEdge(selectedEdge.id)} />
                ) : (
                  <div className="p-3 text-[11px] text-zinc-600">
                    选中节点或边进行编辑；点节点右侧 ◎ 手柄拖到另一节点创建连线；gate 条件的表达式在边属性里编辑。
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-zinc-600">
              {loading ? "加载中..." : "从左侧选择模板，或点「+ 新建」开始设计工作流"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── 节点属性编辑 ── */
function NodeEditor({
  node,
  onChange,
  onDelete,
}: {
  node: WorkflowNode;
  onChange: (n: WorkflowNode) => void;
  onDelete: () => void;
}) {
  const set = (patch: Partial<WorkflowNode>) => onChange({ ...node, ...patch });
  const setParam = (k: string, v: unknown) => onChange({ ...node, params: { ...node.params, [k]: v } });
  const setFail = (patch: Partial<WorkflowNode["fail"]>) => onChange({ ...node, fail: { ...node.fail, ...patch } });

  return (
    <div className="p-3 flex flex-wrap gap-x-6 gap-y-2 items-start">
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">标签</label>
        <input
          value={node.label}
          onChange={(e) => set({ label: e.target.value })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 200 }}
        />
      </div>
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">类型（不可改）</label>
        <span className="text-xs text-zinc-400">{KIND_LABEL[node.kind]}</span>
      </div>

      {node.kind === "agent" || node.kind === "script" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">指令 instruction</label>
            <textarea
              value={(node.params.instruction as string) ?? ""}
              onChange={(e) => setParam("instruction", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 w-72 h-20 resize-none"
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">输出键 output_key</label>
            <input
              value={(node.params.output_key as string) ?? ""}
              onChange={(e) => setParam("output_key", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 120 }}
            />
          </div>
        </>
      ) : node.kind === "approval" ? (
        <div>
          <label className="block text-[10px] text-zinc-500 mb-0.5">审批提示 prompt</label>
          <textarea
            value={(node.params.prompt as string) ?? ""}
            onChange={(e) => setParam("prompt", e.target.value)}
            className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500 w-72 h-20 resize-none"
          />
        </div>
      ) : node.kind === "loop" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">最大迭代 max_iterations</label>
            <input
              type="number"
              value={(node.params.max_iterations as number) ?? 1}
              onChange={(e) => setParam("max_iterations", Number(e.target.value))}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 80 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">继续条件 continue_condition</label>
            <input
              value={(node.params.continue_condition as string) ?? ""}
              onChange={(e) => setParam("continue_condition", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 240 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">循环体 body</label>
            <input
              value={((node.params.body as string[]) ?? []).join(",")}
              onChange={(e) =>
                setParam("body", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
              }
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 160 }}
              placeholder="节点id1,节点id2"
            />
          </div>
        </>
      ) : (
        <div className="text-[11px] text-zinc-600 max-w-xs">
          条件节点：出边的条件在边属性里设置（点条件标签编辑）。
        </div>
      )}

      {/* 失败策略 */}
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">失败自动重试</label>
        <input
          type="number"
          value={node.fail.auto_retry_count}
          onChange={(e) => setFail({ auto_retry_count: Number(e.target.value) })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 60 }}
        />
      </div>
      <label className="flex items-center gap-1.5 text-[11px] text-zinc-400 mt-4 cursor-pointer">
        <input
          type="checkbox"
          checked={node.fail.fail_auto_skip}
          onChange={(e) => setFail({ fail_auto_skip: e.target.checked })}
        />
        重试耗尽跳过
      </label>

      <button
        onClick={onDelete}
        className="ml-auto text-[11px] px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40"
      >
        删除节点
      </button>
    </div>
  );
}

/* ── 边属性编辑 ── */
function EdgeEditor({
  edge,
  onChange,
  onDelete,
}: {
  edge: WorkflowEdge;
  onChange: (e: WorkflowEdge) => void;
  onDelete: () => void;
}) {
  const cond = edge.condition ?? { type: "rule" as const, expression: "" };
  const setCond = (patch: Partial<typeof cond>) => {
    onChange({ ...edge, condition: { ...cond, ...patch } });
  };
  return (
    <div className="p-3 flex flex-wrap gap-x-6 gap-y-2 items-start">
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">条件类型</label>
        <select
          value={cond.type}
          onChange={(e) => setCond({ type: e.target.value as "rule" | "model" })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none"
        >
          <option value="rule">规则 rule</option>
          <option value="model">模型判断 model</option>
        </select>
      </div>
      {cond.type === "rule" ? (
        <div>
          <label className="block text-[10px] text-zinc-500 mb-0.5">{"表达式（{{var}} 引用前序输出）"}</label>
          <input
            value={cond.expression ?? ""}
            onChange={(e) => setCond({ expression: e.target.value })}
            placeholder="例：{{review}} contains '硬伤'"
            className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
            style={{ width: 260 }}
          />
        </div>
      ) : (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">模型问题 prompt</label>
            <input
              value={cond.prompt ?? ""}
              onChange={(e) => setCond({ prompt: e.target.value })}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 240 }}
            />
          </div>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">期望回答 expect</label>
            <input
              value={cond.expect ?? ""}
              onChange={(e) => setCond({ expect: e.target.value })}
              placeholder="yes"
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 100 }}
            />
          </div>
        </>
      )}
      <div>
        <label className="block text-[10px] text-zinc-500 mb-0.5">边标签（可选，显示在线上）</label>
        <input
          value={edge.label ?? cond.label ?? ""}
          onChange={(e) => setCond({ label: e.target.value })}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
          style={{ width: 140 }}
        />
      </div>
      <button
        onClick={onDelete}
        className="ml-auto text-[11px] px-2 py-1 rounded bg-red-900/20 text-red-400 hover:bg-red-900/40"
      >
        删除连线
      </button>
    </div>
  );
}
