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
