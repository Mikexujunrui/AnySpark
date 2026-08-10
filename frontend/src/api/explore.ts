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

// 意图理解结果
export interface IntentResult {
  concepts: string[];
  ambiguities: string[];
  seed_analysis?: string;
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
  intentConfirmed: Record<string, unknown>
): Promise<DirectionCard[]> {
  return apiPost<DirectionCard[]>("/api/explore/cards", {
    seed,
    intent_confirmed: intentConfirmed,
  });
}

// 固化方向到档案 + 叙事树
export function archiveDirection(
  card: DirectionCard,
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
    parent_node_id: parentNodeId ?? null,
  });
}

// 获取已固化方向列表
export function listArchived(): Promise<ArchivedDirection[]> {
  return apiGet<ArchivedDirection[]>("/api/explore/archive");
}
