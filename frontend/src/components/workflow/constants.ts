import type { WorkflowNodeKind } from "../../api/workflow";

/* ── 节点样式 ── */
export const KIND_META: Record<
  WorkflowNodeKind,
  { stroke: string; fill: string; text: string; shape: "rect" | "diamond" | "hex" }
> = {
  agent: { stroke: "#3b82f6", fill: "rgba(30,64,175,0.3)", text: "#93c5fd", shape: "rect" },
  script: { stroke: "#06b6d4", fill: "rgba(8,145,178,0.3)", text: "#67e8f9", shape: "rect" },
  approval: { stroke: "#a855f7", fill: "rgba(88,28,135,0.35)", text: "#d8b4fe", shape: "diamond" },
  gate: { stroke: "#f59e0b", fill: "rgba(146,64,14,0.3)", text: "#fcd34d", shape: "diamond" },
  loop: { stroke: "#f43f5e", fill: "rgba(136,19,55,0.35)", text: "#fda4af", shape: "rect" },
};
export const KIND_LABEL: Record<WorkflowNodeKind, string> = {
  agent: "AI 节点",
  script: "脚本",
  approval: "审批",
  gate: "条件",
  loop: "循环",
};

/* ── script 函数目录（画布选择器） ── */
export const SCRIPT_FUNCTIONS: Record<string, { label: string; params: { key: string; label: string; placeholder?: string; type?: "number" }[] }> = {
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
export const SCRIPT_FN_NAMES = Object.keys(SCRIPT_FUNCTIONS);
export const NODE_W = 148;
export const NODE_H = 56;
export const LAYER_GAP = 230;
export const ROW_GAP = 96;

export interface Pos {
  x: number;
  y: number;
}

export interface NodeState {
  task_id: string;
  node_id: string;
  status: string;
  output?: string;
  error?: string;
}
