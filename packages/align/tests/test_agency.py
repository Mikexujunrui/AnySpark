"""anyspark.align — 能动性协议（机制 2）+ AI 倾向档案（§2）测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import (
    AGENCY_LEVELS,
    AgencyStore,
    BiasStore,
    build_agency_block,
    parse_agency_declaration,
    temperature_for,
)


def test_agency_levels_defaults() -> None:
    assert len(AGENCY_LEVELS) == 5
    assert [lv["level"] for lv in AGENCY_LEVELS] == [0, 1, 2, 3, 4]
    names = [lv["name"] for lv in AGENCY_LEVELS]
    assert names[0] == "只听写" and names[4] == "自主发挥"


def test_temperature_mapping() -> None:
    assert temperature_for(0) == 0.2
    assert temperature_for(2) == 0.6
    assert temperature_for(4) == 1.0
    assert temperature_for(9) == 0.7  # 未知档位回退默认


def test_build_agency_block() -> None:
    b = build_agency_block(3)
    assert "能动级别 3" in b and "建议扩展" in b
    assert build_agency_block(9) == ""


def test_agency_store_clamps_and_adjusts() -> None:
    store = AgencyStore(Path(tempfile.mkdtemp()) / "agency.db")
    assert store.get_level() == 2  # 默认
    assert store.set_level(9) == 4  # 上限钳制
    assert store.set_level(-3) == 0  # 下限钳制
    store.set_level(2)
    assert store.adjust(+1) == 3  # 接受=升级
    store.set_level(0)
    assert store.adjust(-1) == 0  # 拒绝=降级（下限 0 不动）
    store.set_level(4)
    assert store.adjust(+1) == 4  # 上限 4 不动


def test_parse_agency_declaration() -> None:
    assert parse_agency_declaration("【能动级别: 3】继续写") == 3
    assert parse_agency_declaration("【能动级别：1】按骨架填") == 1
    assert parse_agency_declaration("没有声明") is None


def test_bias_store_roundtrip() -> None:
    store = BiasStore(Path(tempfile.mkdtemp()) / "bias.db")
    assert store.render() == ""  # 空档案不注入
    e = store.add("我这个模型写对话偏克制", source="ai")
    assert e["content"] == "我这个模型写对话偏克制"
    e2 = store.add("可以更大胆一些", source="user")
    entries = store.list()
    assert len(entries) == 2
    block = store.render()
    assert "AI 倾向档案" in block and "写对话偏克制" in block and "AI 自述" in block
    store.delete(e2["id"])
    assert len(store.list()) == 1
