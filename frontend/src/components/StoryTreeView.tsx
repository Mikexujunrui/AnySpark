import { useEffect, useState } from "react";
import { useStoryStore } from "../stores/storyStore";
import type { StoryNode, StoryThread } from "../api/story";

// 节点样式按 kind 区分
const KIND_STYLES: Record<StoryNode["kind"], { bg: string; border: string; label: string }> = {
  root: { bg: "bg-amber-900/30", border: "border-amber-500", label: "根" },
  main: { bg: "bg-emerald-900/30", border: "border-emerald-500", label: "主线" },
  anchor: { bg: "bg-purple-900/30", border: "border-purple-500", label: "锚点" },
  candidate: { bg: "bg-zinc-800/50", border: "border-zinc-600 border-dashed", label: "候选" },
  subplot: { bg: "bg-blue-900/30", border: "border-blue-500", label: "支线" },
  loop: { bg: "bg-rose-900/30", border: "border-rose-500", label: "循环" },
};

export default function StoryTreeView() {
  const { nodes, threads, loading, selectedNodeId, fetchTree, addNode, choose, anchor, selectNode } =
    useStoryStore();
  const [showAddInput, setShowAddInput] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  const handleAdd = async () => {
    const content = newContent.trim();
    if (!content) return;
    try {
      await addNode(content, parentId || undefined);
      setNewContent("");
      setShowAddInput(false);
      setParentId(null);
    } catch {
      // error handled in store
    }
  };

  // 构建树结构
  const rootNodes = nodes.filter((n) => !n.parent_id);
  const childrenOf = (id: string) => nodes.filter((n) => n.parent_id === id);

  // 选中的节点详情
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-2 shrink-0">
        <button
          onClick={() => {
            setShowAddInput(!showAddInput);
            setParentId(null);
          }}
          className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
            showAddInput ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          + 节点
        </button>
        <span className="text-[11px] text-zinc-600">|</span>
        <span className="text-[11px] text-zinc-500">
          {nodes.length} 节点 · {threads.filter((t) => t.status === "active").length} 线进行中
        </span>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：树视图 */}
        <div className="flex-1 overflow-auto p-4">
          {loading && nodes.length === 0 ? (
            <p className="text-sm text-zinc-600 text-center py-8">加载中...</p>
          ) : nodes.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm text-zinc-600 mb-2">叙事树为空</p>
              <p className="text-xs text-zinc-700">通过探索或手动添加节点来构建树</p>
            </div>
          ) : (
            <div className="space-y-2">
              {rootNodes.map((node) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  children={childrenOf(node.id)}
                  allNodes={nodes}
                  selectedId={selectedNodeId}
                  onSelect={selectNode}
                  onChoose={choose}
                  onAnchor={anchor}
                  onAddChild={(id) => {
                    setParentId(id);
                    setShowAddInput(true);
                  }}
                  depth={0}
                />
              ))}
            </div>
          )}
        </div>

        {/* 右侧：详情面板 */}
        {selectedNode && (
          <div className="w-64 border-l border-zinc-800 bg-zinc-900/30 p-3 overflow-auto">
            <div className="flex items-center justify-between mb-2">
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${KIND_STYLES[selectedNode.kind].bg} ${KIND_STYLES[selectedNode.kind].border} border`}>
                {KIND_STYLES[selectedNode.kind].label}
              </span>
              <button
                onClick={() => selectNode(null)}
                className="text-zinc-600 hover:text-zinc-400 text-xs"
              >
                ×
              </button>
            </div>
            <p className="text-sm text-zinc-200 mb-3 whitespace-pre-wrap">{selectedNode.content}</p>
            <div className="space-y-1.5">
              {selectedNode.kind !== "main" && (
                <button
                  onClick={() => choose(selectedNode.id)}
                  className="w-full text-left text-xs px-2 py-1 rounded bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50 transition-colors"
                >
                  选为主线
                </button>
              )}
              {selectedNode.kind !== "anchor" && (
                <button
                  onClick={() => anchor(selectedNode.id)}
                  className="w-full text-left text-xs px-2 py-1 rounded bg-purple-900/30 text-purple-400 hover:bg-purple-900/50 transition-colors"
                >
                  标为锚点
                </button>
              )}
              <button
                onClick={() => {
                  setParentId(selectedNode.id);
                  setShowAddInput(true);
                }}
                className="w-full text-left text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"
              >
                添加子节点
              </button>
            </div>
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <p className="text-[10px] text-zinc-600">
                创建：{new Date(selectedNode.created_at).toLocaleDateString()}
              </p>
              {selectedNode.chosen && (
                <p className="text-[10px] text-emerald-500 mt-1">当前主线</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 添加节点输入 */}
      {showAddInput && (
        <div className="border-t border-zinc-800 bg-zinc-900/50 p-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
                if (e.key === "Escape") {
                  setShowAddInput(false);
                  setNewContent("");
                  setParentId(null);
                }
              }}
              placeholder={parentId ? "子节点内容..." : "节点内容..."}
              className="flex-1 bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              autoFocus
            />
            <button
              onClick={handleAdd}
              className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm rounded"
            >
              添加
            </button>
            <button
              onClick={() => {
                setShowAddInput(false);
                setNewContent("");
                setParentId(null);
              }}
              className="px-2 py-1.5 text-zinc-500 hover:text-zinc-300 text-sm"
            >
              取消
            </button>
          </div>
          {parentId && (
            <p className="text-[10px] text-zinc-600 mt-1">
              父节点：{nodes.find((n) => n.id === parentId)?.content.slice(0, 30)}...
            </p>
          )}
        </div>
      )}

      {/* 底部：线进度 */}
      {threads.length > 0 && (
        <div className="border-t border-zinc-800 bg-zinc-900/30 px-3 py-2">
          <p className="text-[10px] text-zinc-600 mb-1">叙事线</p>
          <div className="flex flex-wrap gap-2">
            {threads.map((t) => (
              <ThreadBadge key={t.id} thread={t} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// 树节点组件（递归）
function TreeNode({
  node,
  children,
  allNodes,
  selectedId,
  onSelect,
  onChoose,
  onAnchor,
  onAddChild,
  depth,
}: {
  node: StoryNode;
  children: StoryNode[];
  allNodes: StoryNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onChoose: (id: string) => void;
  onAnchor: (id: string) => void;
  onAddChild: (id: string) => void;
  depth: number;
}) {
  const style = KIND_STYLES[node.kind];
  const isSelected = node.id === selectedId;

  return (
    <div style={{ marginLeft: depth * 20 }}>
      {/* 节点卡片 */}
      <div
        onClick={() => onSelect(node.id)}
        className={`group relative p-2 rounded border cursor-pointer transition-all ${style.bg} ${style.border} ${
          node.chosen ? "ring-1 ring-emerald-500/50" : ""
        } ${isSelected ? "ring-2 ring-zinc-400" : "hover:ring-1 hover:ring-zinc-600"}`}
      >
        <div className="flex items-start gap-2">
          {node.kind === "anchor" && <span className="text-purple-400 text-xs">⚓</span>}
          {node.chosen && <span className="text-emerald-400 text-xs">●</span>}
          <span className="text-xs text-zinc-200 flex-1 line-clamp-2">{node.content}</span>
        </div>
        {/* 操作按钮（hover 显示） */}
        <div className="absolute right-1 top-1 opacity-0 group-hover:opacity-100 flex gap-0.5 transition-opacity">
          {node.kind === "candidate" && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onChoose(node.id);
              }}
              className="text-[9px] px-1 py-0.5 bg-emerald-900/50 text-emerald-400 rounded hover:bg-emerald-900/80"
              title="选为主线"
            >
              主
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAddChild(node.id);
            }}
            className="text-[9px] px-1 py-0.5 bg-zinc-700 text-zinc-400 rounded hover:bg-zinc-600"
            title="添加子节点"
          >
            +
          </button>
        </div>
      </div>
      {/* 子节点 */}
      {children.length > 0 && (
        <div className="mt-1 space-y-1">
          {children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              children={allNodes.filter((n) => n.parent_id === child.id)}
              allNodes={allNodes}
              selectedId={selectedId}
              onSelect={onSelect}
              onChoose={onChoose}
              onAnchor={onAnchor}
              onAddChild={onAddChild}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 线进度徽章
function ThreadBadge({ thread }: { thread: StoryThread }) {
  const roleLabel = { main: "主线", subplot: "支线", parallel: "多线" }[thread.role];
  const roleColor = { main: "text-emerald-400", subplot: "text-blue-400", parallel: "text-purple-400" }[thread.role];

  return (
    <div className="flex items-center gap-1.5 text-[11px]">
      <span className={`${roleColor}`}>{roleLabel}</span>
      <span className="text-zinc-300">{thread.name}</span>
      {thread.progress && (
        <span className="text-zinc-600">· {thread.progress}</span>
      )}
      {thread.status === "done" && (
        <span className="text-[9px] text-zinc-600">[完成]</span>
      )}
    </div>
  );
}
