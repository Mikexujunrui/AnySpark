"""anyspark.align.mindup — 心智模型更新端（S53c：补齐 S51 更新方式缺口）。

对应 DESIGN §12.18 心智模型横断决策的更新方式全景：
- #5 实时负例捕获：用户明确否定 → 雷区条目。**实现说明（S62 修正）**：负例信号
  原文由 signal_collector.negative 记录进 signals 表（不丢），"这句否定是否构成
  雷区、雷区是什么"是**内容判断** → 交给轮末提炼器（PreferenceExtractor 真实 LLM）
  与学习审查。曾用正则关键词 + 守卫补丁机械落条目（正则猜内容 + 模板外漏捕 +
  补丁式守卫"不要停"子串误吞），属"垃圾补丁"，已删除。
- #6 跨会话对账（Reconcile）：沉淀的偏好条目 vs 最近实际行为信号比对——
  发现"标了雷区却在用 / 标了偏好却没遵守" → 提示可能记反/需更新（纠偏）。LLM 判断。
- #7 会话内弱信号快照：试探/微调类语句留快照供轮末提炼参考。**实现说明（S62）**：
  弱信号与否同样是内容判断，原 8 关键词猜测已删除——试探语句作为 custom 信号
  原文进 signals 表，由提炼器 LLM 判定。

哲学：机制（比对流程/解析/落库）硬编码；内容（条目/比对结果）自然语言。
"""

from __future__ import annotations

import re

from .manual import ManualEntry
from .signals import Signal

# ---------------------------------------------------------------------------
# ⑥ 跨会话对账（Reconcile）
# ---------------------------------------------------------------------------

_RECONCILE_PROMPT = """你是心智模型的对账器。下面是用户已沉淀的偏好/雷区条目，
以及最近的实际操作信号。请检查哪些条目**与实际行为一致/冲突**：

冲突示例：条目说"雷区：不要破折号"，但最近用户操作里多次出现破折号相关修改。

要求：
1. 只标出**明显冲突**（条目 vs 行为相反）或**需要更新**的条目。
2. 每条输出一句自然语言说明。
3. 没有冲突就输出空数组。

输出（严格 JSON 数组）：
[{"entry": "原条目内容", "verdict": "冲突|需更新|一致", "note": "说明"}]

条目：
{entries}

最近信号：
{signals}
"""


def _reconcile_prompt(entries: list[ManualEntry], signals: list[Signal]) -> str:
    e = "\n".join(f"- [{s.category}] {s.content}" for s in entries[:20]) or "（无条目）"
    sig = "\n".join(f"- [{s.kind}] {s.content[:80]}" for s in signals[:20]) or "（无信号）"
    return _RECONCILE_PROMPT.replace("{entries}", e).replace("{signals}", sig)


def build_reconcile_prompt(entries: list[ManualEntry], signals: list[Signal]) -> str:
    """对账提示词（供 app 层用真实 LLM 调用，模型无关自然语言）。"""
    return _reconcile_prompt(entries, signals)


def parse_reconcile_result(raw: str) -> list[dict[str, str]]:
    """宽容解析对账结果 JSON（同提炼器解析风格）。"""
    import json

    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [
                {
                    "entry": str(x.get("entry", "")),
                    "verdict": str(x.get("verdict", "")),
                    "note": str(x.get("note", "")),
                }
                for x in data
                if isinstance(x, dict)
            ]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# 后台学习审查（LearningReviewer，S55 #2，借鉴 Hermes background_review）
# ---------------------------------------------------------------------------

_LEARNING_REVIEW_PROMPT = """你是小说写作系统的学习审查器。审查最近的一次写作/对话，
决定**该不该更新心智模型**。

心智模型 = 用户的写作偏好/习惯/雷区（自然语言条目），指导未来协作。

审查规则：
1. 只在**有新信息**时更新——用户明确表达的新偏好、明显的写作习惯变化、新雷区。
2. 不重复已有条目（内容已覆盖就不更新）。
3. 每次最多输出 2 条。没有值得更新的就输出空数组。

输出（严格 JSON 数组，不要其它文字）：
[{"content": "偏好短句（一句明确无歧义自然语言）",
"category": "collab|style|habit", "reason": "为什么值得记"}]

已有条目：
{entries}

最近内容：
{content}
"""


def build_learning_review_prompt(entries: list[ManualEntry], content: str) -> str:
    """学习审查提示词（供 app 层真实 LLM 调用，模型无关）。"""
    e = "\n".join(f"- [{s.category}] {s.content}" for s in entries[:20]) or "（无条目）"
    return _LEARNING_REVIEW_PROMPT.replace("{entries}", e).replace("{content}", content[:2000])


def parse_learning_review_result(raw: str) -> list[dict[str, str]]:
    """宽容解析学习审查结果 JSON。"""
    import json

    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            out = []
            for x in data:
                if not isinstance(x, dict):
                    continue
                category = str(x.get("category", "style"))
                if category not in ("collab", "style", "habit"):
                    category = "style"
                out.append(
                    {
                        "content": str(x.get("content", "")),
                        "category": category,
                        "reason": str(x.get("reason", "")),
                    }
                )
            return out
    except Exception:
        pass
    return []
