"""
anyspark.workflow.condition — 条件表达式解析与评估（gate 分支的硬规则通道）。

语法（对齐 DeterminFlow condition_parser 的设计，自研实现）：
  expr       → or_expr
  or_expr    → and_expr ("OR" and_expr)*
  and_expr   → unary_expr ("AND" unary_expr)*
  unary_expr → "NOT" unary_expr | primary
  primary    → "(" expr ")" | comparison
  comparison → value OP value
  value      → NUMBER | STRING | {{var}}
  OP         → == | != | >= | <= | > | < （数字字符串自动数值比较）

评估前变量字典提供 {{var}} 的值；未定义变量按空串处理（缺省不炸）。
"""

from __future__ import annotations

import re
from typing import Any

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
_TOKEN_RE = re.compile(
    r"\s*(==|!=|>=|<=|>|<|contains|not\s+contains|\(|\)|AND|OR|NOT|[0-9]+(?:\.[0-9]+)?|\"[^\"]*\"|'[^']*'|\{\{[A-Za-z0-9_.\-]+\}\})",
    re.IGNORECASE,
)
_OP_FN: dict[str, Any] = {
    "==": lambda a, b: _num_cmp(a, b, "=="),
    "!=": lambda a, b: _num_cmp(a, b, "!="),
    ">=": lambda a, b: _num_cmp(a, b, ">="),
    "<=": lambda a, b: _num_cmp(a, b, "<="),
    ">": lambda a, b: _num_cmp(a, b, ">"),
    "<": lambda a, b: _num_cmp(a, b, "<"),
    "contains": lambda a, b: str(b).strip().lower() in str(a).lower(),
    "NOT_CONTAINS": lambda a, b: str(b).strip().lower() not in str(a).lower(),
}


def _num_cmp(a: str, b: str, op: str) -> bool:
    """优先数值比较，非数字回退字符串比较。"""
    # 数值比较优先（mypy 无法统一 float/str 联合，用 float() 兜底比较）
    try:
        na, nb = float(a), float(b)
        numeric = True
    except (ValueError, TypeError):
        numeric = False
    if op == "==":
        return na == nb if numeric else str(a).strip() == str(b).strip()
    if op == "!=":
        return na != nb if numeric else str(a).strip() != str(b).strip()
    if not numeric:
        # 非数字字符串不支持关系比较（> >= < <=）——长度比较无语义（S62 修正：
        # 原实现按字符串长度回退，'abc'>'d' 得 True 是拍脑袋伪结果，静默错误分支）
        # 求值失败走 evaluate_rule 的异常路径（条件不满足 → 默认分支）
        raise ValueError(f"非数字字符串不支持关系比较 {op!r}（仅支持 == / != / contains）")
    if op == ">=":
        return na >= nb
    if op == "<=":
        return na <= nb
    if op == ">":
        return na > nb
    return na < nb


def _tokenize(expr: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            # 跳过空白/非法字符，防止表达式带杂散文本时解析崩溃
            pos += 1
            continue
        tok = m.group(1).strip()
        if tok:
            upper = tok.upper()
            if upper in ("AND", "OR", "NOT"):
                tokens.append(upper)
            elif upper in ("NOT CONTAINS", "NOT_CONTAINS"):
                tokens.append("NOT_CONTAINS")
            elif upper == "CONTAINS":
                tokens.append("contains")
            else:
                tokens.append(tok)
        pos = m.end()
    # 归一化：合并被拆开的 NOT + contains → NOT_CONTAINS
    merged: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "NOT" and i + 1 < len(tokens) and tokens[i + 1] == "contains":
            merged.append("NOT_CONTAINS")
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged


class _Parser:
    def __init__(self, tokens: list[str], variables: dict[str, Any]) -> None:
        self._toks = tokens
        self._pos = 0
        self._vars = variables

    def peek(self) -> str | None:
        return self._toks[self._pos] if self._pos < len(self._toks) else None

    def eat(self, expected: str | None = None) -> str | None:
        tok = self.peek()
        if tok is not None and (expected is None or tok == expected):
            self._pos += 1
            return tok
        return None

    # 值：NUMBER | STRING | {{var}}
    def _value(self) -> str:
        tok = self.peek()
        if tok is None:
            return ""
        m = _VAR_RE.match(tok)
        if m:
            self._pos += 1
            key = m.group(1)
            val = self._vars.get(key)
            if val is None:
                return ""
            if isinstance(val, bool):
                return "1" if val else "0"
            if isinstance(val, (int, float)):
                return str(val)
            return str(val)
        # 字符串字面量（带引号）→ 去引号
        if (tok.startswith('"') and tok.endswith('"')) or (
            tok.startswith("'") and tok.endswith("'")
        ):
            self._pos += 1
            return tok[1:-1]
        if tok in (
            "AND",
            "OR",
            "NOT",
            "(",
            ")",
            "==",
            "!=",
            ">=",
            "<=",
            ">",
            "<",
            "contains",
            "NOT_CONTAINS",
        ):
            # 孤立操作符/括号出现在值位 → 当作空串（容错）
            return ""
        self._pos += 1
        return tok

    def _primary(self) -> bool:
        if self.eat("("):
            val = self._or_expr()
            self.eat(")")
            return val
        left = self._value()
        op = self.peek()
        if op in _OP_FN:
            self._pos += 1
            right = self._value()
            fn = _OP_FN[op]
            assert callable(fn)
            return bool(fn(left, right))
        # 无操作符的裸值 → 真值判断（非空即真，兼容 "变量存在" 的常见用法）
        return left.strip() != "" and left.strip().lower() not in ("0", "false", "no", "无", "否")

    def _unary_expr(self) -> bool:
        if self.eat("NOT"):
            return not self._unary_expr()
        return self._primary()

    def _and_expr(self) -> bool:
        val = self._unary_expr()
        while self.peek() == "AND":
            self._pos += 1
            right = self._unary_expr()
            val = val and right
        return val

    def _or_expr(self) -> bool:
        val = self._and_expr()
        while self.peek() == "OR":
            self._pos += 1
            right = self._and_expr()
            val = val or right
        return val


def evaluate_rule(expression: str, variables: dict[str, Any]) -> bool:
    """评估硬规则条件表达式。空表达式 → True（无条件边=默认分支）。"""
    expr = (expression or "").strip()
    if not expr:
        return True
    toks = _tokenize(expr)
    if not toks:
        return False
    try:
        return _Parser(toks, variables)._or_expr()
    except Exception:
        # 表达式语法错误时容错为 False（不炸引擎；条件不满足走默认分支）
        return False


def validate_rule_syntax(expression: str) -> list[str]:
    """语法预检（供生成器校验候选定义用）。"""
    errors: list[str] = []
    expr = (expression or "").strip()
    if not expr:
        return errors
    toks = _tokenize(expr)
    if not toks:
        return ["表达式无有效 token"]
    # 括号配平
    depth = 0
    for t in toks:
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
            if depth < 0:
                return ["括号不配对"]
    if depth != 0:
        return ["括号不配对"]
    # 运算符后必须跟值（S62：_tokenize 已把 not 规范化为 NOT，检查规范化后的 token）
    for i, t in enumerate(toks):
        if t == "NOT" and (i + 1 >= len(toks) or toks[i + 1] != "contains"):
            return [f"位置 {i}: 孤立 NOT（应为 'not contains' 或逻辑 NOT）"]
    return errors
