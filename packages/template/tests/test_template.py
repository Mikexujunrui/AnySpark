"""anyspark.template — 模式库 + 资料消化测试。"""

import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.template import MaterialCard, MaterialDigestor, MaterialStore, default_library


class FakeDigestor:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text=self._reply)


def test_default_library_has_valid_metadata() -> None:
    lib = default_library()
    assert len(lib) >= 5
    for t in lib:
        assert t.granularity in ("全书", "卷", "章", "场景", "段落")
        assert t.position in ("开局", "发展", "高潮", "结局")
        assert t.function in ("铺垫", "主线", "悬念", "爽点", "情感")
        assert t.description  # 自然语言描述非空


def test_material_store_crud() -> None:
    store = MaterialStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        card = MaterialCard(
            title="雾城地理志",
            topic="雾城的地理与气候",
            key_points=["常年大雾", "港口城市"],
            key_settings=["雾城", "临江"],
            characters=["陈渡"],
            terms=["雾瘴"],
        )
        store.save(card)
        got = store.get(card.id)
        assert got is not None
        assert got.topic == "雾城的地理与气候"
        assert got.key_points == ["常年大雾", "港口城市"]
        assert len(store.list()) == 1
    finally:
        store.close()


def test_material_summarize_injection() -> None:
    card = MaterialCard(
        title="雾城地理志",
        topic="雾城地理",
        key_points=["常年大雾", "港口城市"],
        key_settings=["雾城"],
        characters=["陈渡"],
        terms=["雾瘴"],
    )
    summary = card.summarize()
    assert "雾城地理" in summary
    assert "常年大雾" in summary
    assert len(summary) <= 300  # 注入省 token


def test_digestor_parses() -> None:
    model = FakeDigestor(
        '{"title": "江湖传闻", "topic": "武林门派恩怨", '
        '"key_points": ["三派对立", "掌门失踪"], "key_settings": ["青云山"], '
        '"characters": ["叶孤城"], "terms": ["内力"]}'
    )
    digestor = MaterialDigestor(model)
    card = digestor.digest("材料原文……", purpose="fact")
    assert card.title == "江湖传闻"
    assert card.key_points == ["三派对立", "掌门失踪"]
    assert card.purpose == "fact"
    assert card.source_text == "材料原文……"  # 原文保留


def test_digestor_fallback_on_bad_json() -> None:
    model = FakeDigestor("抱歉，无法解析")
    digestor = MaterialDigestor(model)
    card = digestor.digest("一些材料内容", purpose="style")
    assert card.purpose == "style"
    assert card.key_points == []
    assert card.title  # 回退标题


def test_digest_purpose_guides_prompt() -> None:
    """S72：digest 按 purpose 注入不同引导（style 提炼文风特征，fact 提炼设定）。"""

    class _RecordingDigestor:
        model_name = "probe"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.prompts.append(messages[0].content or "")
            return ModelOutput(
                text='{"title": "卡", "topic": "t", "key_points": ["p"], '
                '"key_settings": [], "characters": [], "terms": []}'
            )

    model = _RecordingDigestor()
    digestor = MaterialDigestor(model)
    digestor.digest("原文……", purpose="style")
    digestor.digest("原文……", purpose="fact")
    style_prompt, fact_prompt = model.prompts[0], model.prompts[1]
    assert "文风参考" in style_prompt and "文风特征" in style_prompt
    assert "编造世界观设定" in style_prompt  # style 引导防编造
    assert "设定参考" in fact_prompt
    assert "文风参考" not in fact_prompt
