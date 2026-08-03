"""
anyspark.align.mood — 氛围滑块注入块（机制 4 低摩擦交互组件之一）。

氛围滑块组（B 类交互载体结构：设计者设计形状，模型只填充内容）：
- 维度自然语言描述（模型无关）：紧张感/温暖感/舒缓感/压抑感，强度 0-100
- 操作即语义：滑块值 → 结构化对齐信号 → 注入写作系统提示（本段氛围要求）
- 空字典/空输入 → 空串（不注入，零干扰）
"""

from __future__ import annotations

# 氛围维度（自然语言承载，模型无关；键为前端滑块标识）
MOOD_DIMS: dict[str, str] = {
    "tension": "紧张感",
    "warmth": "温暖感",
    "calm": "舒缓感",
    "dread": "压抑感",
}


def build_mood_block(mood: dict[str, float] | None) -> str:
    """氛围字典 → 自然语言注入块（空字典返回空串，不注入）。"""
    if not mood:
        return ""
    parts: list[str] = []
    for k, v in mood.items():
        name = MOOD_DIMS.get(k, k)
        val = max(0, min(100, int(v)))
        parts.append(f"{name} {val}/100")
    if not parts:
        return ""
    return "# 本段氛围要求\n" + "、".join(parts) + "（写作时让文字承载此氛围）"
