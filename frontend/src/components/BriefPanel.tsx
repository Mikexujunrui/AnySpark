import { useState, useEffect } from "react";
import PanelHeader from "./ui/PanelHeader";
import { useBriefStore } from "../stores/briefStore";
import { useApproval } from "./approval/ApprovalContext";

interface BriefPanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
  bookId?: string; // S101：按项目隔离简介
}

// 项目简介面板（S58：项目智能体简介，AI 与用户共看的协作总览）
export default function BriefPanel({ open, onClose, embedded = false, bookId = "main" }: BriefPanelProps) {
  const content = useBriefStore((s) => s.content);
  const exists = useBriefStore((s) => s.exists);
  const loading = useBriefStore((s) => s.loading);
  const draft = useBriefStore((s) => s.draft);
  const note = useBriefStore((s) => s.note);
  const generating = useBriefStore((s) => s.generating);
  const fetchBrief = useBriefStore((s) => s.fetchBrief);
  const save = useBriefStore((s) => s.save);
  const generate = useBriefStore((s) => s.generate);
  const setDraft = useBriefStore((s) => s.setDraft);
  const clearDraft = useBriefStore((s) => s.clearDraft);
  const { requestApproval } = useApproval()

  // 高负载：AI 生成草案（LLM 约 14s）→ 先审批，同意才执行
  const handleGenerate = async () => {
    const ok = await requestApproval({
      title: 'AI 生成项目简介草案',
      desc: '从现有项目数据（设定/方向/进展）提炼总览，约 14 秒。生成后需人工确认才保存生效。',
      estSeconds: 14,
      cost: 'medium',
    })
    if (ok) generate(bookId)
  }

  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      fetchBrief(bookId);
      setEditing(false);
    }
  }, [open, fetchBrief, bookId]);

  if (!open) return null;

  // 编辑框内容：草稿优先（AI 生成待确认），否则当前正文
  const editorText = draft || editText;

  const handleStartEdit = () => {
    setEditText(content);
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
    setEditText("");
    clearDraft();
  };

  const handleSave = async () => {
    if (!editorText.trim()) return;
    setSaving(true);
    try {
      await save(bookId, editorText.trim());
      setEditing(false);
      setEditText("");
      setSaving(false);
    } catch {
      setSaving(false);
    }
  };

  // S101：删除简介（空内容保存=后端删文件）
  const handleDelete = async () => {
    if (!window.confirm("删除项目简介？此操作不可恢复。")) return;
    setSaving(true);
    try {
      await save(bookId, "");
      setEditing(false);
      setEditText("");
      setSaving(false);
    } catch {
      setSaving(false);
    }
  };

  return (
    <div className={embedded ? "h-full flex flex-col" : "fixed inset-0 z-50 flex"}>
      {/* 遮罩 */}
      {!embedded && <div className="absolute inset-0 bg-black/50" onClick={onClose} />}

      {/* 面板 */}
      <div className={embedded ? "h-full w-full flex flex-col" : "relative ml-auto w-96 h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl"}>
        {/* 头部 */}
        <PanelHeader
          compact
          maxW={false}
          icon="file-text"
          iconClass="text-amber-400"
          title="项目简介"
          desc="协作约定 · 项目上下文"
          actions={
            <div className="flex items-center gap-2">
            {!editing && (
              <button
                onClick={handleStartEdit}
                disabled={loading}
                className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-300 rounded"
              >
                编辑
              </button>
            )}
            {!editing && exists && (
              <button
                onClick={handleDelete}
                disabled={loading || saving}
                title="删除项目简介"
                className="text-xs px-2 py-1 bg-red-900/40 hover:bg-red-800/50 disabled:opacity-50 text-red-300 rounded"
              >
                删除
              </button>
            )}
            <button
              onClick={onClose}
              className="text-zinc-500 hover:text-zinc-300"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            </div>
          }
        />

        {/* 操作条：AI 生成草案 */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="text-xs px-3 py-1 bg-purple-600 hover:bg-purple-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
          >
            {generating ? "生成中..." : "AI 生成草案"}
          </button>
          {note && <span className="text-[11px] text-amber-400 truncate">{note}</span>}
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading ? (
            <p className="text-zinc-600 text-sm text-center py-4">加载中...</p>
          ) : editing || draft ? (
            <div className="space-y-2">
              <textarea
                value={editorText}
                onChange={(e) => setDraft(e.target.value)}
                rows={16}
                placeholder="输入项目简介（一句话世界观/主线/角色/基调/当前进展/写作注意）..."
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
              />
              {draft && (
                <p className="text-[11px] text-zinc-500">
                  ↑ AI 生成的草案，请人工确认后保存生效
                </p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={handleSave}
                  disabled={saving || !editorText.trim()}
                  className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
                >
                  {saving ? "保存中..." : "保存"}
                </button>
                <button
                  onClick={handleCancelEdit}
                  className="text-xs px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
                >
                  取消
                </button>
              </div>
            </div>
          ) : !exists ? (
            <p className="text-zinc-600 text-sm text-center py-4">
              暂无项目简介，点「AI 生成草案」或「编辑」创建
            </p>
          ) : (
            <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
              {content}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
