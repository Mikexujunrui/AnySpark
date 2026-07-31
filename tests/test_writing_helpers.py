"""Tests for writing.py pure helpers — the cheapest way to lift writing.py's
7% coverage (M9.3 leftover: coverage 40% target)."""

import json
from types import SimpleNamespace

from tools.impl.writing import (
    _build_graph_insight_report,
    _build_scope_report,
    _format_chapter_result,
    _guard_new_chapter_target,
    _post_write_constraint_check,
    _requested_regular_chapter_index,
)

# ── _requested_regular_chapter_index ──


def test_chapter_index_from_args():
    assert _requested_regular_chapter_index({"chapter_index": 3}) == 3


def test_chapter_index_extra_returns_none():
    assert _requested_regular_chapter_index({"is_extra": True, "chapter_index": 3}) is None


def test_chapter_index_zero_or_negative_returns_none():
    assert _requested_regular_chapter_index({"chapter_index": 0}) is None
    assert _requested_regular_chapter_index({"chapter_index": -2}) is None


def test_chapter_index_invalid_type_returns_none():
    assert _requested_regular_chapter_index({"chapter_index": "abc"}) is None


def test_chapter_index_from_instruction_text():
    assert _requested_regular_chapter_index({}, "写第 12 章的内容") == 12


def test_chapter_index_from_title():
    assert _requested_regular_chapter_index({"chapter_title": "第5章 真相"}) == 5


def test_chapter_index_ignores_word_count_distraction():
    # "写一章 2500 字" must NOT be read as chapter #2500.
    assert _requested_regular_chapter_index({}, "写一章 2500 字") is None


def test_chapter_index_no_match():
    assert _requested_regular_chapter_index({}, "随便写点") is None


# ── _build_scope_report ──


def _ent(name: str, reason: str = "manual"):
    return SimpleNamespace(entity_name=name, reason=reason)


def test_scope_report_empty():
    assert _build_scope_report(SimpleNamespace(
        characters=[], locations=[], concepts=[], forbidden_characters=[],
        chapter_outline="", writing_rules="",
    )) == ""


def test_scope_report_characters_and_outline():
    report = _build_scope_report(SimpleNamespace(
        characters=[_ent("哈利"), _ent("赫敏")],
        locations=[_ent("霍格沃茨")],
        concepts=[],
        forbidden_characters=["伏地魔"],
        chapter_outline="这是一个比较长的大纲描述",
        writing_rules="规则内容",
    ))
    assert "哈利" in report and "赫敏" in report
    assert "地点(1): 霍格沃茨" in report
    assert "禁止出场: 伏地魔" in report
    assert "大纲:" in report
    assert "角色(2)" in report


def test_scope_report_truncates_long_outline():
    report = _build_scope_report(SimpleNamespace(
        characters=[], locations=[], concepts=[], forbidden_characters=[],
        chapter_outline="长" * 100, writing_rules="",
    ))
    assert "..." in report


# ── _format_chapter_result ──


