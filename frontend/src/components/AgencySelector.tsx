import { useState, useEffect } from "react";
import { getAgency, setAgency, type AgencyLevel } from "../api/agency";

export default function AgencySelector() {
  const [levels, setLevels] = useState<AgencyLevel[]>([]);
  const [currentId, setCurrentId] = useState<string>("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    getAgency()
      .then((data) => {
        setLevels(data.levels.sort((a, b) => a.order - b.order));
        setCurrentId(data.current.level_id);
      })
      .catch(console.error);
  }, []);

  const handleSelect = async (levelId: string) => {
    try {
      const updated = await setAgency(levelId);
      setCurrentId(updated.level_id);
      setOpen(false);
    } catch (e) {
      console.error("Failed to set agency:", e);
    }
  };

  const currentLevel = levels.find((l) => l.level_id === currentId);

  return (
    <div className="relative">
      {/* 档位圆点组 */}
      <div className="flex items-center gap-1.5">
        {levels.map((level) => (
          <button
            key={level.level_id}
            onClick={() => handleSelect(level.level_id)}
            onMouseEnter={() => setHoveredId(level.level_id)}
            onMouseLeave={() => setHoveredId(null)}
            className={`w-3 h-3 rounded-full transition-all ${
              level.level_id === currentId
                ? "bg-amber-400 ring-2 ring-amber-400/30"
                : "bg-zinc-600 hover:bg-zinc-500"
            }`}
            title={level.name}
          />
        ))}
      </div>

      {/* Hover 提示 */}
      {hoveredId && (
        <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 z-50 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 whitespace-nowrap pointer-events-none">
          <p className="text-xs text-zinc-200 font-medium">
            {levels.find((l) => l.level_id === hoveredId)?.name}
          </p>
          <p className="text-[10px] text-zinc-500">
            {levels.find((l) => l.level_id === hoveredId)?.description}
          </p>
        </div>
      )}
    </div>
  );
}
