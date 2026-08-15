// S152b：工作流画布布局/虚拟边纯函数（可测试）
import type { WorkflowDef } from "../api/workflow";

// loop 循环体虚拟边（画布显示用，不入模板定义/引擎）——
// 引擎按 loop.params.body 顺序执行循环体，body 节点间本无边；
// 画布上补虚线链（loop→body[0]→…→body[last]→loop）让人看懂"这是一个循环"。
// back=true 表示环回边（仅显示，不参与分层）。
export interface VirtualEdge {
  source: string;
  target: string;
  loopId: string;
  back: boolean;
}

export function loopVirtualEdges(draft: WorkflowDef | null): VirtualEdge[] {
  const out: VirtualEdge[] = [];
  if (!draft) return out;
  for (const n of draft.nodes) {
    if (n.kind !== "loop") continue;
    const body = (n.params.body as string[] | undefined) ?? [];
    if (body.length === 0) continue;
    out.push({ source: n.id, target: body[0], loopId: n.id, back: false });
    for (let i = 0; i < body.length - 1; i++) {
      out.push({ source: body[i], target: body[i + 1], loopId: n.id, back: false });
    }
    out.push({ source: body[body.length - 1], target: n.id, loopId: n.id, back: true });
  }
  return out;
}

// 分层边 = 真实边 + 虚拟链（不含环回，避免把 loop 自身推到最深）
export function layoutEdges(draft: WorkflowDef | null): Array<{ source: string; target: string }> {
  if (!draft) return [];
  return [
    ...draft.edges.map((e) => ({ source: e.source, target: e.target })),
    ...loopVirtualEdges(draft)
      .filter((v) => !v.back)
      .map((v) => ({ source: v.source, target: v.target })),
  ];
}

// S152c：画布网格对齐（拖拽/放置 snap 到 10px）
export const SNAP_GRID = 10;
export const snapGrid = (v: number): number => Math.round(v / SNAP_GRID) * SNAP_GRID;

// S152c：连线防环即时校验（与后端 validate 的有向环检测对齐：
// loop 节点豁免——进入 loop 不再探查，loop 语义允许环回边由 max_iterations 收敛）。
// 若在现有图上加 source→target 会使 target 能到达 source，则成环。
export function wouldCreateCycle(
  source: string,
  target: string,
  edges: Array<{ source: string; target: string }>,
  loopIds?: Set<string>
): boolean {
  if (source === target) return false;
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    if (e.source === source && e.target === target) continue; // 待加边不计入
    if (!adj.has(e.source)) adj.set(e.source, []);
    adj.get(e.source)!.push(e.target);
  }
  // 从 target 出发 BFS：能回到 source 即成环；进入 loop 节点不继续探查
  const queue = [target];
  const seen = new Set<string>([target]);
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === source) return true;
    if (loopIds?.has(cur)) continue; // 后端同款豁免
    for (const nx of adj.get(cur) ?? []) {
      if (!seen.has(nx)) {
        seen.add(nx);
        queue.push(nx);
      }
    }
  }
  return false;
}

// S152c：画布 START/END 虚拟节点定位（不入模板定义，仅显示）
export function flowTerminalNodes(
  draft: WorkflowDef | null
): { startNodeId: string | null; endNodeIds: string[] } {
  if (!draft || draft.nodes.length === 0) {
    return { startNodeId: null, endNodeIds: [] };
  }
  const targets = new Set(draft.edges.map((e) => e.target));
  const sources = new Set(draft.edges.map((e) => e.source));
  const startNodeId =
    draft.nodes.find((n) => !targets.has(n.id))?.id ?? draft.nodes[0].id;
  const endNodeIds = draft.nodes.filter((n) => !sources.has(n.id)).map((n) => n.id);
  return { startNodeId, endNodeIds };
}