def test_format_chapter_result_basic(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书", "")
    json_store.add_chapter(book["id"], "第一章", "内容内容")
    result = _format_chapter_result(book["id"], "ch1", "第一章", "内容内容")
    assert "✅ 章节: 第一章" in result
    assert "共1章" in result or "进度:" in result
    assert "内容预览: 内容内容" in result


def test_format_chapter_result_with_scope(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书2", "")
    result = _format_chapter_result(book["id"], "ch2", "第二章", "x" * 200, scope_report="📋 知识范围报告:\n  角色(1)")
    assert "📋 知识范围报告" in result
    assert "..." in result  # long content preview truncated


# ── _guard_new_chapter_target ──


def test_guard_allows_new_chapter(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书3", "")
    # No chapters yet → no guard hit.
    assert _guard_new_chapter_target(book["id"], {"chapter_index": 1}) is None


def test_guard_blocks_existing_chapter(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书4", "")
    json_store.add_chapter(book["id"], "第一章 起点", "内容")
    guard = _guard_new_chapter_target(book["id"], {"chapter_index": 1})
    assert guard is not None
    assert guard["type"] == "writing_result"
    assert "原稿保护" in guard["text"]
    assert guard["saved"] is False


# ── _build_graph_insight_report ──


class _FakeKB:
    def __init__(self, insights):
        self._insights = insights

    def get_graph_insights(self):
        return self._insights


def test_graph_insight_empty():
    assert _build_graph_insight_report(_FakeKB({}), SimpleNamespace(characters=[])) == ""


def test_graph_insight_errors_gracefully():
    class Boom:
        def get_graph_insights(self):
            raise RuntimeError("store unavailable")

    assert _build_graph_insight_report(Boom(), SimpleNamespace(characters=[])) == ""


def test_graph_insight_forgotten_and_foreshadow():
    kb = _FakeKB({
        "forgotten_characters": [{"name": "张三"}, {"name": "李四"}],
        "unresolved_foreshadows": [{"text": "那把钥匙到底是谁的？"}],
        "bridge_characters": [{"entity_name": "王五"}],
        "underutilized_locations": ["地窖"],
    })
    report = _build_graph_insight_report(kb, SimpleNamespace(characters=[_ent("张三")]))
    assert "遗忘角色" in report
    assert "李四" in report  # not in scope → reported
    assert "待回收伏笔" in report
    assert "桥接角色" in report
    assert "未使用地点" in report


def test_graph_insight_scope_character_excluded():
    kb = _FakeKB({"forgotten_characters": [{"name": "张三"}], "unresolved_foreshadows": [], "bridge_characters": []})
    report = _build_graph_insight_report(kb, SimpleNamespace(characters=[_ent("张三")]))
    # 张三 is in scope → not reported as forgotten
    assert "遗忘角色" not in report


# ── _post_write_constraint_check ──


def test_post_write_constraint_check_no_constraints(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("约束检查书", "")
    kb = _FakeKB({})
    assert _post_write_constraint_check(kb, book["id"]) == ""


def test_post_write_constraint_check_store_error_returns_empty():
    # ConstraintStore requires a real kb; simulate failure path.
    assert _post_write_constraint_check(None, "whatever") == ""


# ── knowledge.py _call_edit_llm ──


def test_call_edit_llm_returns_result():
    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        return "改写后的正文内容"

    assert _call_edit_llm(fake_chat, "prompt", "system") == "改写后的正文内容"


def test_call_edit_llm_empty_response_blocked():
    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        return ""

    result = _call_edit_llm(fake_chat, "p", "s")
    assert result["blocked_reason"] == "空响应"


def test_call_edit_llm_refusal_detected():
    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        return "抱歉，我无法协助改写这段内容"

    result = _call_edit_llm(fake_chat, "p", "s")
    assert "模型拒绝" in result["blocked_reason"]


def test_call_edit_llm_policy_error_blocked():
    import httpx
    from openai import APIError

    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        req = httpx.Request("POST", "http://example.invalid")
        raise APIError("api error", request=req, body={"message": "content filter triggered"})

    result = _call_edit_llm(fake_chat, "p", "s")
    assert "API审查" in result["blocked_reason"]


def test_call_edit_llm_generic_error_reraises():
    import pytest

    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        raise RuntimeError("connection refused")

    with pytest.raises(RuntimeError):
        _call_edit_llm(fake_chat, "p", "s")


def test_call_edit_llm_content_policy_generic_error():
    from tools.impl.knowledge import _call_edit_llm

    def fake_chat(prompt, system, temperature, task):
        raise RuntimeError("content policy violation detected")

    result = _call_edit_llm(fake_chat, "p", "s")
    assert "审查拦截" in result["blocked_reason"]


# ── generation.py pure helpers ──


def test_coerce_to_dict_none():
    from tools.impl.generation import _coerce_to_dict

    assert _coerce_to_dict(None) == {}
    assert _coerce_to_dict(123) == {}
    assert _coerce_to_dict([]) == {}


def test_coerce_to_dict_passthrough():
    from tools.impl.generation import _coerce_to_dict

    assert _coerce_to_dict({"a": 1}) == {"a": 1}


def test_coerce_to_dict_json_string():
    from tools.impl.generation import _coerce_to_dict

    assert _coerce_to_dict('{"a": 2}') == {"a": 2}
    assert _coerce_to_dict("not json") == {}
    assert _coerce_to_dict("  ") == {}


def test_parse_progressive_result_valid():
    from tools.impl.generation import _parse_progressive_result

    result = _parse_progressive_result('```json\n{"new_entities": [{"name": "x"}]}\n```')
    assert result["new_entities"] == [{"name": "x"}]


def test_parse_progressive_result_invalid():
    from tools.impl.generation import _parse_progressive_result

    result = _parse_progressive_result("garbage")
    assert result["new_entities"] == []
    assert result["relations"] == []


def test_match_extra_outline_regular_chapter():
    from tools.impl.generation import _match_extra_outline

    # Not extra and no 番外 keyword → None
    assert _match_extra_outline("book_x", "写正文", False) is None


def test_match_extra_outline_explicit_number(tmp_data_dir):
    from data.json_store import json_store
    from tools.impl.generation import _match_extra_outline

    book = json_store.create_book("番外匹配书", "")
    json_store.save_outline(book["id"], {"extras": [{"title": "番外一"}, {"title": "番外二"}]})
    result = _match_extra_outline(book["id"], "写番外 2", True)
    assert result is not None
    assert result["extra_num"] == 2
    assert result["outline_entry"]["title"] == "番外二"


def test_match_extra_outline_auto_number(tmp_data_dir):
    from data.json_store import json_store
    from tools.impl.generation import _match_extra_outline

    book = json_store.create_book("番外自动书", "")
    result = _match_extra_outline(book["id"], "写个番外吧", True)
    assert result is not None
    assert result["extra_num"] == 1


# ── extractor.py proposal serialization ──


def test_proposal_roundtrip():
    from core.extractor import _proposal_to_dict, proposal_from_dict
    from core.knowledge import Entity, Foreshadow, KnowledgeProposal, Relation, RelationType

    p = KnowledgeProposal(
        entities=[Entity(id="e1", type="character", name="哈利", aliases=["哈"], data={"age": 11})],
        relations=[Relation(id="r1", from_entity="e1", to_entity="e2", type=RelationType.KNOWS)],
        foreshadows=[Foreshadow(id="f1", text="钥匙之谜", hint="暗示")],
    )
    d = _proposal_to_dict(p)
    p2 = proposal_from_dict(d)
    assert len(p2.entities) == 1
    assert p2.entities[0].name == "哈利"
    assert p2.entities[0].aliases == ["哈"]
    assert p2.relations[0].from_entity == "e1"
    assert p2.relations[0].type == RelationType.KNOWS
    assert p2.foreshadows[0].text == "钥匙之谜"


def test_proposal_from_dict_empty_and_invalid():
    from core.extractor import proposal_from_dict

    p = proposal_from_dict({})
    assert p.entities == [] and p.relations == [] and p.foreshadows == []

    # Invalid relation type falls back to KNOWS
    p2 = proposal_from_dict({"relations": [{"from": "a", "to": "b", "type": "NOT_A_TYPE"}]})
    assert p2.relations[0].type.value == "knows"


def test_parse_single_entity():
    from core.extractor import _parse_single_entity

    result = _parse_single_entity('{"data": {"name": "张三", "age": 30}}')
    assert result["name"] == "张三"

    # Fallback: whole doc is the data
    result2 = _parse_single_entity('{"name": "李四"}')
    assert result2["name"] == "李四"

    # Invalid JSON → empty
    assert _parse_single_entity("not json at all") == {}


def test_parse_batch_result_mapping():
    from core.extractor import _parse_batch_result

    entities = [
        SimpleNamespace(id="e1", type="character", name="哈利", aliases=[], data={}),
        SimpleNamespace(id="e2", type="location", name="霍格沃茨", aliases=[], data={}),
    ]
    result = _parse_batch_result('{"entities": [{"name": "哈利"}, {"name": "霍格沃茨"}]}', entities)
    assert len(result) == 2
    assert result[0].name == "哈利"
    assert result[0].type == "character"


def test_parse_batch_result_invalid_json_falls_back(monkeypatch):
    from core import extractor
    from core.extractor import _parse_batch_result

    # Invalid JSON fallback calls _extract_one → chat(); stub it out.
    def fake_chat(prompt, system, temperature=0.1, task="extraction"):
        return '{"data": {"basic": {"name": "哈利"}}}'

    monkeypatch.setattr(extractor, "chat", fake_chat)

    entities = [
        SimpleNamespace(id="e1", type="character", name="哈利", aliases=[], data={}),
    ]
    result = _parse_batch_result("garbage", entities)
    assert len(result) == 1
    assert result[0].name == "哈利"


def test_parse_batch_result_unknown_name_skipped():
    from core.extractor import _parse_batch_result

    entities = [
        SimpleNamespace(id="e1", type="character", name="哈利", aliases=[], data={}),
    ]
    result = _parse_batch_result('{"entities": [{"name": "不存在的人"}]}', entities)
    assert len(result) == 1  # only the fallback copy of 哈利
    assert result[0].name == "哈利"


# ── extractor.py _parse_proposal ──


def test_parse_proposal_valid():
    from core.extractor import _parse_proposal

    resp = json.dumps({
        "entities": [
            {"type": "character", "name": "哈利", "data": {"basic": {"name": "哈利", "age": 11}}},
        ],
        "relations": [
            {"from": "e1", "to": "e2", "type": "knows"},
        ],
        "foreshadows": [
            {"text": "钥匙之谜", "hint": "暗示"},
        ],
    })
    p = _parse_proposal(resp)
    assert len(p.entities) == 1
    assert p.entities[0].name == "哈利"
    assert len(p.relations) == 1
    assert p.relations[0].type.value == "knows"
    assert len(p.foreshadows) == 1
    assert p.foreshadows[0].text == "钥匙之谜"


def test_parse_proposal_invalid_json():
    from core.extractor import _parse_proposal

    p = _parse_proposal("not json")
    assert p.entities == [] and p.relations == [] and p.foreshadows == []


def test_parse_proposal_with_fenced_code():
    from core.extractor import _parse_proposal

    p = _parse_proposal('```json\n{"entities": [{"name": "张三", "type": "character"}]}\n```')
    assert len(p.entities) == 1
    assert p.entities[0].name == "张三"


def test_get_extraction_system(monkeypatch):
    from core import extractor

    monkeypatch.setattr(extractor, "load_prompt", lambda name: f"模板:{name}")
    assert extractor._get_extraction_system() == "模板:extraction_system"
