import { useDisplayStore, type DisplayMode } from "../stores/displayStore";
import Paper from "./Paper";
import SkillPanel from "./SkillPanel";
import { useState } from "react";

interface DisplayAreaProps {
  onManualClick?: () => void;
  onGraphClick?: () => void;
  onMaterialClick?: () => void;
  manualOpen?: boolean;
  graphOpen?: boolean;
  materialOpen?: boolean;
}

const MODE_LABELS: Record<DisplayMode, string> = {
  paper: "稿纸",
  tree: "叙事树",
  skills: "技巧",
  check: "审读",
  explore: "探索",
};

export default function DisplayArea({
  onManualClick,
  onGraphClick,
  onMaterialClick,
  manualOpen,
  graphOpen,
  materialOpen,
}: DisplayAreaProps = {}) {
  const mode = useDisplayStore((s) => s.mode);
  const setMode = useDisplayStore((s) => s.setMode);
  const [skillOpen, setSkillOpen] = useState(false);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 展示区工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-1 shrink-0">
        {/* 左侧：模式切换 */}
        <div className="flex items-center gap-1">
          {(Object.keys(MODE_LABELS) as DisplayMode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                if (m === "skills") {
                  setSkillOpen(!skillOpen);
                } else {
                  setMode(m);
                  setSkillOpen(false);
                }
              }}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                (m === "skills" && skillOpen) || (m !== "skills" && mode === m)
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
              }`}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>

        {/* 右侧：面板唤起 */}
        <div className="ml-auto flex items-center gap-1">
          {onManualClick && (
            <button
              onClick={onManualClick}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                manualOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              心智
            </button>
          )}
          {onGraphClick && (
            <button
              onClick={onGraphClick}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                graphOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              图谱
            </button>
          )}
          {onMaterialClick && (
            <button
              onClick={onMaterialClick}
              className={`text-[11px] px-2 py-0.5 rounded transition-colors ${
                materialOpen
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              资料
            </button>
          )}
        </div>
      </div>

      {/* 展示内容 */}
      <div className="flex-1 overflow-hidden">
        {mode === "paper" && !skillOpen && <Paper />}
        {mode === "skills" || (mode === "paper" && skillOpen) ? (
          <SkillPanel open={true} onClose={() => setSkillOpen(false)} embedded />
        ) : null}
        {mode === "tree" && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-zinc-600">叙事树视图（待实现）</p>
          </div>
        )}
        {mode === "check" && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-zinc-600">审读报告（待实现）</p>
          </div>
        )}
        {mode === "explore" && (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-zinc-600">探索视图（待实现）</p>
          </div>
        )}
      </div>
    </div>
  );
}
