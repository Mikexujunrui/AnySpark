"""S53c 心智更新端测试：实时负例捕获(⑤) + 弱信号快照(⑦) + 对账解析(⑥)。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import ManualStore, NegativeCapture, weak_signal_from_text
from anyspark.align.mindup import build_reconcile_prompt, parse_reconcile_result


def _manual() -> ManualStore:
    return ManualStore(Path(tempfile.mkdtemp()) / "m.db")


def test_negative_capture_dash() -> None:
    """⑤ 实时负例：'不要用破折号' → 落雷区条目（habit, 低置信度）。"""
    m = _manual()
    nc = NegativeCapture(m)
    entry = nc.capture("不要用破折号，我看着难受")
    assert entry is not None
    assert entry.category == "habit"
    assert entry.confidence <= 0.5  # 低置信度
    assert "破折号" in entry.content
    assert "雷区" in entry.content
    # 幂等：再次捕获不重复落
    assert nc.capture("不要用破折号！") is None
    assert len(m.list("project")) == 1


def test_negative_capture_idiom() -> None:
    """⑤ 用词雷区：'别用成语' → 雷区条目。"""
    m = _manual()
    nc = NegativeCapture(m)
    entry = nc.capture("别用成语，太掉价了")
    assert entry is not None
    assert "成语" in entry.content


def test_negative_capture_positive_guard() -> None:
    """⑤ 守卫：'不要停，继续写' 不是雷区。"""
    m = _manual()
    nc = NegativeCapture(m)
    assert nc.capture("不要停，继续写") is None
    assert len(m.list("project")) == 0


def test_negative_capture_empty() -> None:
    """⑤ 空/无否定 → None。"""
    m = _manual()
    nc = NegativeCapture(m)
    assert nc.capture("这段很好") is None
    assert nc.capture("") is None
    assert len(m.list("project")) == 0


def test_weak_signal() -> None:
    """⑦ 弱信号：'稍微克制一点' → custom 弱信号；普通话 → None。"""
    sig = weak_signal_from_text("稍微克制一点对话")
    assert sig is not None
    assert "[弱信号]" in sig.content
    assert weak_signal_from_text("直接写吧") is None
    assert weak_signal_from_text("") is None


def test_reconcile_prompt_and_parse() -> None:
    """⑥ 对账：提示词含条目与信号；宽容解析结果。"""
    m = _manual()
    from anyspark.align import ManualEntry

    m.add(ManualEntry(content="雷区：不要破折号", category="habit"))
    entries = m.list("project")
    from anyspark.align import Signal

    signals = [Signal(kind="modified", content="改为：用了破折号", book_id="main")]
    prompt = build_reconcile_prompt(entries, signals)
    assert "雷区" in prompt and "破折号" in prompt
    # 宽容解析
    sample = '```json\n[{"entry": "x", "verdict": "冲突", "note": "n"}]\n```'
    parsed = parse_reconcile_result(sample)
    assert parsed and parsed[0]["verdict"] == "冲突"
    assert parse_reconcile_result("（无冲突）") == []


def test_learning_review_parse() -> None:
    """S55 #2 学习审查解析：宽容 JSON + 类别白名单。"""
    from anyspark.align.mindup import (
        build_learning_review_prompt,
        parse_learning_review_result,
    )

    sample = (
        '```json\n[{"content": "喜欢用短句", "category": "style", '
        '"reason": "本章对白全是短句"}]\n```'
    )
    parsed = parse_learning_review_result(sample)
    assert parsed and parsed[0]["content"] == "喜欢用短句"
    assert parsed[0]["category"] == "style"
    # 非法类别 → 回退 style
    bad = parse_learning_review_result('[{"content": "x", "category": "evil"}]')
    assert bad and bad[0]["category"] == "style"
    assert parse_learning_review_result("（无需更新）") == []
    # 提示词含条目与内容
    from anyspark.align import ManualEntry

    m = _manual()
    m.add(ManualEntry(content="对话要克制", category="style"))
    prompt = build_learning_review_prompt(m.list("project"), "本章内容测试")
    assert "对话要克制" in prompt and "本章内容测试" in prompt
