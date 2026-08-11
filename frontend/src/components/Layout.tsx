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
import ChapterWrapup from "./ChapterWrapup";
import BriefPanel from "./BriefPanel";
import BiasPanel from "./BiasPanel";
import BatchPanel from "./BatchPanel";
import UploadPanel from "./UploadPanel";
import TemplatePanel from "./TemplatePanel";
import ImpactPanel from "./ImpactPanel";
import ToolsPanel from "./ToolsPanel";
import PlayPanel from "./PlayPanel";
import RolePanel from "./RolePanel";
import ReviewPanel from "./ReviewPanel";
import DimsPanel from "./DimsPanel";
import { useModelStore } from "../stores/modelStore";
import { useChatStore } from "../stores/chatStore";

// 工具坞：快速面板（盖层，点击打开对应面板）
const TOOL_PANELS: { key: string; label: string; desc: string }[] = [
  { key: "brief", label: "项目简介", desc: "项目总览，可 AI 生成草案" },
  { key: "bias", label: "AI 倾向", desc: "双向黑盒：看 AI 的自述倾向" },
  { key: "batch", label: "批量操作", desc: "多章统一改写/审读" },
  { key: "upload", label: "上传消化", desc: "上传文件 → 拆章/摘要卡" },
  { key: "templates", label: "模板库", desc: "探索方向模式库，可导入" },
  { key: "impact", label: "影响分析", desc: "改一章 → 受影响下游" },
  { key: "tools", label: "扩展工具", desc: "P5 注册表，人工批准生效" },
  { key: "play", label: "互动推演", desc: "扮演角色多轮选择推进" },
  { key: "role", label: "角色推演", desc: "角色卡 + N 路选优" },
  { key: "review", label: "评审团", desc: "拟人评审员多视角审" },
  { key: "dims", label: "探索维度", desc: "探索维度增删改" },
];

export default function Layout() {
  const fetchModels = useModelStore((s) => s.fetchModels);
  const loadLatestConversation = useChatStore((s) => s.loadLatestConversation);

  const [convListOpen, setConvListOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [materialOpen, setMaterialOpen] = useState(false);
  const [wrapupOpen, setWrapupOpen] = useState(false);
  const [toolsDropdown, setToolsDropdown] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);

  const closeActiveTool = () => setActiveTool(null);
  const openTool = (key: string) => {
    setActiveTool(key);
    setToolsDropdown(false);
  };

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
          {/* 工具坞 */}
          <div className="relative">
            <button
              onClick={() => setToolsDropdown(!toolsDropdown)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${toolsDropdown ? "bg-zinc-700 text-zinc-200" : "text-zinc-400 hover:text-zinc-200"}`}
            >
              工具 ▾
            </button>
            {toolsDropdown && (
              <div className="absolute right-0 top-full mt-1 w-52 bg-zinc-800 border border-zinc-700 rounded shadow-lg z-40 overflow-hidden">
                {TOOL_PANELS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => openTool(t.key)}
                    className="w-full px-3 py-2 text-left hover:bg-zinc-700 transition-colors"
                  >
                    <div className="text-xs text-zinc-200">{t.label}</div>
                    <div className="text-[10px] text-zinc-500">{t.desc}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
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
            <DisplayArea
              onManualClick={() => setManualOpen(!manualOpen)}
              onGraphClick={() => setGraphOpen(!graphOpen)}
              onMaterialClick={() => setMaterialOpen(!materialOpen)}
              onWrapupClick={() => setWrapupOpen(!wrapupOpen)}
              manualOpen={manualOpen}
              graphOpen={graphOpen}
              materialOpen={materialOpen}
            />
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

      {/* 一章收尾 */}
      <ChapterWrapup open={wrapupOpen} onClose={() => setWrapupOpen(false)} />

      {/* 工具坞面板 */}
      <BriefPanel open={activeTool === "brief"} onClose={closeActiveTool} />
      <BiasPanel open={activeTool === "bias"} onClose={closeActiveTool} />
      <BatchPanel open={activeTool === "batch"} onClose={closeActiveTool} />
      <UploadPanel open={activeTool === "upload"} onClose={closeActiveTool} />
      <TemplatePanel open={activeTool === "templates"} onClose={closeActiveTool} />
      <ImpactPanel open={activeTool === "impact"} onClose={closeActiveTool} />
      <ToolsPanel open={activeTool === "tools"} onClose={closeActiveTool} />
      <PlayPanel open={activeTool === "play"} onClose={closeActiveTool} />
      <RolePanel open={activeTool === "role"} onClose={closeActiveTool} />
      <ReviewPanel open={activeTool === "review"} onClose={closeActiveTool} />
      <DimsPanel open={activeTool === "dims"} onClose={closeActiveTool} />
    </div>
  );
}
