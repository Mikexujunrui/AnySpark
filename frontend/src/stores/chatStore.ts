import { create } from "zustand";
import { streamChat, getCandidates, steerChat, type Candidate } from "../api/chat";
import {
  listConversations,
  getConversationMessages,
  renameConversation as apiRenameConversation,
  deleteConversation as apiDeleteConversation,
  type Conversation,
} from "../api/conversations";
import type { ChatMessage, SSEEvent } from "../types";
import { useChapterStore } from "./chapterStore";

// 扩展消息类型，支持候选卡
export interface ExtendedMessage extends ChatMessage {
  candidates?: Candidate[];
  loadingCandidates?: boolean;
}

interface ChatState {
  messages: ExtendedMessage[];
  streaming: boolean;
  streamingText: string;
  conversationId: string | null;
  abortController: (() => void) | null;
  conversations: Conversation[];

  sendMessage: (text: string) => void;
  sendSteer: (text: string) => void;
  requestCandidates: (prompt: string) => void;
  selectCandidate: (candidate: Candidate) => void;
  cancelStream: () => void;
  clearMessages: () => void;
  loadConversation: (convId: string) => Promise<void>;
  loadLatestConversation: () => Promise<void>;
  setConversations: (convs: Conversation[]) => void;
  switchConversation: (convId: string) => void;
  startNewConversation: () => void;
  refreshConversations: () => Promise<void>;
  renameConversation: (convId: string, title: string) => Promise<void>;
  deleteConversation: (convId: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streaming: false,
  streamingText: "",
  conversationId: null,
  abortController: null,
  conversations: [],

  sendMessage: (text: string) => {
    const { streaming, conversationId } = get();
    if (streaming) return;

    // 添加用户消息
    set((state) => ({
      messages: [...state.messages, { role: "user", content: text }],
      streaming: true,
      streamingText: "",
    }));

    // 发起流式请求
    const { abort } = streamChat(
      {
        message: text,
        conversation_id: conversationId || undefined,
      },
      (event: SSEEvent) => {
        handleSSEEvent(event, get, set);
      }
    );

    set({ abortController: () => abort() });
  },

  sendSteer: (text: string) => {
    const { conversationId, streaming, abortController } = get();
    if (!conversationId || !streaming) return;

    // 1. 先中断当前流式输出
    if (abortController) {
      abortController();
    }

    // 2. 保存已流式输出的文本 + 添加插话用户消息
    set((state) => ({
      messages: [
        ...(state.streamingText
          ? [...state.messages, { role: "assistant", content: state.streamingText } as ExtendedMessage]
          : state.messages),
        { role: "user", content: `[插话] ${text}` } as ExtendedMessage,
      ],
      streaming: true,
      streamingText: "",
      abortController: null,
    }));

    // 3. 发送 steer 请求注入方向
    steerChat(conversationId, text)
      .then(() => {
        // 4. steer 成功后，发起新的流式请求让 AI 继续生成
        const { abort } = streamChat(
          {
            message: text,
            conversation_id: conversationId,
          },
          (event: SSEEvent) => {
            handleSSEEvent(event, get, set);
          }
        );
        set({ abortController: () => abort() });
      })
      .catch((err) => {
        console.error("Steer failed:", err);
        set({ streaming: false });
      });
  },

  requestCandidates: (prompt: string) => {
    // 添加一个带 loading 状态的候选卡消息
    set((state) => ({
      messages: [
        ...state.messages,
        { role: "assistant", content: "", loadingCandidates: true },
      ],
    }));

    getCandidates(prompt, 3)
      .then(({ candidates }) => {
        set((state) => {
          const msgs = [...state.messages];
          // 替换最后一条 loading 消息
          msgs[msgs.length - 1] = {
            role: "assistant",
            content: "",
            candidates,
            loadingCandidates: false,
          };
          return { messages: msgs };
        });
      })
      .catch((err) => {
        console.error("Candidates failed:", err);
        set((state) => {
          const msgs = [...state.messages];
          msgs[msgs.length - 1] = {
            role: "assistant",
            content: "[获取候选失败]",
            loadingCandidates: false,
          };
          return { messages: msgs };
        });
      });
  },

  selectCandidate: (candidate: Candidate) => {
    // 将选中的候选卡作为用户消息发送
    get().sendMessage(candidate.text);
  },

  cancelStream: () => {
    const { abortController } = get();
    if (abortController) {
      abortController();
      set({ streaming: false, abortController: null });
    }
  },

  clearMessages: () => {
    set({ messages: [], conversationId: null, streaming: false });
  },

  loadConversation: async (convId: string) => {
    try {
      const msgs = await getConversationMessages(convId);
      set({
        messages: msgs.map((m) => ({ role: m.role, content: m.content })),
        conversationId: convId,
      });
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  },

  loadLatestConversation: async () => {
    try {
      const convs = await listConversations();
      set({ conversations: convs });
      if (convs.length > 0) {
        const latest = convs[0]; // 新的在前
        await get().loadConversation(latest.id);
      }
    } catch (err) {
      console.error("Failed to load latest conversation:", err);
    }
  },

  setConversations: (convs: Conversation[]) => {
    set({ conversations: convs });
  },

  switchConversation: (convId: string) => {
    const { abortController } = get();
    // 先中断当前流式请求
    if (abortController) {
      abortController();
    }
    get().loadConversation(convId);
  },

  startNewConversation: () => {
    const { abortController } = get();
    // 先中断当前流式请求
    if (abortController) {
      abortController();
    }
    set({
      messages: [],
      conversationId: null,
      streaming: false,
      streamingText: "",
      abortController: null,
    });
  },

  refreshConversations: async () => {
    try {
      const convs = await listConversations();
      set({ conversations: convs });
    } catch (err) {
      console.error("Failed to refresh conversations:", err);
    }
  },

  renameConversation: async (convId: string, title: string) => {
    try {
      await apiRenameConversation(convId, title);
      // 更新本地 conversations 列表中该项的 title
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === convId ? { ...c, title } : c
        ),
      }));
    } catch (err) {
      console.error("Failed to rename conversation:", err);
    }
  },

  deleteConversation: async (convId: string) => {
    try {
      await apiDeleteConversation(convId);
      const { conversationId, conversations } = get();
      const remaining = conversations.filter((c) => c.id !== convId);
      
      // 如果删除的是当前会话，切换到其他会话或创建新会话
      if (conversationId === convId) {
        if (remaining.length > 0) {
          // 切换到第一个可用会话
          const nextConv = remaining[0];
          const messages = await getConversationMessages(nextConv.id);
          set({
            conversations: remaining,
            conversationId: nextConv.id,
            messages: messages.map((m) => ({ ...m })),
            streaming: false,
            streamingText: "",
          });
        } else {
          // 没有其他会话，清空状态
          set({
            conversations: [],
            conversationId: null,
            messages: [],
            streaming: false,
            streamingText: "",
          });
        }
      } else {
        // 删除的不是当前会话，只更新列表
        set({ conversations: remaining });
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  },
}));

