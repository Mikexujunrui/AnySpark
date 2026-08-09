import { useEffect, useState } from "react";
import ChapterSidebar from "./ChapterSidebar";
import Paper from "./Paper";
import ChatPanel from "./ChatPanel";
import ModelPicker from "./ModelPicker";
import ManualPanel from "./ManualPanel";
import SkillPanel from "./SkillPanel";
import GraphPanel from "./GraphPanel";
import { useModelStore } from "../stores/modelStore";

export default function Layout() {
  const fetchModels = useModelStore((s) => s.fetchModels);
  const [manualOpen, setManualOpen] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);

  // 初始化加载模型列表
  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      {/* 顶栏 */}
      <header className="h-12 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between px-4 shrink-0">
        <h1 className="text-sm font-medium text-zinc-300 tracking-wide">
          AnySpark v4
        </h1>
        {/* 右侧控件 */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setManualOpen(!manualOpen)}
            className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
              manualOpen
                ? "bg-zinc-700 text-zinc-200"
                : "bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
            }`}
          >
            心智
          </button>
          <button
            onClick={() => setSkillOpen(!skillOpen)}
            className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
              skillOpen
                ? "bg-zinc-700 text-zinc-200"
                : "bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
            }`}
          >
            技巧
          </button>
          <button
            onClick={() => setGraphOpen(!graphOpen)}
            className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
              graphOpen
                ? "bg-zinc-700 text-zinc-200"
                : "bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
            }`}
          >
            图谱
          </button>
          <ModelPicker />
        </div>
      </header>

      {/* 主体 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧章节栏 */}
        <ChapterSidebar />

        {/* 右侧：稿纸 + 对话 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 稿纸 */}
          <Paper />

          {/* 对话面板 */}
          <ChatPanel />
        </div>
      </div>

      {/* 心智面板 */}
      <ManualPanel open={manualOpen} onClose={() => setManualOpen(false)} />

      {/* 技巧面板 */}
      <SkillPanel open={skillOpen} onClose={() => setSkillOpen(false)} />

      {/* 图谱面板 */}
      <GraphPanel open={graphOpen} onClose={() => setGraphOpen(false)} />
    </div>
  );
}
