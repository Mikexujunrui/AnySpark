import { useEffect, useState } from "react";
import { useChatStore } from "../stores/chatStore";
import { listConversations, type Conversation } from "../api/conversations";

export default function ConversationList() {
  const conversations = useChatStore((s) => s.conversations);
  const currentConvId = useChatStore((s) => s.conversationId);
  const setConversations = useChatStore((s) => s.setConversations);
  const switchConversation = useChatStore((s) => s.switchConversation);
  const startNewConversation = useChatStore((s) => s.startNewConversation);
  const renameConversation = useChatStore((s) => s.renameConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  useEffect(() => {
    listConversations().then(setConversations).catch(console.error);
  }, [setConversations]);

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}小时前`;
    const days = Math.floor(hours / 24);
    return `${days}天前`;
  };

  const handleDoubleClick = (conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title || "");
  };

  const handleSaveTitle = async (convId: string) => {
    await renameConversation(convId, editTitle);
    setEditingId(null);
    setEditTitle("");
  };

  const handleKeyDown = (e: React.KeyboardEvent, convId: string) => {
    if (e.key === "Enter") {
      handleSaveTitle(convId);
    } else if (e.key === "Escape") {
      setEditingId(null);
      setEditTitle("");
    }
  };

  const handleDelete = async (convId: string) => {
    if (confirm("确定删除此会话？")) {
      await deleteConversation(convId);
    }
  };

  return (
    <div className="flex flex-col h-full border-r border-zinc-800 bg-zinc-900">
      {/* 标题 + 新建按钮 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <h2 className="text-xs font-medium text-zinc-400">会话</h2>
        <button
          onClick={startNewConversation}
          className="text-xs px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
          title="新建会话"
        >
          +
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="px-3 py-4 text-xs text-zinc-500 text-center">
            暂无会话
          </div>
        ) : (
          conversations.map((conv: Conversation) => (
            <div
              key={conv.id}
              onClick={() => switchConversation(conv.id)}
              className={`group px-3 py-2 cursor-pointer border-b border-zinc-800/50 hover:bg-zinc-800/50 ${
                currentConvId === conv.id ? "bg-zinc-800" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                {editingId === conv.id ? (
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => handleSaveTitle(conv.id)}
                    onKeyDown={(e) => handleKeyDown(e, conv.id)}
                    className="flex-1 text-xs bg-zinc-700 text-zinc-200 px-1 py-0.5 rounded border border-zinc-600 focus:outline-none focus:border-zinc-500"
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span
                    className="text-xs text-zinc-300 truncate flex-1"
                    onDoubleClick={() => handleDoubleClick(conv)}
                    title={conv.title || "双击编辑"}
                  >
                    {conv.title || formatTime(conv.created_at)}
                  </span>
                )}
                {currentConvId !== conv.id && editingId !== conv.id && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(conv.id);
                    }}
                    className="ml-2 text-xs text-zinc-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="删除会话"
                  >
                    ×
                  </button>
                )}
              </div>
              {editingId !== conv.id && (
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[10px] text-zinc-500">
                    {conv.title ? formatTime(conv.created_at) : ""}
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    {conv.message_count}条
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
