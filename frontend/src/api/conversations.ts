import { apiFetch } from "./client";

export interface Conversation {
  id: string;
  created_at: string;
  parent_id: string | null;
  fork_point: string;
  message_count: number;
  title: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  metadata?: Record<string, unknown>;
}

export function listConversations(): Promise<Conversation[]> {
  return apiFetch<Conversation[]>("/api/conversations");
}

export function getConversationMessages(convId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`/api/conversations/${convId}/messages`);
}

export function renameConversation(convId: string, title: string): Promise<void> {
  return apiFetch<void>(`/api/conversations/${convId}`, {
    method: "PUT",
    body: JSON.stringify({ title }),
  });
}

export function deleteConversation(convId: string): Promise<void> {
  return apiFetch<void>(`/api/conversations/${convId}`, { method: "DELETE" });
}

// S161：会话继承派生（fork）——从源会话创建继承它的新会话（复制消息 + 链条可追溯）
export function forkConversation(
  convId: string,
  forkPoint = "从会话末尾继承"
): Promise<{ conversation_id: string; parent_id: string | null; fork_point: string; chain: string[] }> {
  return apiFetch(`/api/conversations/${convId}/fork?fork_point=${encodeURIComponent(forkPoint)}`, {
    method: "POST",
  });
}
