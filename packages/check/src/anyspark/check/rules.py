"""
anyspark.check.rules — 规则编译（机制 8：用户自然语言 → 检测函数）。

哲学（DESIGN §1 极简方法论）：**内容判断交给模型、执行机制硬编码**——
- 用户规则"是什么意思"（禁什么/偏好什么/限几句）是内容判断 → LLM 编译
  （compile_with_model：模型把自然语言解析成结构化指令）。
- 检测"怎么做"（查词/统计句数）是过程 → 确定性执行器硬编码
  （_make_forbidden / _make_term_preference / _make_max_sentences）。
- 无 LLM 场景保留轻量模板 fallback（compile_rule）；模型/模板都识别不了时
  **明确告知用户**（不再静默丢弃）。
只读纯文本处理，无文件系统访问，安全风险极低。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from anyspark.core import Message, Model

# 检测函数：输入正文 → 命中的片段列表
RuleChecker = Callable[[str], list[str]]


@dataclass
class CompiledRule:
    """一条已编译的用户规则。"""

    original: str  # 用户原始自然语言规则
    description: str  # 编译后的可读描述
    checker: RuleChecker
    pattern: str = ""  # 正则（若有）


# 写作术语 → 实际字符/模式映射（机制：中文标点名 → 字符，非内容判断）
_TERM_PATTERNS: dict[str, str] = {
    "破折号": "——|—",
    "感叹号": "！|!",
    "省略号": "……|…",
    "括号": "[（）()]",
    "引号": "[「」“”‘’\"']",
    "逗号": "[，,]",
}


def _make_forbidden(phrases: list[str]) -> RuleChecker:
    # 把写作术语映射成实际字符模式
    patterns = [re.compile(_TERM_PATTERNS.get(p, re.escape(p))) for p in phrases]

    def check(text: str) -> list[str]:
        hits: list[str] = []
        for pat in patterns:
            hits.extend(m.group(0) for m in pat.finditer(text))
        return hits

    return check


def _make_term_preference(forbidden: str, preferred: str) -> RuleChecker:
    pat = re.compile(re.escape(forbidden))

    def check(text: str) -> list[str]:
        return [m.group(0) for m in pat.finditer(text)]

    return check


def _make_max_sentences_per_paragraph(n: int) -> RuleChecker:
    def check(text: str) -> list[str]:
        hits: list[str] = []
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                continue
            # 中文句号/问号/感叹号计句
            count = len(re.findall(r"[。！？.!?]", para))
            if count > n:
                hits.append(para[:80])
        return hits

    return check


# ---------------------------------------------------------------------------
# LLM 编译（内容判断交给模型）：用户自然语言 → 结构化指令 → 确定性执行器
# ---------------------------------------------------------------------------

_RULE_COMPILE_PROMPT = """你是写作检测规则的编译器。用户用自然语言描述一条检测规则，
你把它转成结构化指令。只做**字面/结构检测**（禁用词、术语偏好、段落句数），
不做语义/情感判断（那是审读器的职责）。

可选指令类型（输出严格 JSON 对象）：
1. 禁用词/符号：{{"kind": "forbidden", "phrases": ["破折号", "然而"],
"description": "禁用：破折号、然而"}}
2. 术语偏好：{{"kind": "term", "preferred": "她", "forbidden": "那个女孩",
"description": "称呼用「她」不用「那个女孩」"}}
3. 段落句数上限：{{"kind": "sentences", "max": 3, "description": "每段不超过 3 句"}}
4. 无法确定：{{"kind": "unknown", "description": "需要语义判断，超出字面检测能力"}}

要求：phrases/max 尽量具体可执行；description 一句可读自然语言。

