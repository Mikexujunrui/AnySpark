import { useEffect, useState } from "react";
import ConversationList from "./ConversationList";
import ChapterBar from "./ChapterBar";
import DisplayArea from "./DisplayArea";
import ChatPanel from "./ChatPanel";
import ModelPicker from "./ModelPicker";
import AgencySelector from "./AgencySelector";
import ManualPanel from "./ManualPanel";
import GraphPanel from "./GraphPanel";
import SettingsPanel from "./SettingsPanel";
import MaterialPanel from "./MaterialPanel";
import { useModelStore } from "../stores/modelStore";
import { useChatStore } from "../stores/chatStore";

export default function Layout() {
  const fetchModels = useModelStore((s) => s.fetchModels);
  const loadLatestConversation = useChatStore((s) => s.loadLatestConversation);

  const [convListOpen, setConvListOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [materialOpen, setMaterialOpen] = useState(false);

  // 初始化加载模型列表 + 恢复最近会话
  useEffect(() => {
    fetchModels();
    loadLatestConversation();
  }, [fetchModels, loadLatestConversation]);

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      {/* 顶栏 */}
      <header className="h-10 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-medium text-zinc-300 tracking-wide">
            AnySpark v4
          </h1>
          {/* 会话列表切换 */}
          <button
            onClick={() => setConvListOpen(!convListOpen)}
            className={`text-xs px-2 py-0.5 rounded transition-colors ${
              convListOpen
                ? "bg-zinc-700 text-zinc-200"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            会话
          </button>
        </div>

        {/* 右侧控件 */}
        <div className="flex items-center gap-4">
          <AgencySelector />
          <ModelPicker />
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setManualOpen(!manualOpen)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                manualOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              心智
            </button>
            <button
              onClick={() => setGraphOpen(!graphOpen)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                graphOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              图谱
            </button>
            <button
              onClick={() => setMaterialOpen(!materialOpen)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                materialOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              资料
            </button>
            <button
              onClick={() => setSettingsOpen(!settingsOpen)}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                settingsOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              设置
            </button>
          </div>
        </div>
      </header>

      {/* 主体：左右分栏 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：会话列表（可折叠） */}
        {convListOpen && (
          <div className="w-48 shrink-0 border-r border-zinc-800">
            <ConversationList />
          </div>
        )}

        {/* 右侧：展示区 + 对话区 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 章节条 */}
          <ChapterBar />

          {/* 展示区（~60%） */}
          <div className="flex-[3] flex flex-col overflow-hidden">
            <DisplayArea />
          </div>

          {/* 对话区（~40%） */}
          <div className="flex-[2] flex flex-col overflow-hidden border-t border-zinc-800">
            <ChatPanel />
          </div>
        </div>
      </div>

      {/* 心智面板 */}
      <ManualPanel open={manualOpen} onClose={() => setManualOpen(false)} />

      {/* 图谱面板 */}
      <GraphPanel open={graphOpen} onClose={() => setGraphOpen(false)} />

      {/* 设置面板 */}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* 资料面板 */}
      <MaterialPanel open={materialOpen} onClose={() => setMaterialOpen(false)} />
    </div>
  );
}
