"""S53c 心智更新端测试：跨会话对账(⑥) 解析。

S62 修正：负例捕获(⑤)/弱信号快照(⑦) 的原正则/关键词层已删除——负例与试探语句
作为信号原文进 signals 表，"是否构成雷区/弱信号"是内容判断，交给轮末提炼器
（PreferenceExtractor 真实 LLM）与学习审查。本文件保留对账/学习审查的解析测试。
"""

from __future__ import annotations

from anyspark.align.mindup import build_reconcile_prompt, parse_reconcile_result


def test_reconcile_prompt_and_parse() -> None:
    """⑥ 对账提示词构造 + 宽容解析（围栏/前后文字）。"""
    from anyspark.align import ManualEntry
    from anyspark.align.signals import Signal

    entries = [ManualEntry(content="雷区：不要破折号", category="habit")]
    signals = [Signal(kind="accepted", content="这段不错")]
    prompt = build_reconcile_prompt(entries, signals)
    assert "雷区：不要破折号" in prompt and "accepted" in prompt

    raw = '[{"entry": "x", "verdict": "冲突", "note": "n"}]'
    parsed = parse_reconcile_result(raw)
    assert parsed[0]["verdict"] == "冲突"

    fenced = '```json\n[{"entry": "y", "verdict": "需更新", "note": "m"}]\n```'
    assert parse_reconcile_result(fenced)[0]["verdict"] == "需更新"

    assert parse_reconcile_result("没有冲突") == []


def test_learning_review_parse() -> None:
    """学习审查解析（LLM 输出宽容解析）。"""
    from anyspark.align.mindup import (
        build_learning_review_prompt,
        parse_learning_review_result,
    )

    prompt = build_learning_review_prompt([], "本章内容")
    assert "本章内容" in prompt

    raw = (
        '[{"content": "对话短句", "category": "habit", "reason": "用户多次强调"},'
        '{"content": "x", "category": "bogus", "reason": "非法类别回退"}]'
    )
    out = parse_learning_review_result(raw)
    assert len(out) == 2
    assert out[0]["category"] == "habit"
    assert out[1]["category"] == "style"  # 非法类别回退默认

    assert parse_learning_review_result("[]") == []
    assert parse_learning_review_result("废话") == []
