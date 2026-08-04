"""
compare.score — 客观评分器。

判据原则：客观指标（token/违规数/破折号计数）直接用正则/计数；
语义类（设定违反/名字漂移）用 **LLM 裁判**（同模型、双方同一裁判，公平且可重复）。
"""

from __future__ import annotations

import re

from benchmarks.compare.baseline import BareLLM

DASH_PATTERN = re.compile(r"——|—{2,}|–{2,}")


# ---------------------------------------------------------------------------
# 任务 A：设定忠实度（LLM 裁判核对 gold 设定违反）
# ---------------------------------------------------------------------------
SETTING_JUDGE_SYSTEM = (
    "你是严格的小说设定审查员。下面给出【设定清单】和【待审文本】。\n"
    "检查文本中是否出现与设定清单**矛盾**的表述（角色关系/身份/地点/事件因果等）。\n"
    "注意：只是没提到不算违规；只有明确写出与设定冲突的内容才算。\n"
    '输出严格 JSON：{"violations": [{"setting": "被违反的设定（原文摘录）", "reason": "文本中的矛盾表述"}]}\n'
    "无违规时输出 {\"violations\": []}\n"
)


def judge_setting_violations(
    judge: BareLLM, settings: str, text: str
) -> list[dict[str, str]]:
    out = judge.chat(SETTING_JUDGE_SYSTEM, f"【设定清单】\n{settings}\n\n【待审文本】\n{text[:5000]}")
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return []
    try:
        import json

        data = json.loads(m.group(0))
        items = data.get("violations", [])
        return [v for v in items if isinstance(v, dict)]
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# 任务 B：跨章名字漂移（LLM 裁判）
# ---------------------------------------------------------------------------
NAME_JUDGE_SYSTEM = (
    "你是小说连贯性审查员。下面给出一部长篇的【第1章】和【第3章】。\n"
    "检查第3章中提到的角色/地点/物件名字，是否与第1章出现过的对应名字**不一致**"
    "（如改名叫了别的、性别/身份变了、地名变了）。\n"
    "只报确实漂移的；第3章新出现的人物不算。\n"
    '输出严格 JSON：{"drifts": [{"ch1_name": "第1章的名字", "ch3_name": "第3章的名字", "type": "角色/地点/物件"}]}\n'
    "无漂移输出 {\"drifts\": []}\n"
)


def judge_name_drifts(
    judge: BareLLM, ch1: str, ch3: str
) -> list[dict[str, str]]:
    out = judge.chat(
        NAME_JUDGE_SYSTEM, f"【第1章】\n{ch1[:4000]}\n\n【第3章】\n{ch3[:4000]}"
    )
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return []
    try:
        import json

        data = json.loads(m.group(0))
        items = data.get("drifts", [])
        return [d for d in items if isinstance(d, dict)]
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# 任务 C：偏好遵守（客观正则）
# ---------------------------------------------------------------------------
def count_dashes(text: str) -> int:
    """破折号出现次数（——/---/––）。"""
    return len(DASH_PATTERN.findall(text))
