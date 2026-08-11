import { useState, useRef, useEffect } from "react";
import { useModelStore } from "../stores/modelStore";

export default function ModelPicker() {
  const models = useModelStore((s) => s.models);
  const activeModel = useModelStore((s) => s.activeModel);
  const switchModel = useModelStore((s) => s.switchModel);
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleSelect = async (id: string) => {
    await switchModel(id);
    setOpen(false);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-300 transition-colors"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
        <span className="max-w-[120px] truncate">
          {activeModel?.name || "未选择模型"}
        </span>
        <svg className="w-3 h-3 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* 下拉菜单 */}
      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 bg-zinc-800 border border-zinc-700 rounded-md shadow-lg z-50">
          <div className="py-1 max-h-64 overflow-y-auto">
            {models.length === 0 ? (
              <div className="px-3 py-2 text-xs text-zinc-500">暂无模型</div>
            ) : (
              models.map((model) => (
                <button
                  key={model.id}
                  onClick={() => handleSelect(model.id)}
                  className={`w-full text-left px-3 py-2 text-xs hover:bg-zinc-700 transition-colors ${
                    model.is_active ? "text-green-400" : "text-zinc-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{model.name}</span>
                    {model.is_active && (
                      <svg className="w-3 h-3 ml-2 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    )}
                  </div>
                  <div className="text-zinc-500 text-[10px] mt-0.5 truncate">
                    {model.model}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
