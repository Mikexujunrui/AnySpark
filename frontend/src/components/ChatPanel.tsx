import { useState, useRef, useEffect } from "react";
import { useChatStore } from "../stores/chatStore";
import { useDisplayStore } from "../stores/displayStore";
import type { Candidate } from "../api/chat";

// 斜杠命令定义
const SLASH_COMMANDS = [
  { name: "write", description: "切换到稿纸模式", action: () => useDisplayStore.getState().setMode("paper") },
  { name: "explore", description: "切换到探索模式", action: () => useDisplayStore.getState().setMode("explore") },
  { name: "tree", description: "切换到叙事树模式", action: () => useDisplayStore.getState().setMode("tree") },
  { name: "skills", description: "切换到技巧模式", action: () => useDisplayStore.getState().setMode("skills") },
  { name: "check", description: "切换到审读模式", action: () => useDisplayStore.getState().setMode("check") },
];

export default function ChatPanel() {
  const { messages, streaming, streamingText, sendMessage, sendSteer, cancelStream, declareDirection, rewriteMessage } = useChatStore();
  const [input, setInput] = useState("");
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashFilter, setSlashFilter] = useState("");
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 过滤后的命令列表
  const filteredCommands = SLASH_COMMANDS.filter(cmd =>
    cmd.name.toLowerCase().includes(slashFilter.toLowerCase())
  );

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // 检测斜杠命令
    if (value.startsWith("/")) {
      const filter = value.slice(1).split(" ")[0];
      setSlashFilter(filter);
      setShowSlashMenu(true);
      setSelectedCommandIndex(0);
    } else {
      setShowSlashMenu(false);
    }
  };

  const handleSelectCommand = (cmd: typeof SLASH_COMMANDS[0]) => {
    cmd.action();
    setInput("");
    setShowSlashMenu(false);
  };

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
    // 斜杠命令导航
    if (showSlashMenu) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCommandIndex((prev) => (prev + 1) % filteredCommands.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCommandIndex((prev) => (prev - 1 + filteredCommands.length) % filteredCommands.length);
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (filteredCommands[selectedCommandIndex]) {
          handleSelectCommand(filteredCommands[selectedCommandIndex]);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        setShowSlashMenu(false);
      }
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSelectCandidate = (candidate: Candidate) => {
    useChatStore.getState().selectCandidate(candidate);
  };

  const handleDirection = () => {
    const text = input.trim();
    if (!text || streaming) return;
    declareDirection(text);
    setInput("");
  };

  const handleRewrite = (index: number, mode: "subtle" | "balanced" | "bold") => {
    rewriteMessage(index, mode);
  };

  return (
    <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden">
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
            onRewrite={(mode) => handleRewrite(i, mode)}
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
      <div className="px-4 py-3 border-t border-zinc-800 relative">
        {/* 斜杠命令菜单 */}
        {showSlashMenu && filteredCommands.length > 0 && (
          <div className="absolute bottom-full left-4 right-4 mb-2 bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg overflow-hidden z-10">
            <div className="px-3 py-2 border-b border-zinc-700 text-xs text-zinc-500">
              斜杠命令
            </div>
            {filteredCommands.map((cmd, i) => (
              <button
                key={cmd.name}
                onClick={() => handleSelectCommand(cmd)}
                className={`w-full px-3 py-2 text-left flex items-center gap-3 transition-colors ${
                  i === selectedCommandIndex
                    ? "bg-zinc-700 text-zinc-100"
                    : "text-zinc-300 hover:bg-zinc-700/50"
                }`}
              >
                <span className="font-mono text-sm text-amber-400">/{cmd.name}</span>
                <span className="text-xs text-zinc-500">{cmd.description}</span>
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={streaming ? "输入插话引导方向... (Enter 发送)" : "输入消息... (/ 打开命令菜单, Enter 发送, Shift+Enter 换行)"}
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
            <div className="flex gap-2">
              <button
                onClick={handleDirection}
                disabled={!input.trim()}
                className="px-3 py-2 bg-amber-900/40 hover:bg-amber-900/60 disabled:bg-zinc-800 disabled:text-zinc-600 text-amber-300 text-sm rounded-lg border border-amber-800/40"
                title="AI 先声明要写什么（摩擦前置，用户确认）"
              >
                方向
              </button>
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 text-sm rounded-lg"
              >
                发送
              </button>
            </div>
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
  onRewrite,
}: {
  role: string;
  content: string;
  candidates?: Candidate[];
  loadingCandidates?: boolean;
  onSelectCandidate: (c: Candidate) => void;
  onRewrite?: (mode: "subtle" | "balanced" | "bold") => void;
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
        className={`max-w-[80%] rounded-lg px-3 py-2 ${isUser
          ? "bg-zinc-700 text-zinc-100"
          : "bg-zinc-800/60 text-zinc-200"}`}
      >
        <p className="text-sm whitespace-pre-wrap">{content}</p>
        {/* AI 消息：改写渐变条 */}
        {!isUser && onRewrite && content && (
          <div className="flex items-center gap-1 mt-2 pt-2 border-t border-zinc-700/50">
            <span className="text-[10px] text-zinc-500 mr-1">改写</span>
            <button
              onClick={() => onRewrite("subtle")}
              className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
              title="轻微润色"
            >
              保原味
            </button>
            <button
              onClick={() => onRewrite("balanced")}
              className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
              title="语言更生动"
            >
              适中
            </button>
            <button
              onClick={() => onRewrite("bold")}
              className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
              title="大胆重构"
            >
              大幅改
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
