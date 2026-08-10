import { useCheckStore } from "../stores/checkStore";
import type { CheckFinding } from "../api/check";

// severity 排序权重
const SEVERITY_ORDER: Record<CheckFinding["severity"], number> = {
  hard: 0,
  soft: 1,
  info: 2,
};

// severity 样式
const SEVERITY_STYLES: Record<CheckFinding["severity"], { bg: string; text: string; label: string }> = {
  hard: { bg: "bg-red-900/30", text: "text-red-400", label: "严重" },
  soft: { bg: "bg-amber-900/30", text: "text-amber-400", label: "警告" },
  info: { bg: "bg-blue-900/30", text: "text-blue-400", label: "提示" },
};

export default function CheckReport() {
  const { report, loading, error, runCheck, clearReport } = useCheckStore();

  const handleRunCheck = () => {
    runCheck();
  };

  // 初始状态：无报告
  if (!report && !loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        <p className="text-sm text-zinc-500 mb-4">审读当前章节</p>
        <button
          onClick={handleRunCheck}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm rounded-lg border border-zinc-700 transition-colors"
        >
          开始审读
        </button>
        {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
      </div>
    );
  }

  // 加载中
  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        <div className="w-8 h-8 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mb-4" />
        <p className="text-sm text-zinc-500">审读中...</p>
      </div>
    );
  }

  // 错误状态
  if (error && !report) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        <p className="text-sm text-red-400 mb-4">{error}</p>
        <button
          onClick={handleRunCheck}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm rounded-lg border border-zinc-700 transition-colors"
        >
          重试
        </button>
      </div>
    );
  }

  if (!report) return null;

  // 按 severity 排序 findings
  const sortedFindings = [...report.findings].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 报告头部 */}
      <div className="border-b border-zinc-800 bg-zinc-900/30 px-4 py-3 shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-zinc-200">审读报告</h3>
            <p className="text-xs text-zinc-500 mt-0.5">目标：{report.target}</p>
          </div>
          <div className="flex items-center gap-3">
            {report.hard_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-400">
                {report.hard_count} 严重问题
              </span>
            )}
            <button
              onClick={handleRunCheck}
              className="text-xs px-2 py-1 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              重新审读
            </button>
            <button
              onClick={clearReport}
              className="text-xs px-2 py-1 text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      </div>

      {/* 报告内容 */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Findings 列表 */}
        {sortedFindings.length > 0 ? (
          <div className="space-y-2">
            <h4 className="text-xs text-zinc-500 uppercase tracking-wide">发现项</h4>
            {sortedFindings.map((finding, i) => (
              <FindingCard key={i} finding={finding} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-sm text-emerald-400">未发现明显问题</p>
            <p className="text-xs text-zinc-600 mt-1">章节内容通过了所有检测</p>
          </div>
        )}

        {/* 图谱证据 */}
        {report.graph_evidence && (
          <div className="space-y-2">
            <h4 className="text-xs text-zinc-500 uppercase tracking-wide">图谱证据</h4>
            <div className="bg-zinc-900/50 rounded-lg p-3 border border-zinc-800">
              <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-mono">
                {report.graph_evidence}
              </pre>
            </div>
          </div>
        )}

        {/* 时序警告 */}
        {report.temporal_warnings.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs text-zinc-500 uppercase tracking-wide">时序警告</h4>
            <div className="space-y-1">
              {report.temporal_warnings.map((warning, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-xs px-3 py-2 bg-amber-900/20 border border-amber-900/30 rounded"
                >
                  <span className="text-amber-400">⚠</span>
                  <span className="text-amber-200">{warning}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// 单个发现项卡片
function FindingCard({ finding }: { finding: CheckFinding }) {
  const style = SEVERITY_STYLES[finding.severity];

  return (
    <div className={`rounded-lg border ${style.bg} border-zinc-800 p-3`}>
      <div className="flex items-start gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.bg} ${style.text} border border-current/20 shrink-0`}>
          {style.label}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 shrink-0">
          {finding.category}
        </span>
      </div>
      <p className="text-sm text-zinc-200 mt-2">{finding.message}</p>
      {finding.evidence && (
        <div className="mt-2 pt-2 border-t border-zinc-800/50">
          <p className="text-xs text-zinc-500">证据</p>
          <p className="text-xs text-zinc-400 mt-0.5">{finding.evidence}</p>
        </div>
      )}
      {finding.suggestion && (
        <div className="mt-2">
          <p className="text-xs text-zinc-500">建议</p>
          <p className="text-xs text-emerald-400/80 mt-0.5">{finding.suggestion}</p>
        </div>
      )}
      <p className="text-[10px] text-zinc-600 mt-2">来源：{finding.source}</p>
    </div>
  );
}
