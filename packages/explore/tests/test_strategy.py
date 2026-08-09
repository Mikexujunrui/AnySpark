"""anyspark.explore.strategy + intent 测试（无网络）。"""

from anyspark.core.types import Message, ModelOutput
from anyspark.explore import (
    ExplorationStrategy,
    IntentUnderstander,
    extract_json_dict,
)


class FakeModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text=self._reply)


def test_extract_json_dict_fence() -> None:
    d = extract_json_dict('```json\n{"a": 1}\n```')
    assert d == {"a": 1}


def test_extract_json_dict_noise() -> None:
    d = extract_json_dict('结果是 {"title": "X"} 完毕')
    assert d == {"title": "X"}


def test_strategy_assign_dimension_and_source() -> None:
    s = ExplorationStrategy(
        seed="一个雨夜侦探抵达小城",
        intent_confirmed={"concept": {"core": "雨夜侦探", "mood": "阴郁", "genre": "悬疑"}},
    )
    dim0, src0 = s.assign(0)
    dim1, src1 = s.assign(1)
    assert dim0 != dim1  # 维度差异化
    assert src0 == "template"
    assert src1 == "grow"  # 三来源混合


def test_strategy_prompt_contains_constraints() -> None:
    s = ExplorationStrategy(
        seed="种子",
        intent_confirmed={"concept": {"core": "X"}},
        constraints=["女主=医者"],
    )
    prompt = s.explorer_prompt(0)
    assert "女主=医者" in prompt
    assert "不得冲突" in prompt


def test_card_from_response() -> None:
    s = ExplorationStrategy(seed="s", intent_confirmed={"concept": {}})
    card = s.card_from_response(
        0,
        '{"title": "双线叙事", "summary": "A线主线B线暗线", "term": "双线"}',
    )
    assert card.title == "双线叙事"
    assert card.dimension == "情节驱动"  # 第一个探索者
    assert card.source == "template"
    assert card.term == "双线"


def test_template_injection_only_for_template_source() -> None:
    """S68：template 来源探索者注入真实模板；grow/user 不注入（三来源隔离）。"""
    tpl = [
        "废柴流开局·反差铺垫：主角以废柴登场，通过反差暗示隐藏潜力",
        "三幕·先抑后扬：压低到谷底再逆转",
    ]
    s = ExplorationStrategy(
        seed="s",
        intent_confirmed={"concept": {"core": "X"}},
        templates=tpl,
    )
    # 来源顺序 template/grow/user/template：0 和 3 是 template，1 是 grow，2 是 user
    p0 = s.explorer_prompt(0)
    p1 = s.explorer_prompt(1)
    p2 = s.explorer_prompt(2)
    # 用注入块特征判据（"参考叙事模板" + 模板内容独有短语，避开 prompt 内 JSON 示例）
    assert "参考叙事模板" in p0  # template 来源注入
    assert "暗示隐藏潜力" in p0
    assert "参考叙事模板" not in p1  # grow 不注入
    assert "暗示隐藏潜力" not in p1
    assert "参考叙事模板" not in p2  # user 不注入
    assert "暗示隐藏潜力" not in p2


def test_template_injection_omitted_when_empty() -> None:
    """S68：无模板时保持原行为（不注入空块）。"""
    s = ExplorationStrategy(seed="s", intent_confirmed={"concept": {}})
    p = s.explorer_prompt(0)
    assert "参考叙事模板" not in p
    assert "产出方向卡" in p


def test_template_injection_capped() -> None:
    """S68：注入条数上限 MAX_TEMPLATES（轻量上下文防超预算）。"""
    many = [f"模板{i}" for i in range(20)]
    s = ExplorationStrategy(seed="s", intent_confirmed={"concept": {}}, templates=many)
    p = s.explorer_prompt(0)
    assert "模板0" in p
    assert "模板19" not in p  # 超出上限不注入
    assert p.count("- 模板") <= 12


def test_intent_understander_parses() -> None:
    model = FakeModel(
        '{"concept": {"core": "雨夜侦探抵达雾城", "mood": "阴郁潮湿", '
        '"genre": "悬疑", "seed_position": "开篇"}, '
        '"questions": ["侦探为何来雾城？"]}'
    )
    u = IntentUnderstander(model)
    concept = u.understand("一个侦探来到陌生小城")
    assert concept["concept"]["core"] == "雨夜侦探抵达雾城"
    assert len(concept["questions"]) == 1
    confirm = u.build_confirmation(concept)
    assert "画面核心" in confirm
