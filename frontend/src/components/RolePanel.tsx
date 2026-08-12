import { useState } from "react";
import PanelHeader from "./ui/PanelHeader";
import { useRoleStore } from "../stores/roleStore";
import { useApproval } from "./approval/ApprovalContext";

interface RolePanelProps {
  open: boolean;
  onClose: () => void;
  embedded?: boolean;
}

// S48-P4 角色推演：角色卡 + 场景 → N 路隔离推演 → 判别选优
export default function RolePanel({ open, onClose, embedded = false }: RolePanelProps) {
  const { requestApproval } = useApproval()
  const candidates = useRoleStore((s) => s.candidates);
  const best = useRoleStore((s) => s.best);
  const scoreReason = useRoleStore((s) => s.scoreReason);
  const loading = useRoleStore((s) => s.loading);
  const error = useRoleStore((s) => s.error);
  const runPlay = useRoleStore((s) => s.runPlay);
  const saveCard = useRoleStore((s) => s.saveCard);

  const [tab, setTab] = useState<"card" | "play">("play");
  const [cardName, setCardName] = useState("");
  const [cardContent, setCardContent] = useState("");
  const [cardMsg, setCardMsg] = useState("");
  const [role, setRole] = useState("");
  const [scenario, setScenario] = useState("");
  const [n, setN] = useState(4);

  if (!open) return null;

  const handleSaveCard = async () => {
    if (!cardName.trim() || !cardContent.trim()) return;
    setCardMsg("");
    try {
      await saveCard(cardName.trim(), cardContent.trim());
      setCardMsg(`角色卡已保存：${cardName.trim()}`);
      setRole(cardName.trim());
    } catch (e) {
      setCardMsg(`保存失败：${e}`);
    }
  };

  const handlePlay = async () => {
    if (!role.trim() || !scenario.trim()) return;
    // 高负载：N 路隔离推演（LLM 多路约 18s）→ 先审批
    const ok = await requestApproval({
      title: '角色推演',
      desc: `${role.trim()} 在「${scenario.trim().slice(0, 30)}…」场景下 ${n} 路推演选优，约 18 秒。`, 
      estSeconds: 18,
      cost: 'high',
    })
    if (ok) await runPlay(role.trim(), scenario.trim(), n);
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
          icon="user"
          iconClass="text-sky-400"
          title="角色推演"
          desc="低成本多探索 + 判别选优"
          actions={
            <div className="flex items-center gap-2">
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          </div>
          }
        />

        {/* Tab 切换 */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800">
          {(
            [
              ["play", "推演"],
              ["card", "角色卡"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`text-xs px-2 py-1 rounded ${
                tab === k
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {tab === "play" ? (
            <>
              {/* 推演输入 */}
              <div className="space-y-2">
                <input
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="角色名（须已有角色卡或图谱实体）"
                  className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                />
                <textarea
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                  placeholder="推演场景（自然语言）..."
                  rows={3}
                  className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
                />
                <div className="flex items-center gap-2">
                  <label className="text-xs text-zinc-500">路数</label>
                  <select
                    value={n}
                    onChange={(e) => setN(Number(e.target.value))}
                    className="bg-zinc-800 text-zinc-300 text-xs px-2 py-1 rounded border border-zinc-700"
                  >
                    {[2, 3, 4, 5, 6].map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handlePlay}
                    disabled={loading || !role.trim() || !scenario.trim()}
                    className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded ml-auto"
                  >
                    {loading ? "推演中..." : "开始推演"}
                  </button>
                </div>
              </div>

              {error && <p className="text-xs text-red-400">{error}</p>}

              {/* 结果 */}
              {!loading && candidates.length > 0 && (
                <div className="space-y-3">
                  {best && (
                    <div className="bg-emerald-900/30 border border-emerald-600/40 rounded-lg p-3 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          最佳
                        </span>
                        <span className="text-xs font-medium text-emerald-300">
                          {best.strategy}
                        </span>
                      </div>
                      <p className="text-sm text-zinc-200 whitespace-pre-wrap">{best.text}</p>
                    </div>
                  )}
                  {scoreReason && (
                    <p className="text-xs text-zinc-500 whitespace-pre-wrap">
                      选优理由：{scoreReason}
                    </p>
                  )}
                  {candidates.map((c, i) => (
                    <div
                      key={i}
                      className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3 space-y-1"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-400">
                          候选 {i + 1}
                        </span>
                        {c.strategy && (
                          <span className="text-xs text-zinc-400">{c.strategy}</span>
                        )}
                      </div>
                      {c.text && (
                        <p className="text-sm text-zinc-300 whitespace-pre-wrap">{c.text}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {!loading && candidates.length === 0 && !error && (
                <p className="text-zinc-600 text-sm text-center py-4">
                  输入角色与场景，开始多路推演
                </p>
              )}
            </>
          ) : (
            <>
              {/* 角色卡编辑 */}
              <div className="space-y-2">
                <input
                  value={cardName}
                  onChange={(e) => setCardName(e.target.value)}
                  placeholder="角色名"
                  className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500"
                />
                <textarea
                  value={cardContent}
                  onChange={(e) => setCardContent(e.target.value)}
                  placeholder="角色卡内容（性格/目标/背景/口头禅...）"
                  rows={10}
                  className="w-full bg-zinc-800 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
                />
                <button
                  onClick={handleSaveCard}
                  disabled={!cardName.trim() || !cardContent.trim()}
                  className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded"
                >
                  保存角色卡
                </button>
                {cardMsg && <p className="text-xs text-zinc-400">{cardMsg}</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
