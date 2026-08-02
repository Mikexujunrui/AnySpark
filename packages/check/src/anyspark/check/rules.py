"""
anyspark.check.rules — 轻量规则编译器（机制 8 一级实现，默认极小）。

用户自然语言规则 → 内置编译（规则模板 + 正则/简单逻辑）→ 检测函数。
只读纯文本处理，无文件系统访问，安全风险极低。
复杂规则（编码扩展包 anyspark-codex）按需后补（YAGNI）。

支持的规则模板（当前极简集）：
- 禁用词/表达："不要破折号" / "禁用「然而」"
- 术语偏好："称呼要用「她」，不要用「那个女孩」"
- 风格约束："每段不超过三句话"
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# 检测函数：输入正文 → 命中的片段列表
RuleChecker = Callable[[str], list[str]]


@dataclass
class CompiledRule:
    """一条已编译的用户规则。"""

    original: str  # 用户原始自然语言规则
    description: str  # 编译后的可读描述
    checker: RuleChecker
    pattern: str = ""  # 正则（若有）


# 写作术语 → 实际字符/模式映射（轻量词典：用户说"不要破折号"→禁的是「——」）
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


# 规则模板识别（轻量关键词匹配）
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
