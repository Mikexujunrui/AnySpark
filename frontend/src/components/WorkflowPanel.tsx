import { useEffect, useMemo, useRef, useState } from "react";
import { useWorkflowStore } from "../stores/workflowStore";
import type {
  WorkflowDef,
  WorkflowNode,
  WorkflowEdge,
  WorkflowNodeKind,
  WorkflowTask,
} from "../api/workflow";
import ConfirmModal from "./ui/ConfirmModal";
import { loopVirtualEdges, layoutEdges, snapGrid, wouldCreateCycle, flowTerminalNodes } from "../lib/workflowLayout";

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

/* ── script 函数目录（画布选择器） ── */
const SCRIPT_FUNCTIONS: Record<string, { label: string; params: { key: string; label: string; placeholder?: string; type?: "number" }[] }> = {
  read_chapter: {
    label: "读章节正文",
    params: [{ key: "chapter_title", label: "章名" }],
  },
  read_settings: {
    label: "读设定档（正典）",
    params: [
      { key: "keyword", label: "关键词过滤", placeholder: "留空=全部" },
      { key: "limit", label: "条数上限", type: "number" },
    ],
  },
  read_graph: {
    label: "读图谱（人物/状态/关系）",
    params: [
      { key: "keyword", label: "实体名过滤", placeholder: "留空=Top N" },
      { key: "limit", label: "实体上限", type: "number" },
    ],
  },
  query_reference: {
    label: "查参考书（分级检索）",
    params: [
      { key: "keyword", label: "检索词" },
      { key: "max_per_book", label: "每书段数", type: "number" },
    ],
  },
  list_chapters: { label: "列章节", params: [] },
  review_chapter: {
    label: "审读章节（检测网）",
    params: [{ key: "chapter_title", label: "章名" }],
  },
  write_chapter: {
    label: "写回章节",
    params: [
      { key: "chapter_title", label: "章名" },
      { key: "text_key", label: "内容变量", placeholder: "缺省 rewritten" },
    ],
  },
  noop: { label: "无操作（占位）", params: [] },
};
const SCRIPT_FN_NAMES = Object.keys(SCRIPT_FUNCTIONS);
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

