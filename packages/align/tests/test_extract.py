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
