import { useState, useRef, useEffect } from "react";
import { useChatStore } from "../stores/chatStore";
import type { Candidate } from "../api/chat";

export default function ChatPanel() {
  const { messages, streaming, streamingText, sendMessage, sendSteer, cancelStream } = useChatStore();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;

    if (streaming) {
      // 流式中发送 steer
      sendSteer(text);
    } else {
      sendMessage(text);
    }
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSelectCandidate = (candidate: Candidate) => {
    useChatStore.getState().selectCandidate(candidate);
  };

  return (
    <div className="h-[45%] flex flex-col bg-zinc-950 border-t border-zinc-800">
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !streaming && (
          <p className="text-zinc-700 text-sm text-center py-8">
            输入消息开始对话，或让 AI 帮你写章节
          </p>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            role={msg.role}
            content={msg.content}
            candidates={msg.candidates}
            loadingCandidates={msg.loadingCandidates}
            onSelectCandidate={handleSelectCandidate}
          />
        ))}

        {/* 流式输出中的文本 */}
        {streaming && streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[80%] bg-zinc-800/60 rounded-lg px-3 py-2">
              <p className="text-sm text-zinc-200 whitespace-pre-wrap">{streamingText}</p>
              <span className="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}

        {/* 流式中但没有文本（等待首个 token） */}
        {streaming && !streamingText && (
          <div className="flex justify-start">
            <div className="bg-zinc-800/60 rounded-lg px-3 py-2">
              <span className="text-sm text-zinc-500">思考中...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div className="px-4 py-3 border-t border-zinc-800">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={streaming ? "输入插话引导方向... (Enter 发送)" : "输入消息... (Enter 发送, Shift+Enter 换行)"}
            rows={1}
            className="flex-1 bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded-lg border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
          />
          {streaming ? (
            <div className="flex gap-2">
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="px-3 py-2 bg-blue-900/50 hover:bg-blue-900/70 disabled:bg-zinc-800 disabled:text-zinc-600 text-blue-300 text-sm rounded-lg border border-blue-800/50"
              >
                插话
              </button>
              <button
                onClick={cancelStream}
                className="px-3 py-2 bg-red-900/50 hover:bg-red-900/70 text-red-300 text-sm rounded-lg border border-red-800/50"
              >
                停止
              </button>
            </div>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 text-sm rounded-lg"
            >
              发送
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// 消息气泡组件
function MessageBubble({
  role,
  content,
  candidates,
  loadingCandidates,
  onSelectCandidate,
}: {
  role: string;
  content: string;
  candidates?: Candidate[];
  loadingCandidates?: boolean;
  onSelectCandidate: (c: Candidate) => void;
}) {
  if (role === "tool") {
    return (
      <div className="flex justify-center">
        <span className="text-xs text-zinc-600 bg-zinc-800/40 px-2 py-0.5 rounded">
          {content}
        </span>
      </div>
    );
  }

  // 候选卡消息
  if (loadingCandidates) {
    return (
      <div className="flex justify-start">
        <div className="bg-zinc-800/60 rounded-lg px-3 py-2">
          <span className="text-sm text-zinc-500">生成候选中...</span>
        </div>
      </div>
    );
  }

  if (candidates && candidates.length > 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-zinc-500 pl-1">选择你喜欢的方向：</p>
        <div className="grid gap-2">
          {candidates.map((c) => (
            <button
              key={c.id}
              onClick={() => onSelectCandidate(c)}
              className="text-left bg-zinc-800/60 hover:bg-zinc-700/60 border border-zinc-700/50 rounded-lg px-3 py-2 transition-colors group"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-zinc-400 group-hover:text-zinc-300">
                  {c.style}
                </span>
                <svg className="w-3 h-3 text-zinc-600 group-hover:text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
              <p className="text-sm text-zinc-300 line-clamp-3">{c.text}</p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 ${
          isUser
            ? "bg-zinc-700 text-zinc-100"
            : "bg-zinc-800/60 text-zinc-200"
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
