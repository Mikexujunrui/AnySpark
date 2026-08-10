"""anyspark.align.extract — 提炼器测试（fake model，不走网络）。"""

from anyspark.align import PreferenceExtractor
from anyspark.align.extract import _parse_json_array
from anyspark.core.types import Message, ModelOutput


class FakeModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text=self._reply)


def test_parse_json_array_fence() -> None:
    items = _parse_json_array('```json\n[{"content": "A", "confidence": 0.8}]\n```')
    assert items == [{"content": "A", "confidence": 0.8}]


def test_parse_json_array_noise() -> None:
    items = _parse_json_array('好的，这是提炼结果：[{"content": "B"}] 以上就是。')
    assert items == [{"content": "B"}]


def test_extract_filters_skip_and_invalid() -> None:
    model = FakeModel(
        '[{"content": "SKIP"}, {"content": "主角对话要克制", '
        '"confidence": 0.9, "activity": "high"}, '
        '{"content": "禁破折号", "confidence": "bad", "activity": "weird"}]'
    )
    ex = PreferenceExtractor(model)
    entries = ex.extract(dialogue=[], signals=[])
    assert len(entries) == 2
    e1, e2 = entries
    assert e1.content == "主角对话要克制"
    assert e1.confidence == 0.9
    assert e1.activity == "high"
    assert e1.source == "auto"
    # 非法 activity 回落到 medium，坏 confidence 回落到 0.5
    assert e2.confidence == 0.5
    assert e2.activity == "medium"


def test_extract_empty_output() -> None:
    model = FakeModel("什么都没有")
    ex = PreferenceExtractor(model)
    assert ex.extract(dialogue=[], signals=[]) == []


def test_extract_parses_category_and_negative() -> None:
    """S73d：提炼条目落分类（负向偏好归 habit，category 解析）。"""
    from anyspark.align.extract import EXTRACT_PROMPT

    # 负向句式引导在 prompt 里（natural 语言语义）
    assert "雷区/负向偏好" in EXTRACT_PROMPT
    assert "避免…/不要…" in EXTRACT_PROMPT
    assert "category" in EXTRACT_PROMPT

    raw = (
        '[{"content": "避免使用破折号", "confidence": 0.9, "activity": "high",'
        ' "category": "habit"},'
        ' {"content": "对话要克制", "confidence": 0.7, "activity": "medium",'
        ' "category": "style"},'
        ' {"content": "先给大纲再动笔", "confidence": 0.6, "activity": "low",'
        ' "category": "collab"}]'
    )
    model = FakeModel(raw)
    entries = PreferenceExtractor(model).extract([], [], max_items=3)
    cats = {e.content: e.category for e in entries}
    assert cats["避免使用破折号"] == "habit"  # 负向偏好归 habit
    assert cats["对话要克制"] == "style"
    assert cats["先给大纲再动笔"] == "collab"
    # 非法 category 回退 style
    raw2 = '[{"content": "x", "category": "nonsense"}]'
    entries2 = PreferenceExtractor(FakeModel(raw2)).extract([], [], max_items=1)
    assert entries2[0].category == "style"
