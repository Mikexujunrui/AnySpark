import { useState, useEffect } from "react";
import { useSkillStore } from "../stores/skillStore";

interface SkillPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
}

export default function SkillPanel({ open, onClose, embedded = false }: SkillPanelProps) {
  const skills = useSkillStore((s) => s.skills);
  const loading = useSkillStore((s) => s.loading);
  const fetchSkills = useSkillStore((s) => s.fetchSkills);
  const addSkill = useSkillStore((s) => s.addSkill);
  const editSkill = useSkillStore((s) => s.editSkill);
  const removeSkill = useSkillStore((s) => s.removeSkill);

  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newTarget, setNewTarget] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTarget, setEditTarget] = useState("");

  useEffect(() => {
    if (open) fetchSkills();
  }, [open, fetchSkills]);

  const handleAdd = async () => {
    if (!newName.trim() || !newContent.trim()) return;
    await addSkill(
      newName.trim(),
      newContent.trim(),
      newDescription.trim() || undefined,
      newTarget.trim() || undefined
    );
    setNewName("");
    setNewContent("");
    setNewDescription("");
    setNewTarget("");
    setShowAdd(false);
  };

  const handleEdit = async (id: string) => {
    if (!editName.trim() || !editContent.trim()) return;
    await editSkill(id, {
      name: editName.trim(),
      content: editContent.trim(),
      description: editDescription.trim() || undefined,
      target: editTarget.trim() || undefined,
    });
    setEditingId(null);
    setEditName("");
    setEditContent("");
    setEditDescription("");
    setEditTarget("");
  };

  const handleToggleEnabled = async (id: string, currentEnabled: boolean) => {
    await editSkill(id, { enabled: !currentEnabled });
  };

  const handleDelete = async (id: string) => {
    if (confirm("确定删除这个技巧？")) {
      await removeSkill(id);
    }
  };

  if (!open) return null;

  // 内嵌模式（展示区内）
  if (embedded) {
    return (
      <div className="h-full bg-zinc-900 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : skills.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无技巧</p>
          ) : (
            skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                editingId={editingId}
                setEditingId={setEditingId}
                editName={editName}
                setEditName={setEditName}
                editContent={editContent}
                setEditContent={setEditContent}
                editDescription={editDescription}
                setEditDescription={setEditDescription}
                editTarget={editTarget}
                setEditTarget={setEditTarget}
                handleEdit={handleEdit}
                handleToggleEnabled={handleToggleEnabled}
                handleDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-[480px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">技巧库</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAdd(!showAdd)}
              className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
            >
              {showAdd ? "取消" : "+ 新增"}
            </button>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 新增表单 */}
        {showAdd && (
          <div className="px-4 py-3 border-b border-zinc-800 space-y-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="技巧名称 *"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="技巧内容 *"
              rows={4}
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="描述（可选）"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <input
              type="text"
              value={newTarget}
              onChange={(e) => setNewTarget(e.target.value)}
              placeholder="目标（可选，如章节/场景）"
              className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
            />
            <button
              onClick={handleAdd}
              disabled={!newName.trim() || !newContent.trim()}
              className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
            >
              添加
            </button>
          </div>
        )}

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : skills.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">暂无技巧</p>
          ) : (
            skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                editingId={editingId}
                setEditingId={setEditingId}
                editName={editName}
                setEditName={setEditName}
                editContent={editContent}
                setEditContent={setEditContent}
                editDescription={editDescription}
                setEditDescription={setEditDescription}
                editTarget={editTarget}
                setEditTarget={setEditTarget}
                handleEdit={handleEdit}
                handleToggleEnabled={handleToggleEnabled}
                handleDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// 技巧卡片组件
import type { Skill } from "../api/skills";

function SkillCard({
  skill,
  editingId,
  setEditingId,
  editName,
  setEditName,
  editContent,
  setEditContent,
  editDescription,
  setEditDescription,
  editTarget,
  setEditTarget,
  handleEdit,
  handleToggleEnabled,
  handleDelete,
}: {
  skill: Skill;
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  editName: string;
  setEditName: (v: string) => void;
  editContent: string;
  setEditContent: (v: string) => void;
  editDescription: string;
  setEditDescription: (v: string) => void;
  editTarget: string;
  setEditTarget: (v: string) => void;
  handleEdit: (id: string) => void;
  handleToggleEnabled: (id: string, enabled: boolean) => void;
  handleDelete: (id: string) => void;
}) {
  return (
    <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-2">
      {/* 名称 + 操作 */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">{skill.name}</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleToggleEnabled(skill.id, !!skill.enabled)}
            className={`text-[10px] px-1.5 py-0.5 rounded border ${
              skill.enabled
                ? "bg-green-500/20 text-green-400 border-green-500/30"
                : "bg-zinc-700/50 text-zinc-500 border-zinc-600/50"
            }`}
          >
            {skill.enabled ? "启用" : "禁用"}
          </button>
          <button
            onClick={() => {
              setEditingId(skill.id);
              setEditName(skill.name);
              setEditContent(skill.content);
              setEditDescription(skill.description || "");
              setEditTarget(skill.target || "");
            }}
            className="p-1 text-zinc-600 hover:text-zinc-400 rounded"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button
            onClick={() => handleDelete(skill.id)}
            className="p-1 text-zinc-600 hover:text-red-400 rounded"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>

      {/* 描述 */}
      {skill.description && (
        <p className="text-xs text-zinc-500">{skill.description}</p>
      )}

      {/* 目标 */}
      {skill.target && (
        <span className="inline-block text-[10px] px-1.5 py-0.5 bg-zinc-700/50 text-zinc-400 rounded">
          目标: {skill.target}
        </span>
      )}

      {/* 内容 */}
      {editingId === skill.id ? (
        <div className="space-y-2">
          <input
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            placeholder="名称"
            className="w-full bg-zinc-900 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-600 focus:outline-none"
          />
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            placeholder="内容"
            rows={4}
            className="w-full bg-zinc-900 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-600 focus:outline-none resize-none"
          />
          <input
            type="text"
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            placeholder="描述"
            className="w-full bg-zinc-900 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-600 focus:outline-none"
          />
          <input
            type="text"
            value={editTarget}
            onChange={(e) => setEditTarget(e.target.value)}
            placeholder="目标"
            className="w-full bg-zinc-900 text-zinc-200 text-sm px-2 py-1 rounded border border-zinc-600 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleEdit(skill.id)}
              className="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded"
            >
              保存
            </button>
            <button
              onClick={() => setEditingId(null)}
              className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-zinc-300 whitespace-pre-wrap line-clamp-3">
          {skill.content}
        </p>
      )}
    </div>
  );
}