// 处理 SSE 事件
function handleSSEEvent(
  event: SSEEvent,
  get: () => ChatState,
  set: (fn: (state: ChatState) => Partial<ChatState>) => void
) {
  const { type, data } = event;

  switch (type) {
    case "turn_start":
      if (data.conversation_id) {
        set(() => ({ conversationId: data.conversation_id as string }));
      }
      break;

    case "text_delta":
      if (data.content) {
        set((state) => ({
          streamingText: state.streamingText + (data.content as string),
        }));
      }
      break;

    case "tool_call":
      if (data.name) {
        set((state) => ({
          messages: [
            ...state.messages,
            { role: "tool", content: `[调用工具: ${data.name}]` },
          ],
        }));
      }
      break;

    case "tool_result":
      break;

    case "done":
      set((state) => ({
        messages: state.streamingText
          ? [...state.messages, { role: "assistant", content: state.streamingText }]
          : state.messages,
        streaming: false,
        streamingText: "",
        abortController: null,
      }));
      useChapterStore.getState().fetchChapters();
      get().refreshConversations();
      break;

    case "error":
      set((state) => ({
        messages: [
          ...state.messages,
          { role: "assistant", content: `[错误: ${data.message || "未知错误"}]` },
        ],
        streaming: false,
        streamingText: "",
        abortController: null,
      }));
      break;
  }
}
