import { useEffect, useState } from "react";
import { useExploreStore } from "../stores/exploreStore";
import type { DirectionCard } from "../api/explore";
import { explorePath, type PathCandidate } from "../api/explore";
import { useApproval } from "./approval/ApprovalContext";

export default function ExploreView({ bookId = "main" }: { bookId?: string }) {
  const { requestApproval } = useApproval()
  const [pathMode, setPathMode] = useState(false);
  const {
    phase,
    seed,
    intent,
    cards,
    archived,
    loading,
    error,
    setSeed,
    submitSeed,
    confirmIntent,
    archiveCard,
    fetchArchived,
    reset,
  } = useExploreStore();

  // 初始加载已固化方向（S152：按当前项目）
  useEffect(() => {
    fetchArchived(bookId);
  }, [bookId, fetchArchived]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 工具条 */}
      <div className="h-8 bg-zinc-900/50 border-b border-zinc-800/50 flex items-center px-3 gap-2 shrink-0">
        <button
          onClick={() => { if (pathMode) reset(); setPathMode(false); }}
          className="text-[11px] px-2 py-0.5 rounded text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          新探索
        </button>
        <button
          onClick={() => setPathMode(!pathMode)}
          className={`text-[11px] px-2 py-0.5 rounded transition-colors ${pathMode ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}
        >
          路径探索
        </button>
        <span className="text-[11px] text-zinc-600">|</span>
        <span className="text-[11px] text-zinc-500">
          阶段：{phase === "seed" && "种子输入"}
          {phase === "intent" && "意图理解"}
          {phase === "cards" && "方向选择"}
          {phase === "archived" && "已固化"}
        </span>
        {loading && (
          <span className="text-[11px] text-amber-400 ml-auto">处理中...</span>
        )}
      </div>

      {/* 主内容区 */}
      <div className="flex-1 overflow-auto p-4">
        {pathMode ? (
          <PathExplore bookId={bookId} />
        ) : (
        <>
        {/* 阶段 1：种子输入 */}
        {phase === "seed" && (
          <div className="max-w-lg mx-auto">
            <h3 className="text-sm font-medium text-zinc-200 mb-2">探索新方向</h3>
            <p className="text-xs text-zinc-500 mb-4">
              输入一个种子（故事概念、情节方向、角色发展等），AI 将理解意图并生成多个探索方向。
            </p>
            <textarea
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="例如：主角在废墟中发现一本日记，记载着他从未经历过的记忆..."
              rows={4}
              className="w-full bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded-lg border border-zinc-700 focus:outline-none focus:border-zinc-500 resize-none"
            />
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={async () => {
                  // 高负载：AI 理解意图（LLM 约 8s）→ 审批
                  const ok = await requestApproval({
                    title: '探索意图理解',
                    desc: 'AI 分析种子并生成方向候选，约 8 秒。',
                    estSeconds: 8,
                    cost: 'medium',
                  })
                  if (ok) submitSeed()
                }}
                disabled={!seed.trim() || loading}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 text-sm rounded-lg transition-colors"
              >
                理解意图
              </button>
              {error && <span className="text-xs text-red-400">{error}</span>}
            </div>
          </div>
        )}

        {/* 阶段 2：意图理解 */}
        {phase === "intent" && intent && (
          <div className="max-w-lg mx-auto">
            <h3 className="text-sm font-medium text-zinc-200 mb-2">意图理解</h3>
            <p className="text-xs text-zinc-500 mb-4">
              AI 对种子的理解如下，确认后生成方向卡。
            </p>
            
            {/* 种子分析 */}
            {intent.concept?.core && (
              <div className="mb-4 p-3 bg-zinc-900/50 rounded-lg border border-zinc-800">
                <p className="text-xs text-zinc-500 mb-1">种子分析</p>
                <p className="text-sm text-zinc-300">{intent.concept.core}</p>
              </div>
            )}

            {/* 概念标签 */}
            <div className="mb-4">
              {intent.concept?.genre && intent.concept.genre !== "待定" && (
                <div className="mb-3">
                  <p className="text-xs text-zinc-500 mb-2">类型</p>
                  <span className="text-xs px-2 py-1 bg-emerald-900/30 text-emerald-400 rounded border border-emerald-900/50">
                    {intent.concept.genre}
                  </span>
                </div>
              )}
              {intent.concept?.mood && intent.concept.mood !== "待定" && (
                <div className="mb-3">
                  <p className="text-xs text-zinc-500 mb-2">情绪</p>
                  <span className="text-xs px-2 py-1 bg-blue-900/30 text-blue-400 rounded border border-blue-900/50">
                    {intent.concept.mood}
                  </span>
                </div>
              )}
              {intent.concept?.seed_position && intent.concept.seed_position !== "未知" && (
                <div className="mb-3">
                  <p className="text-xs text-zinc-500 mb-2">种子位置</p>
                  <span className="text-xs px-2 py-1 bg-purple-900/30 text-purple-400 rounded border border-purple-900/50">
                    {intent.concept.seed_position}
                  </span>
                </div>
              )}
            </div>

            {/* AI 追问 */}
            {intent.questions && intent.questions.length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-zinc-500 mb-2">AI 追问</p>
                <div className="space-y-1">
                  {intent.questions.map((q, i) => (
                    <p key={i} className="text-xs text-amber-400/80">
                      • {q}
                    </p>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2 mt-4">
              <button
                onClick={async () => {
                  const ok = await requestApproval({
                    title: '生成方向卡',
                    desc: 'AI 基于确认的意图生成 4 个方向候选，约 10 秒。',
                    estSeconds: 10,
                    cost: 'medium',
                  })
                  if (ok) confirmIntent()
                }}
                disabled={loading}
                className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 text-sm rounded-lg transition-colors"
              >
                确认，生成方向卡
              </button>
              <button
                onClick={reset}
                className="px-4 py-2 text-zinc-500 hover:text-zinc-300 text-sm transition-colors"
              >
                重新输入
              </button>
              {error && <span className="text-xs text-red-400">{error}</span>}
            </div>
          </div>
        )}

        {/* 阶段 3：方向选择 */}
        {phase === "cards" && cards.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-zinc-200 mb-2">选择方向</h3>
            <p className="text-xs text-zinc-500 mb-4">
              点击选择一张方向卡，将固化到叙事树中成为主线节点。
            </p>
            <div className="grid grid-cols-2 gap-3">
              {cards.map((card) => (
                <DirectionCardView
                  key={card.id}
                  card={card}
                  onSelect={() => archiveCard(card, bookId)}
                  loading={loading}
                />
              ))}
            </div>
            {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
          </div>
        )}

        {/* 阶段 4：已固化 */}
        {phase === "archived" && (
          <div>
            <h3 className="text-sm font-medium text-emerald-400 mb-2">方向已固化</h3>
            <p className="text-xs text-zinc-500 mb-4">
              选中的方向已写入叙事树。可以继续探索新方向。
            </p>
            <button
              onClick={reset}
              className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm rounded-lg transition-colors"
            >
              新探索
            </button>
          </div>
        )}

        {/* 已固化历史列表 */}
        {archived.length > 0 && (
          <div className="mt-8 pt-6 border-t border-zinc-800">
            <h4 className="text-xs text-zinc-500 uppercase tracking-wide mb-3">
              历史探索方向（{archived.length}）
            </h4>
            <div className="space-y-2">
              {archived.map((a) => (
                <div
                  key={a.id}
                  className="p-3 bg-zinc-900/30 rounded-lg border border-zinc-800"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm text-zinc-200">{a.title}</p>
                      <p className="text-xs text-zinc-500 mt-0.5">{a.summary.slice(0, 80)}...</p>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 bg-zinc-800 text-zinc-500 rounded">
                      {a.dimension}
                    </span>
                  </div>
                  <p className="text-[10px] text-zinc-600 mt-2">
                    {new Date(a.created_at).toLocaleDateString()}
                    {a.story_node_id && " · 已关联叙事树"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}

// S67 路径探索组件：起点 A → 终点 B 的串联路径候选
function PathExplore({ bookId }: { bookId: string }) {
  const [fromDesc, setFromDesc] = useState("");
  const [toDesc, setToDesc] = useState("");
  const [constraints, setConstraints] = useState("");
  const [paths, setPaths] = useState<PathCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!toDesc.trim()) {
      setError("请输入终点描述");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await explorePath({
        from_desc: fromDesc.trim(),
        to_desc: toDesc.trim(),
        constraints: constraints
          .split(/[\n,，]/)
          .map((c) => c.trim())
          .filter(Boolean),
        n: 4,
        book_id: bookId, // S152：项目隔离（落树按当前项目）
      });
      setPaths(res.paths || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h3 className="text-sm font-medium text-zinc-200 mb-2">路径探索</h3>
      <p className="text-xs text-zinc-500 mb-4">
        起点 A → 终点 B 的串联路径候选（叙事树节点之间的桥梁）。
      </p>
      <div className="space-y-3">
        <textarea
          value={fromDesc}
          onChange={(e) => setFromDesc(e.target.value)}
          placeholder="起点描述（可为空）"
          rows={2}
          className="w-full bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none resize-none"
        />
        <textarea
          value={toDesc}
          onChange={(e) => setToDesc(e.target.value)}
          placeholder="终点描述（必填），例如：主角直面十年前的仇人"
          rows={2}
          className="w-full bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none resize-none"
        />
        <input
          value={constraints}
          onChange={(e) => setConstraints(e.target.value)}
          placeholder="补充设定约束（逗号分隔可选）"
          className="w-full bg-zinc-900 text-zinc-200 text-sm px-3 py-2 rounded border border-zinc-700 focus:outline-none"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={run}
            disabled={!toDesc.trim() || loading}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-200 text-sm rounded-lg transition-colors"
          >
            {loading ? "探索中..." : "探索路径"}
          </button>
          {error && <span className="text-xs text-red-400">{error}</span>}
        </div>

        {/* 结果 */}
        {paths.length > 0 && (
          <div className="mt-4 space-y-3">
            <h4 className="text-xs text-zinc-500 uppercase tracking-wide">
              候选路径（{paths.length}）
            </h4>
            {paths.map((p, i) => (
              <div key={i} className="p-3 bg-zinc-900/40 rounded-lg border border-zinc-800">
                <div className="text-[11px] text-zinc-400 mb-1">路径 {i + 1}</div>
                <div className="space-y-1">
                  {Array.isArray(p.events) &&
                    p.events.map((ev, j) => (
                      <p key={j} className="text-sm text-zinc-300 flex gap-2">
                        <span className="text-zinc-600">{j + 1}.</span>
                        {ev}
                      </p>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 方向卡组件
function DirectionCardView({
  card,
  onSelect,
  loading,
}: {
  card: DirectionCard;
  onSelect: () => void;
  loading: boolean;
}) {
  const sourceLabel = { template: "模板", grow: "生长", user: "用户" }[card.source];
  const sourceColor = {
    template: "text-blue-400 bg-blue-900/30",
    grow: "text-emerald-400 bg-emerald-900/30",
    user: "text-purple-400 bg-purple-900/30",
  }[card.source];

  return (
    <button
      onClick={onSelect}
      disabled={loading}
      className="text-left p-4 bg-zinc-900/50 hover:bg-zinc-800/50 disabled:opacity-50 rounded-lg border border-zinc-800 hover:border-zinc-600 transition-all group"
    >
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-sm font-medium text-zinc-200 group-hover:text-zinc-100">
          {card.title}
        </h4>
        <span className={`text-[9px] px-1.5 py-0.5 rounded ${sourceColor}`}>
          {sourceLabel}
        </span>
      </div>
      <p className="text-xs text-zinc-400 line-clamp-3">{card.summary}</p>
      {card.term && (
        <p className="text-[10px] text-amber-400/70 mt-2 font-mono">{card.term}</p>
      )}
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-zinc-800/50">
        <span className="text-[10px] text-zinc-600">{card.dimension}</span>
        <span className="text-[10px] text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity">
          点击选择 →
        </span>
      </div>
    </button>
  );
}
