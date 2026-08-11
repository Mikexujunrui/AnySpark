"""
anyspark.align.extract — 提炼器（对话+操作 → 偏好条目）。

设计（DESIGN 第 6 节）：提炼器把"对话 + 操作信号"提炼成偏好条目，
进用户模型（承担对齐）。条目=自然语言短句 + 来源 + 置信度 + 活跃度 + 锁定。
用真实 DeepSeek 提炼（模型无关：提示词与输出全为自然语言）。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import Message
from anyspark.core.jsonutil import parse_json_array

from .manual import Activity, ManualEntry
from .signals import Signal

# 提炼提示模板（自然语言，模型无关）
EXTRACT_PROMPT = """你是小说写作协作系统的偏好提炼器。从下面的"对话片段 + 用户操作信号"中，
提炼出用户稳定、可复用的写作偏好/雷区条目。

信号类型含义（S73d）：
- negative（用户否定/撤回）：如"不要破折号"——提炼为**雷区/负向偏好**，句式用
  "避免…/不要…"（如"避免使用破折号"），category=habit
- modified（用户修改）："改成这样更好"——提炼为正向偏好（用户更想要的样子），
  category 按内容定（style/habit/collab）
- accepted（用户接受）：偏好确认，可提炼为高置信度偏好
- rejected（用户拒绝）：同 negative 处理（可能是雷区）

要求：
1. 只提炼**稳定偏好**（重复出现/强烈表达），不要提炼一次性事实。
2. 每条用一句明确无歧义的自然语言短句表达，能直接指导未来写作。
3. 标注置信度（0-1，越高越确定）、活跃度（high/medium/low）与分类（collab/style/habit）。
4. 若某条与用户已有偏好冲突，不要输出它（写"SKIP"）。

输出格式（严格 JSON 数组，不要其它文字）：
[{"content": "偏好短句", "confidence": 0.8, "activity": "high", "category": "style"}]

对话与操作信号：
"""


class PreferenceExtractor:
    """偏好提炼器：真实 LLM 提炼（模型无关，适配器注入）。"""

    def __init__(self, model: object) -> None:
        # model 实现 core.Model 协议（respond(messages, tools) -> ModelOutput）
        self._model = model

    def extract(
        self, dialogue: list[Message], signals: list[Signal], max_items: int = 3
    ) -> list[ManualEntry]:
        """从对话+操作提炼偏好条目（过滤 SKIP 与非法项）。"""
        signal_text = (
            "\n".join(f"- [{s.kind}] {s.content}" for s in signals[:20]) or "（无操作信号）"
        )
        dialogue_text = (
            "\n".join(f"{m.role}: {m.content[:200]}" for m in dialogue[-10:]) or "（无对话）"
        )

        prompt = EXTRACT_PROMPT + f"\n对话片段：\n{dialogue_text}\n\n操作信号：\n{signal_text}\n"
        prompt += f"\n请提炼最多 {max_items} 条偏好，输出 JSON 数组。"

        # 用真实模型（无工具）调用
        output = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return self._parse(output.text)

    def _parse(self, raw: str) -> list[ManualEntry]:
        entries: list[ManualEntry] = []
        for item in _parse_json_array(raw):
            content = str(item.get("content", "")).strip()
            if not content or content == "SKIP" or content.upper() == "SKIP":
                continue
            try:
                conf = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            activity: Activity = (
                item.get("activity", "medium")
                if item.get("activity", "medium") in ("high", "medium", "low")
                else "medium"
            )
            # S73d：提炼条目落分类（collab/style/habit，负向偏好归 habit）
            category = str(item.get("category", "style")).strip()
            if category not in ("collab", "style", "habit"):
                category = "style"
            entries.append(
                ManualEntry(
                    content=content,
                    source="auto",
                    confidence=conf,
                    activity=activity,
                    category=category,  # type: ignore[arg-type]
                )
            )
        return entries


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """宽容解析模型输出的 JSON 数组（去围栏/取数组/过滤 dict，行为同旧实现）。"""
    data = parse_json_array(text)
    if data is None:
        return []
    return [d for d in data if isinstance(d, dict)]
