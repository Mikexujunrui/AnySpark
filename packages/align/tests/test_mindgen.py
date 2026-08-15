"""anyspark.align.mindgen — 心智生成端测试（S61：档位 L2 建议 + L3 生成）。"""

from __future__ import annotations

from anyspark.align import AgencyLevel, ManualEntry
from anyspark.align.mindgen import (
    build_agency_gen_prompt,
    build_agency_suggest_prompt,
    parse_agency_gen_result,
    parse_agency_suggest_result,
)


def _levels() -> list[AgencyLevel]:
    return [
        AgencyLevel(
            id="default-0",
            name="只听写",
            description="严格按原文输出",
            temperature=0.2,
            order=0,
        ),
        AgencyLevel(
            id="default-4",
            name="自主发挥",
            description="自行探索写作",
            temperature=1.0,
            order=4,
        ),
    ]


def test_suggest_prompt_includes_entries_and_levels() -> None:
    entries = [ManualEntry(content="先给方案再动笔，不要直接写", category="collab")]
    prompt = build_agency_suggest_prompt(entries, _levels())
    assert "先给方案再动笔" in prompt
    assert "default-0" in prompt and "只听写" in prompt
    assert "default-4" in prompt


def test_suggest_prompt_no_entries() -> None:
    prompt = build_agency_suggest_prompt([], _levels())
    assert "无协作偏好条目" in prompt


def test_parse_suggest_result_plain() -> None:
    raw = '{"level_id": "default-4", "reason": "用户要放手", "note": ""}'
    res = parse_agency_suggest_result(raw)
    assert res["level_id"] == "default-4"
    assert res["reason"] == "用户要放手"


def test_parse_suggest_result_fenced() -> None:
    raw = '```json\n{"level_id": "default-0", "reason": "要确认", "note": "新建档位：xxx"}\n```'
    res = parse_agency_suggest_result(raw)
    assert res["level_id"] == "default-0"
    assert res["note"].startswith("新建档位")


def test_parse_suggest_result_garbage() -> None:
    res = parse_agency_suggest_result("抱歉，我无法完成")
    assert res == {"level_id": "", "reason": "", "note": ""}


def test_gen_prompt_contains_description_and_n() -> None:
    prompt = build_agency_gen_prompt("多给方案别直接写", 2)
    assert "多给方案别直接写" in prompt
    assert "2" in prompt


def test_parse_gen_result_valid() -> None:
    raw = (
        '[{"name": "自主推进", "description": "AI 自主续写推进。", "temperature": 0.9},'
        '{"name": "全程确认", "description": "每步先给方案。", "temperature": 0.3}]'
    )
    out = parse_agency_gen_result(raw)
    assert len(out) == 2
    assert out[0]["name"] == "自主推进"
    assert out[0]["temperature"] == 0.9


def test_parse_gen_result_temperature_clamped() -> None:
    raw = (
        '[{"name": "x", "description": "y", "temperature": 3.5},'
        ' {"name": "z", "description": "w", "temperature": "bad"}]'
    )
    out = parse_agency_gen_result(raw)
    assert out[0]["temperature"] == 1.0  # 钳制上限
    assert out[1]["temperature"] == 0.7  # 非法 → 默认


def test_parse_gen_result_skips_invalid() -> None:
    raw = (
        '[{"name": "", "description": "缺名"},'
        ' {"name": "正常", "description": "OK", "temperature": 0.5}]'
    )
    out = parse_agency_gen_result(raw)
    assert len(out) == 1
    assert out[0]["name"] == "正常"
