// workflowLayout 纯函数测试（S152b：loop 循环体虚拟边——画布可视化）
import { describe, it, expect } from "vitest";
import { loopVirtualEdges, layoutEdges, wouldCreateCycle, flowTerminalNodes } from "../workflowLayout";
import type { WorkflowDef } from "../../api/workflow";

// 模拟「章节加料」模板结构（真实 seed 模板：8 节点 2 边，loop body 5 节点无边）
function enrichTemplate(): WorkflowDef {
  return {
    id: "wf-test",
    name: "章节加料",
    description: "",
    nodes: [
      { id: "prep", kind: "script", label: "收集章节", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "gate_confirm", kind: "approval", label: "确认加料", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "loop", kind: "loop", label: "逐章加料", params: { body: ["read", "title", "enrich", "stitch", "save"] }, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "read", kind: "script", label: "读原文", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "title", kind: "script", label: "取标题", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "enrich", kind: "agent", label: "生成插入内容", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "stitch", kind: "script", label: "合并原文", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
      { id: "save", kind: "script", label: "写回章节", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } },
    ],
    edges: [
      { id: "e1", source: "prep", target: "gate_confirm" },
      { id: "e2", source: "gate_confirm", target: "loop" },
    ],
  };
}

describe("loopVirtualEdges（loop body 虚拟边）", () => {
  it("真实边之外生成 body 链 + 环回边（加料模板 5 节点 body）", () => {
    const v = loopVirtualEdges(enrichTemplate());
    // loop→read, read→title, title→enrich, enrich→stitch, stitch→save, save→loop
    expect(v).toHaveLength(6);
    expect(v[0]).toMatchObject({ source: "loop", target: "read", back: false });
    expect(v[1]).toMatchObject({ source: "read", target: "title", back: false });
    expect(v[4]).toMatchObject({ source: "stitch", target: "save", back: false });
    expect(v[5]).toMatchObject({ source: "save", target: "loop", back: true }); // 环回
  });

  it("body 为空 / 无 loop 节点 → 无虚拟边", () => {
    const noLoop: WorkflowDef = {
      id: "x",
      name: "无loop",
      description: "",
      nodes: [{ id: "a", kind: "script", label: "A", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } }],
      edges: [],
    };
    expect(loopVirtualEdges(noLoop)).toEqual([]);
    const emptyBody: WorkflowDef = {
      ...noLoop,
      nodes: [{ id: "lp", kind: "loop", label: "L", params: {}, fail: { auto_retry_count: 0, auto_retry_interval_seconds: 0, fail_auto_skip: false } }],
    };
    expect(loopVirtualEdges(emptyBody)).toEqual([]);
  });
});

describe("layoutEdges（分层边 = 真实 + 虚拟，环回剔除）", () => {
  it("环回边不参与分层（避免 loop 被推深）", () => {
    const edges = layoutEdges(enrichTemplate());
    const srcs = edges.map((e) => `${e.source}→${e.target}`);
    // 含真实边 + 5 条虚拟链
    expect(srcs).toContain("prep→gate_confirm");
    expect(srcs).toContain("loop→read");
    expect(srcs).toContain("stitch→save");
    // 环回 save→loop 不在分层边里
    expect(srcs).not.toContain("save→loop");
  });
});

describe("wouldCreateCycle（连线防环即时校验）", () => {
  const edges = [
    { source: "a", target: "b" },
    { source: "b", target: "c" },
  ];

  it("正常加边不成环", () => {
    expect(wouldCreateCycle("c", "d", edges)).toBe(false);
    expect(wouldCreateCycle("a", "d", edges)).toBe(false);
  });

  it("回边成环 → true（c→a）", () => {
    expect(wouldCreateCycle("c", "a", edges)).toBe(true);
  });

  it("loop 豁免：路径经过 loop 节点不回查", () => {
    // b→loop→d；在 d→b 加边：若 loop 豁免则不成环
    const loopEdges = [
      { source: "a", target: "b" },
      { source: "b", target: "loop" },
      { source: "loop", target: "d" },
    ];
    expect(wouldCreateCycle("d", "b", loopEdges, new Set(["loop"]))).toBe(false);
    // 无豁免 → 成环
    expect(wouldCreateCycle("d", "b", loopEdges)).toBe(true);
  });
});

describe("flowTerminalNodes（START/END 定位）", () => {
  it("无入边节点 = 起点；无出边节点 = 终点", () => {
    const { startNodeId, endNodeIds } = flowTerminalNodes(enrichTemplate());
    expect(startNodeId).toBe("prep");
    expect(endNodeIds).toContain("save");
  });

  it("空定义 → 无起终点", () => {
    expect(flowTerminalNodes(null)).toEqual({ startNodeId: null, endNodeIds: [] });
  });
});
