import { apiFetch } from "./client";

// 候选卡
export interface Candidate {
  id: string;
  style: string;
  text: string;
}

// 获取候选卡
export function getCandidates(prompt: string, n = 3): Promise<{ candidates: Candidate[] }> {
  return apiFetch<{ candidates: Candidate[] }>("/api/chat/candidates", {
    method: "POST",
    body: JSON.stringify({ prompt, n }),
  });
}

// ── S99 会话消息队列（排队接力第一步：排队/查看/删/转插入） ──
export interface QueueItem {
  id: string
  text: string
}

export interface QueueStatus {
  queues: Record<string, QueueItem[]>
  running: string[]
}

// 查看所有会话的排队消息 + 运行中会话
export function fetchQueues(): Promise<QueueStatus> {
  return apiFetch<QueueStatus>("/api/chat/queues")
}

// 消息入队（接力执行：当前会话完成后自动消费——第二步 SSE 循环化）
export function enqueueChat(conversationId: string, message: string): Promise<{ ok: boolean; queue: QueueItem[] }> {
  return apiFetch("/api/chat/queue", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  })
}

// 删除一条排队消息
export function dequeueChat(conversationId: string, queueItemId: string): Promise<{ ok: boolean; queue: QueueItem[] }> {
  return apiFetch(`/api/chat/queue/${conversationId}/${queueItemId}`, {
    method: "DELETE",
  })
}

// 排队消息转插入（steer 成功才移除；会话未运行则保留并提示）
export function steerQueuedChat(
  conversationId: string,
  queueItemId: string
): Promise<{ ok: boolean; queue?: QueueItem[]; reason?: string }> {
  return apiFetch(`/api/chat/queue/${conversationId}/${queueItemId}/steer`, {
    method: "POST",
  })
}

export function steerChat(conversationId: string, message: string): Promise<void> {
  return apiFetch<void>("/api/chat/steer", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}

// 中止运行中的会话生成（S41 配套：前端停止按钮走后端，感知会话态）
export function cancelChat(conversationId?: string): Promise<void> {
  return apiFetch<void>("/api/chat/cancel", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId || null }),
  });
}

// 方向声明：AI 先声明要写什么，不写正文（摩擦前置，用户确认）
export function getDirection(
  prompt: string,
  context = ""
): Promise<{ direction: string }> {
  return apiFetch<{ direction: string }>("/api/chat/direction", {
    method: "POST",
    body: JSON.stringify({ prompt, context }),
  });
}

// 改写渐变条：保原味↔大幅改（subtle|balanced|bold）
export function rewriteText(
  text: string,
  mode: "subtle" | "balanced" | "bold" = "balanced"
): Promise<{ rewritten: string; mode: string }> {
  return apiFetch<{ rewritten: string; mode: string }>("/api/chat/rewrite", {
    method: "POST",
    body: JSON.stringify({ text, mode }),
  });
}
