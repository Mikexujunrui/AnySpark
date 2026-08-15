// S100：token 成本估算（按模型定价，仅估算——价格可能变动，见 DeepSeek 官方定价页）
// 2026-08 非高峰价（¥/百万 token，缓存未命中）：V4-Pro 输入 3 / 输出 6；V4-Flash 输入 1 / 输出 2。
// 高峰时段（工作日 9-12/14-18）翻倍；缓存命中远便宜——此处用未命中价，估算偏保守（偏高）。

export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

const PRICING: Record<string, { in: number; out: number }> = {
  'deepseek-v4-pro': { in: 3, out: 6 },
  'deepseek-v4-flash': { in: 1, out: 2 },
}
const DEFAULT_PRICING = { in: 3, out: 6 }

/** 按模型名取单价（未命中价，¥/百万 token）。未知模型回退 pro 价。 */
export function pricingFor(model: string | undefined): { in: number; out: number } {
  if (!model) return DEFAULT_PRICING
  const lower = model.toLowerCase()
  for (const [key, price] of Object.entries(PRICING)) {
    if (lower.includes(key)) return price
  }
  return DEFAULT_PRICING
}

/** 估算一次/累计消耗的成本（元）。 */
export function estimateCost(model: string | undefined, usage: TokenUsage | undefined): number {
  if (!usage) return 0
  const p = pricingFor(model)
  return ((usage.prompt_tokens || 0) * p.in + (usage.completion_tokens || 0) * p.out) / 1_000_000
}

export function formatCost(yuan: number): string {
  if (yuan <= 0) return '¥0'
  if (yuan < 0.01) return `¥${(yuan * 100).toFixed(1)}分`
  return `≈¥${yuan.toFixed(3)}`
}

export function formatTokens(n: number | undefined): string {
  if (!n) return '0'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}