export default function WorkflowPanel({ bookId }: { bookId: string }) {
  const { templates, drafts, tasks, loading, fetchAll, openWorkflow, saveWorkflow, removeWorkflow, aiGenerate, promote, discardDraft, startRun, refreshTask, decide, setError } =
    useWorkflowStore();

  // 编辑中的定义（本地草稿态）
  const [draft, setDraft] = useState<WorkflowDef | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [placeKind, setPlaceKind] = useState<WorkflowNodeKind | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<string | null>(null);
  // 节点手动拖拽位置（本地，不持久化）
  // 扩展点（DESIGN §12.37）：持久化时在此接入 —— 数据即本 state；方案：
  // WorkflowDef 加 layout 字段（随模板 definition JSON 存）+ WorkflowIn 增 layout，保存模板时序列化
  const [manualPos, setManualPos] = useState<Record<string, Pos>>({});
  const [zoom, setZoom] = useState(0.85);
  const [pan, setPan] = useState<Pos>({ x: 20, y: 20 });
  const [goalInput, setGoalInput] = useState("");
  const [showGenerate, setShowGenerate] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pendingDeleteWf, setPendingDeleteWf] = useState<string | null>(null);
  // S152d：右键菜单 / 迷你地图 / 适配视图
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; kind: "node" | "edge" | "canvas"; id?: string } | null>(null);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [showExecLog, setShowExecLog] = useState(false); // S152e：执行明细浮层
  const canvasWrapRef = useRef<HTMLDivElement>(null);

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

  /* ── 布局：迭代最长路径分层（真实边 + loop body 虚拟边，环回边不参与）── */
  const layout = useMemo(() => {
    const pos: Record<string, Pos> = {};
    if (!draft) return pos;
    const layer: Record<string, number> = {};
    for (const n of draft.nodes) layer[n.id] = 0;
    // 迭代：target 层 = max(所有入边 source 层 + 1)，最多 60 轮收敛
    for (let iter = 0; iter < 60; iter++) {
      let changed = false;
      for (const e of layoutEdges(draft)) {
        if (layer[e.source] === undefined || layer[e.target] === undefined) continue;
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

  // S152e：运行反馈——当前执行节点/完成统计/进度百分比/当前节点名
  const runningNodeId = useMemo(() => {
    if (!runningTask) return null;
    return (
      runningTask.current_node_id ??
      (runningTask.node_states ?? []).find((s) => s.status === "running")?.node_id ??
      null
    );
  }, [runningTask]);
  const runningDoneCount = useMemo(
    () => (runningTask?.node_states ?? []).filter((s) => s.status === "done").length,
    [runningTask]
  );
  const runningTotalCount = draft?.nodes.length ?? 1;
  const runningProgressPct = Math.min(
    100,
    Math.round((runningDoneCount / Math.max(runningTotalCount, 1)) * 100)
  );
  const runningCurrentLabel = useMemo(() => {
    if (!runningTask) return "";
    const cid = runningNodeId;
    if (cid) return draft?.nodes.find((n) => n.id === cid)?.label ?? cid;
    return runningTask.status;
  }, [runningTask, runningNodeId, draft]);

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
      // S152c：放置位置 snap 网格
      setManualPos((prev) => ({ ...prev, [node.id]: { x: snapGrid(x), y: snapGrid(y) } }));
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
    setCtxMenu(null);
  };

  // S152d：复制节点（新 id + 位置偏移；复制其出边指向原下游；入边不复制避免双输入）
  const duplicateNode = (id: string) => {
    patchDraft((d) => {
      const src = d.nodes.find((n) => n.id === id);
      if (!src) return d;
      const clone: WorkflowNode = {
        ...structuredClone(src),
        id: genId("n"),
        label: (src.label || src.id) + " 副本",
      };
      const p = finalPos(id);
      const cloneId = clone.id;
      d.nodes.push(clone);
      setManualPos((prev) => ({ ...prev, [cloneId]: { x: snapGrid(p.x + 24), y: snapGrid(p.y + 24) } }));
      // 复制出边（源指向原下游；入边不复制）
      for (const e of d.edges) {
        if (e.source === id) {
          d.edges.push({ ...structuredClone(e), id: genId("e"), source: cloneId });
        }
      }
      setSelectedNodeId(cloneId);
      return d;
    });
    setCtxMenu(null);
  };

  // S152d：右键菜单操作
  const handleCtxAction = (action: "delete" | "duplicate") => {
    if (!ctxMenu) return;
    if (ctxMenu.kind === "node" && ctxMenu.id) {
      if (action === "delete") removeNode(ctxMenu.id);
      else duplicateNode(ctxMenu.id);
    } else if (ctxMenu.kind === "edge" && ctxMenu.id) {
      if (action === "delete") removeEdge(ctxMenu.id);
    } else if (ctxMenu.kind === "canvas") {
      if (action === "delete") {
        setSelectedNodeId(null);
        setSelectedEdgeId(null);
      }
    }
    setCtxMenu(null);
  };

  // S152d：键盘 Delete/Backspace 删除选中（输入框聚焦时不触发）+ 点击外部关闭右键菜单
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (ctxMenu) {
        setCtxMenu(null);
        return;
      }
      if (selectedNodeId) {
        e.preventDefault();
        removeNode(selectedNodeId);
      } else if (selectedEdgeId) {
        e.preventDefault();
        removeEdge(selectedEdgeId);
      }
    };
    const onDocDown = (e: MouseEvent) => {
      if (!ctxMenu) return;
      const el = e.target as HTMLElement | null;
      if (el && el.closest?.("[data-wf-context-menu]")) return;
      setCtxMenu(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDocDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDocDown);
    };
  });

  // S152d：适配视图——缩放/平移使全部节点可见
  const fitView = () => {
    const wrap = canvasWrapRef.current;
    if (!wrap || !draft || draft.nodes.length === 0) return;
    const xs = draft.nodes.map((n) => finalPos(n.id).x);
    const x2s = draft.nodes.map((n) => finalPos(n.id).x + NODE_W);
    const ys = draft.nodes.map((n) => finalPos(n.id).y);
    const y2s = draft.nodes.map((n) => finalPos(n.id).y + NODE_H);
    const x0 = Math.min(...xs) - LAYER_GAP;
    const x1 = Math.max(...x2s) + LAYER_GAP;
    const y0 = Math.min(...ys) - ROW_GAP;
    const y1 = Math.max(...y2s) + ROW_GAP;
    const bw = x1 - x0;
    const bh = y1 - y0;
    const scale = Math.min(
      2,
      Math.max(0.3, Math.min(wrap.clientWidth / bw, wrap.clientHeight / bh))
    );
    setZoom(scale);
    setPan({ x: 24 - x0 * scale, y: 24 - y0 * scale });
  };

  // S152c：加边带防环校验（与后端 validate 一致；loop 节点豁免回边）
  const addEdge = (source: string, target: string): boolean => {
    if (source === target) return false;
    const loopIds = new Set(draft?.nodes.filter((n) => n.kind === "loop").map((n) => n.id));
    const ok = !wouldCreateCycle(source, target, draft?.edges ?? [], loopIds);
    if (!ok) {
      setError("⚠️ 该连线会形成循环（loop 除外）——已拦截");
      return false;
    }
    setError(null);
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
    return true;
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
    // S152c：拖拽位置 snap 10px 网格
    setManualPos((prev) => ({
      ...prev,
      [d.id]: {
        x: snapGrid((e.clientX - d.dx) / zoom),
        y: snapGrid((e.clientY - d.dy) / zoom),
      },
    }));
  };
  const onNodePointerUp = (e: React.PointerEvent, id: string) => {
    if (dragRef.current) {
      if (!dragRef.current.moved) {
        // S152c：两段式连线——处于连接态时点击目标节点完成连线
        if (connectingFrom && connectingFrom !== id) {
          const from = connectingFrom;
          setConnectingFrom(null);
          addEdge(from, id);
        } else {
          setSelectedNodeId(id);
          setSelectedEdgeId(null);
          setPlaceKind(null);
          setConnectingFrom(null);
        }
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
  const [runParamsText, setRunParamsText] = useState("");
  const parseRunParams = (): Record<string, string> | null => {
    const t = runParamsText.trim();
    if (!t) return {};
    try {
      const obj = JSON.parse(t) as Record<string, unknown>;
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(obj)) out[k] = String(v);
      return out;
    } catch {
      setError("运行参数不是合法 JSON");
      return null;
    }
  };
  const handleRun = async (id: string) => {
    try {
      setError(null);
      const params = parseRunParams();
      if (params === null) return;
      // S152：运行时绑定当前项目（此前硬编码 main，跨项目写错书）
      const taskId = await startRun(id, bookId, params);
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
                // S76：保存时把画布手动坐标序列化进模板 layout
                // S152：保存后同步 draft.id（新建时后端生成），保证后续保存=原地更新
                const wfToSave = { ...draft, layout: manualPos };
                await saveWorkflow(wfToSave);
                const saved = useWorkflowStore.getState().current;
                if (saved) setDraft(saved);
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
        {/* S152e：任务进度条（运行中时） */}
        {runningTask && (
          <div className="ml-auto flex items-center gap-2 select-none">
            <div className="w-44 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${runningProgressPct}%`,
                  background: runningTask.status === "failed" ? "#ef4444" : "#10b981",
                }}
              />
            </div>
            <span className="text-[11px] text-zinc-400 whitespace-nowrap">
              {runningDoneCount}/{runningTotalCount}{" "}
              {runningTask.status === "done" ? "· 完成" : runningTask.status === "failed" ? "· 失败" : runningTask.status === "waiting_approval" ? "· 等待确认" : runningTask.status === "cancelled" ? "· 已取消" : `· 正在执行: ${runningCurrentLabel}`}
            </span>
          </div>
        )}
        {!runningTask && (
          <span className="ml-auto text-[11px] text-zinc-600">
            滚轮缩放 · 拖背景平移 · 拖节点移动 · 点节点右侧◎拖到目标节点连线（gate 可拖多条）
          </span>
        )}
      </div>

      {/* 运行参数输入条（可选 JSON：{{var}} 初始值，如 {"chapter_title":"第五章"}） */}
      <div className="px-3 py-1.5 bg-zinc-900/30 border-b border-zinc-800/40 flex items-center gap-2 shrink-0">
        <span className="text-[10px] text-zinc-600 whitespace-nowrap">运行参数 JSON（可选）</span>
        <input
          value={runParamsText}
          onChange={(e) => setRunParamsText(e.target.value)}
          placeholder={'{"chapter_title": "第五章", "ref_keyword": "怀表"}'}
          className="flex-1 text-[11px] bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-zinc-300 outline-none focus:border-zinc-500 font-mono"
        />
        {runParamsText.trim() && (
          <button
            onClick={() => setRunParamsText("")}
            className="text-[10px] text-zinc-500 hover:text-zinc-300"
          >
            清空
          </button>
        )}
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
                    setManualPos({});
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
                    onClick={() =>
                    openWorkflow(t.id).then((wf) => {
                      // S76：打开模板时应用持久化布局坐标
                      // S152：关键修复——载入 draft 到画布（此前漏 setDraft，画布永远空白无法编辑）
                      setDraft(wf);
                      setManualPos(wf.layout ?? {});
                      setDirty(false);
                      setRunningTask(null);
                      setSelectedNodeId(null);
                    })
                  }
                    className={`px-2 py-1.5 rounded mb-0.5 cursor-pointer text-xs ${
                      draft?.id === t.id
                        ? "bg-zinc-700/60 text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-800/60"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate">{t.name}</span>
                      <span className="text-[10px] text-zinc-600 flex items-center gap-1">
                        {t.builtin ? (
                          <span className="text-sky-500/90 border border-sky-800/50 rounded px-1 py-px" title="系统预置模板：工具收编执行路径，不可删除（可复制改造）">
                            系统
                          </span>
                        ) : null}
                        <span>模板</span>
                      </span>
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
                          if (t.builtin) {
                            setError("系统预置模板不可删除（可复制后修改自定义版本）");
                            return;
                          }
                          setPendingDeleteWf(t.id);
                        }}
                        className={`text-[10px] ${
                          t.builtin ? "text-zinc-700 cursor-not-allowed" : "text-red-500 hover:text-red-400"
                        }`}
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
                        onClick={() =>
                          promote(d.id).then(() => {
                            // S152：转正后直接载入画布（store 仅设 current，draft 需同步）
                            const cur = useWorkflowStore.getState().current;
                            if (cur) {
                              setDraft(cur);
                              setManualPos(cur.layout ?? {});
                              setDirty(false);
                              setSelectedNodeId(null);
                            }
                          })
                        }
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
              <div ref={canvasWrapRef} className="flex-1 min-h-0 overflow-hidden relative bg-zinc-950">
                <svg
                  className="w-full h-full touch-none cursor-grab active:cursor-grabbing"
                  onPointerDown={onCanvasPointerDown}
                  onPointerMove={onCanvasPointerMove}
                  onPointerUp={onCanvasPointerUp}
                  onPointerLeave={onCanvasPointerUp}
                  onWheel={onWheel}
                  onClick={onCanvasClick}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setCtxMenu({ x: e.clientX, y: e.clientY, kind: "canvas" });
                    setConnectingFrom(null);
                    setPlaceKind(null);
                  }}
                >
                  <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                    {/* S152b：loop 循环体虚拟边（虚线，纯显示；不入定义/引擎） */}
                    {loopVirtualEdges(draft).map((v, vi) => {
                      if (!nodesById[v.source] || !nodesById[v.target]) return null;
                      const from = finalPos(v.source);
                      const to = finalPos(v.target);
                      const d = edgePath(from, to, false);
                      const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
                      return (
                        <g key={`vloop-${v.loopId}-${vi}`} style={{ pointerEvents: "none" }}>
                          <path
                            d={d}
                            fill="none"
                            stroke={v.back ? "rgba(244,63,94,0.45)" : "rgba(244,63,94,0.65)"}
                            strokeWidth={1.4}
                            strokeDasharray="6 4"
                          />
                          {/* 链首标“循环体”，环回标“回环” */}
                          {(vi === 0 || v.back) && (
                            <g>
                              <rect
                                x={mid.x - 22}
                                y={mid.y - 9}
                                width={44}
                                height={14}
                                rx={4}
                                fill="#18181b"
                                stroke="rgba(244,63,94,0.5)"
                              />
                              <text x={mid.x} y={mid.y + 1} textAnchor="middle" fontSize={8} fill="#fda4af">
                                {v.back ? "回环" : "循环体"}
                              </text>
                            </g>
                          )}
                        </g>
                      );
                    })}

                    {/* S152c：START/END 虚拟节点（不入定义，仅显示流程起终点） */}
                    {(() => {
                      const { startNodeId, endNodeIds } = flowTerminalNodes(draft);
                      // 计算所有节点坐标范围（手动/布局）
                      const allNodes = draft.nodes;
                      if (allNodes.length === 0) return null;
                      const xMin = Math.min(...allNodes.map((n) => finalPos(n.id).x));
                      const xMax = Math.max(...allNodes.map((n) => finalPos(n.id).x + NODE_W));
                      const startNode = startNodeId ? nodesById[startNodeId] : null;
                      const endAnchor = endNodeIds.length ? endNodeIds[0] : null;
                      return (
                        <g style={{ pointerEvents: "none" }}>
                          {/* START → 起始节点 */}
                          {startNode && startNodeId && (
                            <>
                              <path
                                d={(() => {
                                  const sp = finalPos(startNodeId);
                                  const x1 = xMin - LAYER_GAP + 36;
                                  const y1 = sp.y + NODE_H / 2;
                                  const x2 = sp.x;
                                  const y2 = sp.y + NODE_H / 2;
                                  const mx = (x1 + x2) / 2;
                                  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
                                })()}
                                fill="none"
                                stroke="rgba(16,185,129,0.5)"
                                strokeWidth={1.3}
                                strokeDasharray="5 4"
                              />
                              <circle
                                cx={xMin - LAYER_GAP + 20}
                                cy={finalPos(startNodeId).y + NODE_H / 2}
                                r={15}
                                fill="rgba(6,78,59,0.55)"
                                stroke="#10b981"
                                strokeWidth={1.6}
                              />
                              <text
                                x={xMin - LAYER_GAP + 20}
                                y={finalPos(startNodeId).y + NODE_H / 2 + 4}
                                textAnchor="middle"
                                fontSize={9}
                                fill="#6ee7b7"
                                fontWeight={600}
                              >
                                START
                              </text>
                            </>
                          )}
                          {/* 无出边节点 → END */}
                          {endAnchor && nodesById[endAnchor] &&
                            endNodeIds.map((eid) => {
                              if (!nodesById[eid]) return null;
                              const ep = finalPos(eid);
                              return (
                                <path
                                  key={`endline-${eid}`}
                                  d={(() => {
                                    const x1 = ep.x + NODE_W;
                                    const y1 = ep.y + NODE_H / 2;
                                    const x2 = xMax + LAYER_GAP - 36;
                                    const y2 = ep.y + NODE_H / 2;
                                    const mx = (x1 + x2) / 2;
                                    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
                                  })()}
                                  fill="none"
                                  stroke="rgba(239,68,68,0.45)"
                                  strokeWidth={1.3}
                                  strokeDasharray="5 4"
                                />
                              );
                            })}
                          {endAnchor && nodesById[endAnchor] && (
                            <circle
                              cx={xMax + LAYER_GAP - 20}
                              cy={finalPos(endAnchor).y + NODE_H / 2}
                              r={15}
                              fill="rgba(127,29,29,0.55)"
                              stroke="#ef4444"
                              strokeWidth={1.6}
                            />
                          )}
                          {endAnchor && nodesById[endAnchor] && (
                            <text
                              x={xMax + LAYER_GAP - 20}
                              y={finalPos(endAnchor).y + NODE_H / 2 + 4}
                              textAnchor="middle"
                              fontSize={9}
                              fill="#fca5a5"
                              fontWeight={600}
                            >
                              END
                            </text>
                          )}
                        </g>
                      );
                    })()}

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
                      // S152e：执行路径染色——已完成路径变绿；流向当前节点的边黄流动动画
                      const srcDone = nodeStateMap[e.source]?.status === "done";
                      const tgtDone = nodeStateMap[e.target]?.status === "done";
                      const flowToCurrent = !!runningNodeId && e.target === runningNodeId;
                      const isDonePath = srcDone && tgtDone;
                      const strokeColor = sel
                        ? "#fbbf24"
                        : flowToCurrent
                          ? "#facc15"
                          : isDonePath
                            ? "rgba(16,185,129,0.65)"
                            : "rgba(113,113,122,0.55)";
                      return (
                        <g key={e.id} className="cursor-pointer">
                          <path
                            d={d}
                            fill="none"
                            stroke={strokeColor}
                            strokeWidth={sel ? 2.5 : flowToCurrent ? 2 : 1.5}
                            strokeDasharray={flowToCurrent ? "7 7" : undefined}
                            onClick={(ev) => {
                              ev.stopPropagation();
                              setSelectedEdgeId(e.id);
                              setSelectedNodeId(null);
                            }}
                            onContextMenu={(ev) => {
                              ev.preventDefault();
                              ev.stopPropagation();
                              setSelectedEdgeId(e.id);
                              setSelectedNodeId(null);
                              setCtxMenu({ x: ev.clientX, y: ev.clientY, kind: "edge", id: e.id });
                            }}
                          >
                            {/* 数据流动画：流向当前节点的边虚线流动 */}
                            {flowToCurrent && (
                              <animate
                                attributeName="stroke-dashoffset"
                                from="14"
                                to="0"
                                dur="0.7s"
                                repeatCount="indefinite"
                              />
                            )}
                          </path>
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
                          onContextMenu={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setSelectedNodeId(n.id);
                            setSelectedEdgeId(null);
                            setCtxMenu({ x: e.clientX, y: e.clientY, kind: "node", id: n.id });
                          }}
                        >
                          {/* 连线出口（右侧手柄）：S152c 两段式——点一下开始，再点目标节点完成 */}
                          <circle
                            cx={NODE_W + 6}
                            cy={NODE_H / 2}
                            r={7}
                            fill="#3f3f46"
                            stroke={connectingFrom === n.id ? "#fbbf24" : "#71717a"}
                            strokeWidth={connectingFrom === n.id ? 2 : 1.5}
                            onClick={(e) => {
                              e.stopPropagation();
                              if (connectingFrom === n.id) {
                                setConnectingFrom(null);
                              } else {
                                setConnectingFrom(n.id);
                                setSelectedNodeId(n.id);
                                setSelectedEdgeId(null);
                              }
                            }}
                            aria-label="连线出口（点一下开始连线）"
                          />
                          <title>连线出口：点一下开始连线，再点目标节点完成（gate 可重复多分支）</title>
                          {/* S152c：左侧入点端口（视觉对称；连线目标=节点本身，点击节点即连入） */}
                          <circle
                            cx={-6}
                            cy={NODE_H / 2}
                            r={4.5}
                            fill="#27272a"
                            stroke="#52525b"
                            strokeWidth={1.2}
                            style={{ pointerEvents: "none" }}
                            aria-label="连线入口"
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
                          {/* S152e：运行状态徽标（✓完成 / ✗失败 / 旋转指示 running） */}
                          {st?.status === "done" && (
                            <g transform={`translate(${NODE_W + 6}, ${NODE_H / 2 - 16})`} style={{ pointerEvents: "none" }}>
                              <circle r={8} fill="rgba(16,185,129,0.2)" stroke="#10b981" strokeWidth={1.5} />
                              <path d="M -3.5 0.5 L -1 3 L 3.5 -3" fill="none" stroke="#34d399" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
                            </g>
                          )}
                          {st?.status === "failed" && (
                            <g transform={`translate(${NODE_W + 6}, ${NODE_H / 2 - 16})`} style={{ pointerEvents: "none" }}>
                              <circle r={8} fill="rgba(239,68,68,0.2)" stroke="#ef4444" strokeWidth={1.5} />
                              <path d="M -3 -3 L 3 3 M 3 -3 L -3 3" stroke="#f87171" strokeWidth={1.8} strokeLinecap="round" />
                            </g>
                          )}
                          {st?.status === "running" && (
                            <>
                              {/* 脉冲扩散光圈 */}
                              <circle cx={NODE_W / 2} cy={NODE_H / 2} r={NODE_H / 2} fill="none" stroke="#facc15" strokeWidth={2} style={{ pointerEvents: "none" }}>
                                <animate attributeName="r" values={`${NODE_H / 2};${NODE_H / 2 + 14}`} dur="1s" repeatCount="indefinite" />
                                <animate attributeName="opacity" values="0.9;0" dur="1s" repeatCount="indefinite" />
                              </circle>
                              {/* 旋转指示 */}
                              <g transform={`translate(${NODE_W / 2}, ${NODE_H / 2})`} style={{ pointerEvents: "none" }}>
                                <circle r={7} fill="none" stroke="#facc15" strokeWidth={2} strokeDasharray="10 22" strokeLinecap="round">
                                  <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="0.9s" repeatCount="indefinite" />
                                </circle>
                              </g>
                            </>
                          )}
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

                {/* S152d：缩放控件（右上角浮动） */}
                <div className="absolute top-2 right-2 flex flex-col gap-1 select-none">
                  <button
                    onClick={() => setZoom((z) => Math.min(2, z * 1.2))}
                    className="w-7 h-7 rounded bg-zinc-900/90 border border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-sm leading-none"
                    title="放大"
                  >
                    +
                  </button>
                  <button
                    onClick={() => setZoom((z) => Math.max(0.3, z / 1.2))}
                    className="w-7 h-7 rounded bg-zinc-900/90 border border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-sm leading-none"
                    title="缩小"
                  >
                    −
                  </button>
                  <button
                    onClick={fitView}
                    className="w-7 h-7 rounded bg-zinc-900/90 border border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-xs leading-none"
                    title="适配视图（全部节点可见）"
                  >
                    ⛶
                  </button>
                  <button
                    onClick={() => setShowExecLog(!showExecLog)}
                    className={`w-7 h-7 rounded bg-zinc-900/90 border text-xs leading-none ${showExecLog ? "border-zinc-600 text-zinc-200" : "border-zinc-700 text-zinc-500 hover:bg-zinc-800"}`}
                    title={showExecLog ? "隐藏执行明细" : "显示执行明细"}
                  >
                    ☰
                  </button>
                </div>

                {/* S152e：执行明细浮层（右下角，任务运行时/结束后可看） */}
                {showExecLog && runningTask && (
                  <ExecLogPanel
                    runningTask={runningTask}
                    nodesById={nodesById}
                    onLocate={(nodeId) => {
                      setSelectedNodeId(nodeId);
                      setSelectedEdgeId(null);
                    }}
                    onClose={() => setShowExecLog(false)}
                  />
                )}

                {/* S152d：迷你地图（右下角） */}
                {showMiniMap && draft.nodes.length > 0 && (
                  <MiniMapOverlay
                    draft={draft}
                    finalPos={finalPos}
                    zoom={zoom}
                    pan={pan}
                    viewportW={canvasWrapRef.current?.clientWidth ?? 800}
                    viewportH={canvasWrapRef.current?.clientHeight ?? 600}
                    onNavigate={(nx, ny) => setPan({ x: nx, y: ny })}
                  />
                )}

                {/* S152d：右键菜单浮层 */}
                {ctxMenu && (
                  <div
                    data-wf-context-menu
                    className="fixed z-50 min-w-[140px] py-1 rounded-lg bg-zinc-800/95 border border-zinc-700 shadow-xl text-xs"
                    style={{ left: ctxMenu.x, top: ctxMenu.y }}
                    onContextMenu={(e) => e.preventDefault()}
                  >
                    {ctxMenu.kind === "node" && (
                      <>
                        <button
                          onClick={() => handleCtxAction("duplicate")}
                          className="w-full text-left px-3 py-1.5 text-zinc-300 hover:bg-zinc-700"
                        >
                          复制节点
                        </button>
                        <button
                          onClick={() => handleCtxAction("delete")}
                          className="w-full text-left px-3 py-1.5 text-red-400 hover:bg-zinc-700"
                        >
                          删除节点（含边）
                        </button>
                      </>
                    )}
                    {ctxMenu.kind === "edge" && (
                      <button
                        onClick={() => handleCtxAction("delete")}
                        className="w-full text-left px-3 py-1.5 text-red-400 hover:bg-zinc-700"
                      >
                        删除连线
                      </button>
                    )}
                    {ctxMenu.kind === "canvas" && (
                      <>
                        <button
                          onClick={fitView}
                          className="w-full text-left px-3 py-1.5 text-zinc-300 hover:bg-zinc-700"
                        >
                          适配视图
                        </button>
                        <button
                          onClick={() => setCtxMenu(null)}
                          className="w-full text-left px-3 py-1.5 text-zinc-500 hover:bg-zinc-700"
                        >
                          取消选择
                        </button>
                      </>
                    )}
                  </div>
                )}
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

      {/* 删除工作流模板确认 */}
      <ConfirmModal
        open={!!pendingDeleteWf}
        title="删除工作流模板"
        message="确定删除此模板？此操作不可恢复。"
        confirmText="删除"
        danger
        onConfirm={() => {
          if (pendingDeleteWf) removeWorkflow(pendingDeleteWf);
          setPendingDeleteWf(null);
        }}
        onCancel={() => setPendingDeleteWf(null)}
      />
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

      {node.kind === "agent" ? (
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
      ) : node.kind === "script" ? (
        <>
          <div>
            <label className="block text-[10px] text-zinc-500 mb-0.5">函数 function</label>
            <select
              value={(node.params.function as string) ?? ""}
              onChange={(e) => setParam("function", e.target.value)}
              className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
              style={{ width: 220 }}
            >
              <option value="">（选择函数）</option>
              {SCRIPT_FN_NAMES.map((fn) => (
                <option key={fn} value={fn}>
                  {SCRIPT_FUNCTIONS[fn].label}
                </option>
              ))}
            </select>
          </div>
          {SCRIPT_FUNCTIONS[(node.params.function as string) ?? ""]?.params.map((p) => (
            <div key={p.key}>
              <label className="block text-[10px] text-zinc-500 mb-0.5">{p.label}</label>
              <input
                type={p.type === "number" ? "number" : "text"}
                value={(node.params[p.key] as string | number | undefined) ?? ""}
                onChange={(e) =>
                  setParam(p.key, p.type === "number" ? Number(e.target.value) : e.target.value)
                }
                placeholder={p.placeholder}
                className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 outline-none focus:border-zinc-500"
                style={{ width: 140 }}
              />
            </div>
          ))}
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

/* ── S152e：执行明细浮层（节点状态时间线） ── */
const EXEC_STATUS_TEXT: Record<string, string> = {
  done: "完成",
  failed: "失败",
  running: "执行中",
  skipped: "跳过",
  pending: "等待",
  queued: "排队",
};
const EXEC_STATUS_COLOR: Record<string, string> = {
  done: "#10b981",
  failed: "#ef4444",
  running: "#facc15",
  skipped: "#71717a",
  pending: "#3f3f46",
  queued: "#3f3f46",
};

function ExecLogPanel({
  runningTask,
  nodesById,
  onLocate,
  onClose,
}: {
  runningTask: WorkflowTask;
  nodesById: Record<string, WorkflowNode>;
  onLocate: (nodeId: string) => void;
  onClose: () => void;
}) {
  const states = [...(runningTask.node_states ?? [])].reverse(); // 最新在前
  const statusText = runningTask.status;
  return (
    <div className="absolute bottom-2 left-2 w-72 max-h-64 flex flex-col bg-zinc-900/95 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-zinc-800 bg-zinc-900">
        <span className="text-[10px] text-zinc-400 font-medium">
          执行明细 · {statusText === "done" ? "✓ 完成" : statusText === "failed" ? "✗ 失败" : statusText === "waiting_approval" ? "⏸ 等待确认" : `● ${statusText}`}
        </span>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-xs leading-none">×</button>
      </div>
      <div className="flex-1 overflow-auto p-1">
        {states.length === 0 && <p className="text-[11px] text-zinc-600 px-2 py-2">暂无节点明细（任务初始化中）</p>}
        {states.map((s) => {
          const n = nodesById[s.node_id];
          const color = EXEC_STATUS_COLOR[s.status] ?? "#3f3f46";
          const text = EXEC_STATUS_TEXT[s.status] ?? s.status;
          const summary = (s.output ?? s.error ?? "")
            .replace(/\n+/g, " ")
            .slice(0, 48);
          return (
            <button
              key={s.node_id}
              onClick={() => onLocate(s.node_id)}
              className={`w-full text-left px-2 py-1 rounded hover:bg-zinc-800 transition-colors ${s.status === "running" ? "bg-zinc-800/60" : ""}`}
              title={summary || n?.label || s.node_id}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span className="text-[11px] text-zinc-300 truncate flex-1">
                  {n?.label ?? s.node_id}
                </span>
                <span className="text-[10px] text-zinc-500 shrink-0" style={{ color }}>
                  {text}
                </span>
              </div>
              {summary && (
                <p className="text-[10px] text-zinc-600 truncate pl-3">{summary}</p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── S152d：迷你地图（画布导航） ── */
function MiniMapOverlay({
  draft,
  finalPos,
  zoom,
  pan,
  viewportW,
  viewportH,
  onNavigate,
}: {
  draft: WorkflowDef;
  finalPos: (id: string) => Pos;
  zoom: number;
  pan: Pos;
  viewportW: number;
  viewportH: number;
  onNavigate: (x: number, y: number) => void;
}) {
  const MAP_W = 176;
  const MAP_H = 116;
  const PAD = 8;
  const dragRef = useRef<{ startClientX: number; startClientY: number; startPanX: number; startPanY: number } | null>(null);

  // 内容包围盒（真实节点）
  const xs = draft.nodes.map((n) => finalPos(n.id).x);
  const x2s = draft.nodes.map((n) => finalPos(n.id).x + NODE_W);
  const ys = draft.nodes.map((n) => finalPos(n.id).y);
  const y2s = draft.nodes.map((n) => finalPos(n.id).y + NODE_H);
  const x0 = Math.min(...xs, ...x2s) - PAD;
  const x1 = Math.max(...xs, ...x2s) + PAD;
  const y0 = Math.min(...ys, ...y2s) - PAD;
  const y1 = Math.max(...ys, ...y2s) + PAD;
  const cw = Math.max(x1 - x0, 1);
  const ch = Math.max(y1 - y0, 1);
  const scale = Math.min((MAP_W - 4) / cw, (MAP_H - 4) / ch);
  const offX = 2 + (MAP_W - cw * scale) / 2 - x0 * scale;
  const offY = 2 + (MAP_H - ch * scale) / 2 - y0 * scale;
  const toX = (x: number) => x * scale + offX;
  const toY = (y: number) => y * scale + offY;

  // 视口矩形（当前 pan/zoom 可视范围）
  const vx0 = pan.x;
  const vy0 = pan.y;
  const vx1 = pan.x + viewportW / zoom;
  const vy1 = pan.y + viewportH / zoom;
  const rx = toX(vx0);
  const ry = toY(vy0);
  const rw = (vx1 - vx0) * scale;
  const rh = (vy1 - vy0) * scale;

  // 点击/拖动小地图 → 平移主画布（视口中心对齐指针）
  const jumpTo = (e: React.PointerEvent) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const wx = (mx - offX) / scale;
    const wy = (my - offY) / scale;
    onNavigate(wx - viewportW / zoom / 2, wy - viewportH / zoom / 2);
  };
  const onPointerDown = (e: React.PointerEvent) => {
    e.stopPropagation();
    dragRef.current = { startClientX: e.clientX, startClientY: e.clientY, startPanX: pan.x, startPanY: pan.y };
    jumpTo(e);
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    // 小地图像素位移 → 世界坐标位移（÷ scale）；视口跟随鼠标同向移动
    const dx = (e.clientX - d.startClientX) / scale;
    const dy = (e.clientY - d.startClientY) / scale;
    onNavigate(d.startPanX + dx, d.startPanY + dy);
  };
  const onPointerUp = () => {
    dragRef.current = null;
  };

  return (
    <div className="absolute bottom-2 right-2 bg-zinc-900/90 border border-zinc-700 rounded-lg p-1 select-none shadow-lg">
      <svg
        width={MAP_W}
        height={MAP_H}
        className="touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        style={{ cursor: "crosshair" }}
      >
        {/* 边 */}
        {draft.edges.map((e) => {
          const a = finalPos(e.source);
          const b = finalPos(e.target);
          return (
            <line
              key={e.id}
              x1={toX(a.x + NODE_W / 2)}
              y1={toY(a.y + NODE_H / 2)}
              x2={toX(b.x + NODE_W / 2)}
              y2={toY(b.y + NODE_H / 2)}
              stroke="rgba(113,113,122,0.5)"
              strokeWidth={0.8}
            />
          );
        })}
        {/* 节点 */}
        {draft.nodes.map((n) => (
          <rect
            key={n.id}
            x={toX(finalPos(n.id).x)}
            y={toY(finalPos(n.id).y)}
            width={Math.max(2, NODE_W * scale)}
            height={Math.max(2, NODE_H * scale)}
            rx={1.5}
            fill={KIND_META[n.kind].stroke}
            opacity={0.8}
          />
        ))}
        {/* 视口矩形 */}
        <rect
          x={rx}
          y={ry}
          width={rw}
          height={rh}
          fill="rgba(251,191,36,0.08)"
          stroke="#fbbf24"
          strokeWidth={1}
          pointerEvents="none"
        />
      </svg>
      <div className="text-[9px] text-zinc-600 text-center">迷你地图（点/拖跳转）</div>
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
