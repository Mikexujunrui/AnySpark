"""
anyspark.core.jsonutil — 模型输出 JSON 宽容解析（R1 收敛）。

背景：align/explore/graph 多包各自实现"围栏剥离 + 括号提取 + json.loads 容错"
样板（~15 行重复）。收敛为共享函数，行为与既有实现一致：

- strip_fence：去除 ```json ... ``` 围栏（无围栏返回原文）
- parse_json_object：提取第一个 { 到最后一个 } 后容错解析，成功且为 dict 返回，
  否则返回 None（调用方决定回退：空 dict / fallback）
- parse_json_array：提取第一个 [ 到最后一个 ] 后容错解析，成功且为 list 返回，
  否则返回 None（调用方回退空列表）

core 不依赖任何第三方包（json/re 为 Python 标准库）。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def strip_fence(text: str) -> str:
    """去除 ```json ... ``` 围栏；无围栏返回原文。"""
    m = _FENCE.search(text)
    return m.group(1) if m else text


def parse_json_object(text: str) -> dict[str, Any] | None:
    """宽容解析模型输出中的 JSON 对象。

    去围栏 → 取第一个 { 到最后一个 } → json.loads 容错。
    解析成功且为 dict 返回 dict；失败/非 dict 返回 None。
    """
    cleaned = strip_fence(text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def parse_json_array(text: str) -> list[Any] | None:
    """宽容解析模型输出中的 JSON 数组。

    去围栏 → 取第一个 [ 到最后一个 ] → json.loads 容错。
    解析成功且为 list 返回 list；失败/非 list/无括号 返回 None。
    """
    cleaned = strip_fence(text.strip())
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None
