import { useRef } from "react";
import type { WorkflowDef } from "../../api/workflow";
import { KIND_META, NODE_W, NODE_H } from "./constants";
import type { Pos } from "./constants";

/* ── S152d：迷你地图（画布导航） ── */
export default function MiniMapOverlay({
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