用户规则：{rule}
"""


_RULE_COMPILE_EXAMPLES: list[tuple[str, dict[str, Any]]] = [
    ("不要用破折号", {"kind": "forbidden", "phrases": ["破折号"], "description": "禁用：破折号"}),
    ("每段不要超过三句话", {"kind": "sentences", "max": 3, "description": "每段不超过 3 句"}),
    (
        "称呼要用她，不要用那个女孩",
        {
            "kind": "term",
            "preferred": "她",
            "forbidden": "那个女孩",
            "description": "称呼用「她」不用「那个女孩」",
        },
    ),
]


def _parse_compiled(raw: str) -> dict[str, Any] | None:
    """宽容解析 LLM 编译结果 JSON。"""
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def compile_with_model(user_rule: str, model: Model) -> CompiledRule | None:
    """LLM 编译：模型解析用户自然语言 → 结构化指令 → 确定性执行器。

    模型/指令都无法落地时返回 None（调用方明确告知用户，不静默丢弃）。
    """
    rule = user_rule.strip()
    if not rule:
        return None
    prompt = _RULE_COMPILE_PROMPT.replace("{rule}", rule)
    try:
        out = model.respond([Message(role="system", content=prompt)], [])
        spec = _parse_compiled(out.text)
    except Exception:
        return None
    if not spec:
        return None
    kind = str(spec.get("kind", ""))
    description = str(spec.get("description", "")) or rule
    if kind == "forbidden":
        phrases = [str(p) for p in (spec.get("phrases") or []) if str(p).strip()]
        if phrases:
            return CompiledRule(
                original=rule,
                description=description,
                checker=_make_forbidden(phrases),
                pattern="|".join(re.escape(p) for p in phrases),
            )
    elif kind == "term":
        forbidden = str(spec.get("forbidden", "")).strip()
        preferred = str(spec.get("preferred", "")).strip()
        if forbidden:
            return CompiledRule(
                original=rule,
                description=description,
                checker=_make_term_preference(forbidden, preferred),
                pattern=re.escape(forbidden),
            )
    elif kind == "sentences":
        try:
            n = int(spec.get("max", 0))
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return CompiledRule(
                original=rule,
                description=description,
                checker=_make_max_sentences_per_paragraph(n),
            )
    return None  # unknown 或字段缺失 → 调用方明确告知


# ---------------------------------------------------------------------------
# 无 LLM fallback：轻量模板编译（保留，极简）
# ---------------------------------------------------------------------------
_FORBIDDEN_RE = re.compile(
    r"(?:不要|禁用|禁止|避免|不许|别用|不用)(?:用|出现)?"
    r"[「\"']?([^「」\"'。；，,\n]{2,12})[」\"']?"
)
_TERM_RE = re.compile(
    r"(?:要用|称呼要用|统一要用|统一用|用)「([^」]{1,10})」(?:，|而|,)?"
    r"(?:不要|而不要|别用|别)用?「([^」]{1,10})」"
)
_PARAGRAPH_RE = re.compile(
    r"每段(?:不|最)?超过?((?:\d+|[一二两三四五六七八九十]))\s*句"
    r"|每段(?:不超过|最多)((?:\d+|[一二两三四五六七八九十]))\s*句"
)


# 中文数字（供句数规则用）
_CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _num(s: str) -> int:
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s, 0)


def compile_rule(user_rule: str) -> CompiledRule | None:
    """把用户自然语言规则编译成检测函数。不匹配任何模板返回 None。"""
    rule = user_rule.strip()
    if not rule:
        return None

    # 模板2（先于禁用词）：术语偏好（要用 X 不要用 Y）
    m = _TERM_RE.search(rule)
    if m:
        preferred, forbidden = m.group(1), m.group(2)
        return CompiledRule(
            original=rule,
            description=f"称呼用「{preferred}」，不用「{forbidden}」",
            checker=_make_term_preference(forbidden, preferred),
            pattern=re.escape(forbidden),
        )

    # 模板1：禁用词/表达
    m = _FORBIDDEN_RE.search(rule)
    if m:
        phrase = m.group(1)
        return CompiledRule(
            original=rule,
            description=f"禁用：{phrase}",
            checker=_make_forbidden([phrase]),
            pattern=re.escape(phrase),
        )

    # 模板3：段落句数
    m = _PARAGRAPH_RE.search(rule)
    if m:
        n = _num(m.group(1) or m.group(2) or "0")
        if n > 0:
            return CompiledRule(
                original=rule,
                description=f"每段不超过 {n} 句",
                checker=_make_max_sentences_per_paragraph(n),
            )

    return None


def check_text(rules: list[CompiledRule], text: str) -> list[tuple[CompiledRule, list[str]]]:
    """对正文跑全部规则，返回 [(规则, 命中片段)]。"""
    return [(r, r.checker(text)) for r in rules if r.checker(text)]
