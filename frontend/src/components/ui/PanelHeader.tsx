import type { ReactNode } from "react";
import Icon from "./Icon";

/**
 * 统一渐变横幅头部（S106 美术统一）：
 * 深底 + 品牌色光晕 + 渐变标题图标 + 描述 + 操作区。
 * 页面型（maxW）与面板型（紧凑）两种尺寸。
 */
export default function PanelHeader({
  icon,
  iconClass = "text-violet-400",
  title,
  desc,
  actions,
  compact = false,
  maxW = true,
}: {
  icon?: string;
  iconClass?: string;
  title: ReactNode;
  desc?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  maxW?: boolean;
}) {
  const inner = compact ? "px-4 py-3.5" : "px-6 py-6";
  return (
    <div className="relative overflow-hidden border-b border-zinc-800 bg-zinc-950 shrink-0">
      <div className="absolute -top-24 left-1/4 w-72 h-72 rounded-full bg-violet-600/10 blur-3xl pointer-events-none" />
      <div className="absolute -top-16 right-1/4 w-60 h-60 rounded-full bg-sky-600/10 blur-3xl pointer-events-none" />
      <div className={`relative ${maxW ? "max-w-6xl mx-auto" : ""} ${inner} flex items-center justify-between gap-4 flex-wrap`}>
        <div className="min-w-0">
          <h1 className={`${compact ? "text-base" : "text-2xl"} font-bold tracking-tight flex items-center gap-2.5`}>
            {icon && (
              <span className={iconClass}>
                <Icon name={icon} size={compact ? 17 : 24} />
              </span>
            )}
            <span className="truncate">{title}</span>
          </h1>
          {desc && <p className={`text-zinc-500 mt-1 ${compact ? "text-xs" : "text-sm"}`}>{desc}</p>}
        </div>
        {actions && <div className="flex gap-2 items-center shrink-0">{actions}</div>}
      </div>
    </div>
  );
}
