import { useState, useEffect } from "react";
import { useSettingsStore } from "../stores/settingsStore";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export default function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const categories = useSettingsStore((s) => s.categories);
  const settings = useSettingsStore((s) => s.settings);
  const uncensored = useSettingsStore((s) => s.uncensored);
  const loading = useSettingsStore((s) => s.loading);
  const fetchAll = useSettingsStore((s) => s.fetchAll);
  const addCategory = useSettingsStore((s) => s.addCategory);
  const removeCategory = useSettingsStore((s) => s.removeCategory);
  const addSetting = useSettingsStore((s) => s.addSetting);
  const updateSetting = useSettingsStore((s) => s.updateSetting);
  const removeSetting = useSettingsStore((s) => s.removeSetting);
  const toggleUncensored = useSettingsStore((s) => s.toggleUncensored);

  const [newCatName, setNewCatName] = useState("");
  const [newSettingCat, setNewSettingCat] = useState("");
  const [newSettingName, setNewSettingName] = useState("");
  const [newSettingContent, setNewSettingContent] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  useEffect(() => {
    if (open) fetchAll();
  }, [open, fetchAll]);

  const handleAddCategory = () => {
    if (!newCatName.trim()) return;
    addCategory(newCatName.trim());
    setNewCatName("");
  };

  const handleAddSetting = () => {
    if (!newSettingCat || !newSettingName.trim() || !newSettingContent.trim()) return;
    addSetting(newSettingCat, newSettingName.trim(), newSettingContent.trim());
    setNewSettingName("");
    setNewSettingContent("");
  };

  const handleStartEdit = (id: string, content: string) => {
    setEditingId(id);
    setEditContent(content);
  };

  const handleSaveEdit = (id: string) => {
    updateSetting(id, { content: editContent });
    setEditingId(null);
    setEditContent("");
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 面板 */}
      <div className="relative ml-auto w-[520px] h-full bg-zinc-900 border-l border-zinc-800 flex flex-col shadow-xl">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">设置</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6">
          {/* 破限模式 */}
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">破限模式</h3>
            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-zinc-200">启用破限</p>
                  <p className="text-xs text-zinc-500 mt-0.5">允许 AI 生成更自由的内容</p>
                </div>
                <button
                  onClick={() => toggleUncensored(!uncensored.enabled)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    uncensored.enabled ? "bg-red-500" : "bg-zinc-700"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                      uncensored.enabled ? "translate-x-5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              {uncensored.enabled && (
                <div className="mt-3 pt-3 border-t border-zinc-700">
                  <p className="text-xs text-zinc-400">当前级别：{uncensored.level}</p>
                </div>
              )}
            </div>
          </section>

          {/* 设定类别 */}
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">设定类别</h3>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newCatName}
                onChange={(e) => setNewCatName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddCategory()}
                placeholder="新类别名称..."
                className="flex-1 bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              />
              <button
                onClick={handleAddCategory}
                className="text-xs px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded"
              >
                添加
              </button>
            </div>
            {categories.length === 0 ? (
              <p className="text-xs text-zinc-600 py-2">暂无类别</p>
            ) : (
              <div className="flex flex-wrap gap-1">
                {categories.map((cat) => (
                  <span
                    key={cat.id}
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-zinc-800 text-zinc-300 rounded border border-zinc-700"
                  >
                    {cat.name}
                    <button
                      onClick={() => {
                        if (confirm(`确定删除类别「${cat.name}」？`)) removeCategory(cat.id);
                      }}
                      className="text-zinc-500 hover:text-red-400"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* 设定条目 */}
          <section>
            <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">世界设定</h3>
            {/* 添加表单 */}
            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 mb-3 space-y-2">
              <select
                value={newSettingCat}
                onChange={(e) => setNewSettingCat(e.target.value)}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              >
                <option value="">选择类别...</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.name}>
                    {cat.name}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={newSettingName}
                onChange={(e) => setNewSettingName(e.target.value)}
                placeholder="设定名称..."
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
              />
              <textarea
                value={newSettingContent}
                onChange={(e) => setNewSettingContent(e.target.value)}
                placeholder="设定内容..."
                rows={3}
                className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-1.5 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
              />
              <button
                onClick={handleAddSetting}
                disabled={!newSettingCat || !newSettingName.trim() || !newSettingContent.trim()}
                className="text-xs px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              >
                添加设定
              </button>
            </div>
            {/* 列表 */}
            {loading ? (
              <p className="text-xs text-zinc-600 py-2">加载中...</p>
            ) : settings.length === 0 ? (
              <p className="text-xs text-zinc-600 py-2">暂无设定</p>
            ) : (
              <div className="space-y-2">
                {settings.map((s) => (
                  <div key={s.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-medium text-zinc-200">{s.name}</h4>
                        <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded">
                          {s.category}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => (editingId === s.id ? handleSaveEdit(s.id) : handleStartEdit(s.id, s.content))}
                          className="text-xs text-zinc-500 hover:text-zinc-300"
                        >
                          {editingId === s.id ? "保存" : "编辑"}
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`确定删除设定「${s.name}」？`)) removeSetting(s.id);
                          }}
                          className="text-xs text-zinc-500 hover:text-red-400"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                    {editingId === s.id ? (
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        rows={3}
                        className="w-full bg-zinc-800 text-zinc-200 text-xs px-2 py-1 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
                      />
                    ) : (
                      <p className="text-xs text-zinc-400 whitespace-pre-wrap">{s.content}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
