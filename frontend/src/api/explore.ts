import { apiGet, apiPost } from "./client";

// 方向卡
export interface DirectionCard {
  id: string;
  title: string;
  summary: string;
  dimension: string;
  source: "template" | "grow" | "user";
  term: string;
}

// 种子概念（后端返回）
export interface SeedConcept {
  core: string;
  mood: string;
  genre: string;
  seed_position: string;
}

// 意图理解结果
export interface IntentResult {
  concept: SeedConcept;
  questions: string[];
}

// 已固化的方向
export interface ArchivedDirection {
  id: string;
  book_id: string;
  title: string;
  summary: string;
  dimension: string;
  source: string;
  term: string;
  created_at: string;
  story_node_id?: string;
}

// 意图理解（种子 → 概念卡 + 歧义点）
export function exploreIntent(seed: string): Promise<IntentResult> {
  return apiPost<IntentResult>("/api/explore/intent", { seed });
}

// 生成方向卡（确认后 → 4 张候选）
export function exploreCards(
  seed: string,
  intentConfirmed: object
): Promise<DirectionCard[]> {
  return apiPost<DirectionCard[]>("/api/explore/cards", {
    seed,
    intent_confirmed: intentConfirmed,
  });
}

// 固化方向到档案 + 叙事树（S152：bookId 项目隔离）
export function archiveDirection(
  card: DirectionCard,
  bookId = "main",
  parentNodeId?: string
): Promise<ArchivedDirection & { story_node_id: string }> {
  return apiPost<ArchivedDirection & { story_node_id: string }>("/api/explore/archive", {
    card: {
      title: card.title,
      summary: card.summary,
      dimension: card.dimension,
      source: card.source,
      term: card.term,
    },
    book_id: bookId,
    parent_node_id: parentNodeId ?? null,
  });
}

// 获取已固化方向列表（S152：按项目隔离）
export function listArchived(bookId = "main"): Promise<ArchivedDirection[]> {
  return apiGet<ArchivedDirection[]>(`/api/explore/archive?book_id=${bookId}`);
}

// S67 路径探索：起点 A → 终点 B 的 N 条串联路径候选（叙事树节点之间）
export interface PathCandidate {
  events: string[];
  [k: string]: unknown;
}

export interface PathResult {
  paths: PathCandidate[];
  archived: { node_ids: string[]; path: PathCandidate } | null;
}

export function explorePath(params: {
  from_desc?: string;
  to_desc: string;
  from_node_id?: string;
  to_node_id?: string;
  constraints?: string[];
  n?: number;
  archive_index?: number;
  book_id?: string; // S152：项目隔离（落树按当前项目）
}): Promise<PathResult> {
  return apiPost<PathResult>("/api/explore/path", {
    from_desc: params.from_desc ?? "",
    to_desc: params.to_desc,
    from_node_id: params.from_node_id ?? null,
    to_node_id: params.to_node_id ?? null,
    constraints: params.constraints ?? [],
    n: params.n ?? 4,
    archive_index: params.archive_index ?? null,
    book_id: params.book_id ?? "main",
  });
}
