"""anyspark.align.mindup — 心智模型更新端（S53c：补齐 S51 更新方式缺口）。

对应 DESIGN §12.18 心智模型横断决策的更新方式全景：
- #5 实时负例捕获（NegativeCapture）：用户明确否定/撤回 → 即时落低置信度雷区条目，
  防隐式否定被上下文稀释丢失。规则硬编码（机制），条目内容自然语言。
- #6 跨会话对账（Reconcile）：沉淀的偏好条目 vs 最近实际行为信号比对——
  发现"标了雷区却在用 / 标了偏好却没遵守" → 提示可能记反/需更新（纠偏）。
- #7 会话内弱信号快照（WeakSignal）：过程里产生的低置信度信号留快照，
  供轮末/归档时提炼器参考（不直接升置信度）。

哲学：机制（规则/比对/快照结构）硬编码；内容（条目/比对结果）自然语言。
"""

from __future__ import annotations

import re

from .manual import ManualEntry, ManualStore
from .signals import Signal

# ---------------------------------------------------------------------------
# ⑤ 实时负例捕获（NegativeCapture）
# ---------------------------------------------------------------------------

# 否定/撤回的关键词（机制硬编码：可扩展；内容判定靠关键词自然语言）
_NEGATIVE_HINTS: list[tuple[str, str]] = [
    # (触发正则, 规范化后的"雷区"语义前缀)
    (r"不(要|用|想|喜欢|需要|该).{0,20}(破折号|省略号|感叹号|括号)", "雷区（标点）："),
    (r"不要[写用].{0,15}(废话|铺垫|描写|形容词|副词)", "雷区（写法）："),
    (r"别[用写].{0,15}(成语|网络词|英文|术语)", "雷区（用词）："),
    (r"我?说(了|过|的)?不[要是]", "雷区（明确否定）："),
    (r"不许|禁止|千万别", "雷区："),
    (r"不(要|喜欢).{0,20}(血腥|暴力|色情|悲剧|虐)", "雷区（题材）："),
    (r"我[是]?不[要喜][^。，；]{0,15}", "雷区（偏好否定）："),
]

# 明显不是负例的肯定句（避免把"不要觉得难，继续写"误判为雷区）
_POSITIVE_GUARDS: list[str] = [
    "不要停",
    "不要怕",
    "不要紧",
    "不要想太多",
    "不必要",
    "不需",
]


class NegativeCapture:
    """实时负例捕获：把用户明确否定/撤回即时落成低置信度雷区条目。"""

    def __init__(self, manual: ManualStore, book_id: str = "main") -> None:
        self._manual = manual
        self._book_id = book_id

    def capture(self, text: str, context: str = "") -> ManualEntry | None:
        """检测否定语句 → 落雷区条目（低置信度，可编辑）。返回 None=未命中。

        幂等：已有相同雷区条目不重复落（内容含该雷区词）。
        """
        text = (text or "").strip()
        if not text:
            return None
        # 肯定句式守卫：整句命中守卫词（"不要停"等）→ 不是雷区
        if any(g in text for g in _POSITIVE_GUARDS):
            return None
        for pattern, prefix in _NEGATIVE_HINTS:
            m = re.search(pattern, text)
            if not m:
                continue
            # 提取雷区具体对象（否定词后的内容），如"不要用破折号"→"破折号"
            hit = m.group(0)
            # 已有条目含相同雷区词 → 幂等跳过（只提高活跃度）
            existing = self._manual.list("project", self._book_id)
            if any(e.category == "habit" and hit in e.content for e in existing):
                return None
            content = f"{prefix}{hit}（用户原话：{text[:60]}）"
            entry = ManualEntry(
                content=content,
                source="auto",
                confidence=0.45,  # 低置信度：规则命中，需用户确认/校准
                activity="high",  # 新鲜负例，活跃度高
                locked=False,
                scope="project",
                book_id=self._book_id,
                category="habit",  # 雷区归习惯类（MindPlanner 已读 habit）
            )
            self._manual.add(entry)
            return entry
        return None


# ---------------------------------------------------------------------------
# ⑦ 会话内弱信号快照（WeakSignal）
# ---------------------------------------------------------------------------

_WEAK_KEYWORDS: list[str] = [
    "有点",
    "稍微",
    "试着",
    "可能",
    "不太",
    "犹豫",
    "改一下",
    "调一下",
]


def weak_signal_from_text(text: str, context: str = "") -> Signal | None:
    """从用户一句话里提取弱信号（试探/微调/犹豫），返回 Signal 或 None。

    弱信号 = 低置信度的偏好线索（"稍微克制一点"），不直接升置信度，
    只留快照供轮末/归档提炼器参考（S51 #7）。
    """
    text = (text or "").strip()
    if not text:
        return None
    if any(kw in text for kw in _WEAK_KEYWORDS):
        return Signal(kind="custom", content=f"[弱信号]{text}", context=context)
    return None


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
