// workflowParse — 批量任务结果/历史消息的纯解析函数（S147 修复逻辑抽离，可单测）
// 从组件内联逻辑抽出：BatchPanel 的 loop items 解析 / 旧任务 fallback、
// ChatPanel 的历史消息过滤与陈旧状态纠正。纯函数零依赖，vitest 直测。

export interface LoopItem {
  iter?: number
  [nodeId: string]: string | number | undefined
}

export type LoopItemText = Record<string, string>

export interface TaskDetailLike {
  node_states?: { node_id?: string; output?: string | null }[]
  results?: Record<string, unknown>
}

// S145b：从任务详情提取 loop 迭代明细（每章审读/改写输出）
export function parseLoopItems(task: TaskDetailLike): LoopItemText[] {
  return _parseLoopItems(task).map((it) => {
    const out: LoopItemText = {}
    for (const [k, v] of Object.entries(it)) out[k] = String(v)
    return out
  })
}

function _parseLoopItems(task: TaskDetailLike): LoopItem[] {
  const loop = (task.node_states ?? []).find((s) => s.node_id === "loop")
  if (!loop?.output) return []
  try {
    const parsed = JSON.parse(loop.output) as { items?: unknown }
    return Array.isArray(parsed.items) ? (parsed.items as LoopItem[]) : []
  } catch {
    return []
  }
}

// S147b：旧引擎任务 fallback——loop 无 items 时从顶层 results 提取可展示输出
export function extractFallbackResult(
  results: Record<string, unknown> | null | undefined
): { key: string; text: string } | null {
  if (!results) return null
  const keys = ["review_report", "review", "report", "rewritten", "fixed", "saved"]
  for (const k of keys) {
    const v = results[k]
    if (v != null && String(v).trim()) return { key: k, text: String(v) }
  }
  return null
}

export interface HistoryMsg {
  role: string
  text: string
  [k: string]: unknown
}

// S107b+S145b：历史消息规范化——content→text 映射、过滤空文本消息
// （后端消息 role 为 assistant，前端渲染 role 为 agent——两者都算 AI 消息）
export function normalizeHistoryMessages(raw: unknown[]): HistoryMsg[] {
  return (raw ?? [])
    .map((m) => ({ ...(m as HistoryMsg), text: ((m as HistoryMsg).content ?? (m as HistoryMsg).text ?? "") as string }))
    .filter((m) => {
      const isAi = m.role === "agent" || m.role === "assistant"
      return !isAi || (m.text && m.text.trim().length > 0)
    })
}

// S145b：纠正陈旧的"[批量X执行中]"历史快照（轮询中断残留 → 任务实际已结束）
export function correctStaleBatchMessages(messages: HistoryMsg[]): HistoryMsg[] {
  return messages.map((m) => {
    const t = String(m.text || "")
    const isAi = m.role === "agent" || m.role === "assistant"
    if (isAi && /^\[批量(改写|审读)执行中\]/.test(t)) {
      return {
        ...m,
        text: t.replace(/^\[批量(改写|审读)执行中\]/, "[批量$1任务已结束（详情见批量面板）]"),
      }
    }
    return m
  })
}
