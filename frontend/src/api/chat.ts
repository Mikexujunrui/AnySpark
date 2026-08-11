import type { SSEEvent } from "../types";
import { apiFetch } from "./client";

// SSE 事件回调
export type SSECallback = (event: SSEEvent) => void;

// 流式对话请求参数
export interface StreamChatParams {
  message: string;
  conversation_id?: string;
  temperature?: number;
}

// 流式对话
export function streamChat(
  params: StreamChatParams,
  onEvent: SSECallback
): { abort: () => void } {
  const controller = new AbortController();

  // 发起请求
  fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: params.message,
      conversation_id: params.conversation_id,
      temperature: params.temperature ?? 0.7,
    }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        onEvent({
          type: "error",
          data: { message: text || response.statusText },
        });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onEvent({ type: "error", data: { message: "No response body" } });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 按 \n\n 分割 SSE 帧
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || ""; // 最后一帧可能不完整，保留

        for (const frame of frames) {
          if (!frame.trim()) continue;

          let eventType = "message";
          let eventData = "";

          // 解析帧
          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.slice(6);
            }
          }

          // 解析 JSON
          try {
            const data = eventData ? JSON.parse(eventData) : {};
            onEvent({ type: eventType, data });
          } catch {
            // 忽略解析错误
          }
        }
      }

      onEvent({ type: "done", data: {} });
    })
    .catch((error) => {
      if (error.name !== "AbortError") {
        onEvent({ type: "error", data: { message: error.message } });
      }
    });

  return {
    abort: () => controller.abort(),
  };
}

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

// 运行中插话
export function steerChat(conversationId: string, message: string): Promise<void> {
  return apiFetch<void>("/api/chat/steer", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}
