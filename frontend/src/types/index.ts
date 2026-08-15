// 章节类型（对应后端 ChapterOut）
export interface Chapter {
  id: string;
  book_id: string;
  title: string;
  content: string;
  order_index: number;
  updated_at: string;
}

// 聊天消息角色
export type MessageRole = "user" | "assistant" | "system" | "tool";

// 聊天消息
export interface ChatMessage {
  role: MessageRole;
  content: string;
}

// SSE 事件
export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}
