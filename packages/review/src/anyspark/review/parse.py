"""anyspark.review.parse — 宽容 JSON 提取（LLM 输出解析）。

LLM 输出 JSON 常带 ```json fence、前后废话、注释尾逗号等噪声。
策略（对齐 v4 check 的经验，比参考项目的裸 json.loads 更稳）：
1. 尝试整体 loads（兼容纯 JSON 输出）；
2. 失败则剥离 markdown fence，找第一个平衡的 {...} 或 [...] 块提取；
3. 仍失败返回 None（调用方降级处理，不抛异常）。
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(raw: str | None) -> Any | None:
    """从 LLM 输出中宽容提取 JSON 对象/数组；失败返回 None。"""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None

    # 1. 直接解析
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 剥 fence（```json ... ``` 或 ``` ... ```）
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            cleaned = fence.group(1).strip()

    # 3. 提取第一个平衡结构（{...} 或 [...]）
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break  # 该块不可解析，试下一个起点
    return None


def parse_review_json(raw: str) -> dict[str, Any] | None:
    """解析单个评审员输出（JSON 对象）。返回 None 表示解析失败。"""
    data = extract_json(raw)
    if isinstance(data, dict):
        return data
    return None


def _to_str_list(value: Any) -> list[str]:
    """把 LLM 输出的字符串/列表归一化为 str 列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        # 兼容 "1. xxx\n2. yyy" 形式的文本列表
        lines = [ln.strip() for ln in value.splitlines() if ln.strip()]
        return [re.sub(r"^[\d\.\-\*\s]+", "", ln) for ln in lines]
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_scores(data: dict[str, Any]) -> dict[str, float]:
    """提取评分映射：只收数值且 0-10 范围内的维度分（防 LLM 输出越界/字符串）。"""
    scores: dict[str, float] = {}
    raw = data.get("scores")
    if not isinstance(raw, dict):
        return scores
    for k, v in raw.items():
        if v is None:
            continue
        f = _to_float(v)
        if 0 <= f <= 10:
            scores[str(k)] = f
    return scores
