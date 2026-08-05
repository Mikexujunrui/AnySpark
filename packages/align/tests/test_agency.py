"""anyspark.align — 能动性协议（机制 2，S35 档位记录集）+ AI 倾向档案（§2）测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import (
    DEFAULT_ID,
    DEFAULT_LEVELS,
    AgencyLevel,
    AgencyStore,
    BiasStore,
    build_agency_block,
    parse_agency_declaration,
    temperature_for,
)


def test_agency_levels_defaults() -> None:
    """S35：默认五级档位作为稳定基线（id 固定）。"""
    assert len(DEFAULT_LEVELS) == 5
    ids = [lv["id"] for lv in DEFAULT_LEVELS]
    assert ids == [f"default-{i}" for i in range(5)]
    assert DEFAULT_LEVELS[0]["name"] == "只听写"
    assert DEFAULT_LEVELS[4]["name"] == "自主发挥"


def test_temperature_mapping() -> None:
    """温度入档：默认档位 by 数字查表兼容 + 记录自带温度。"""
    assert temperature_for(0) == 0.2
    assert temperature_for(4) == 1.0
    assert temperature_for(9) == 0.7  # 未知数字回退默认
    lv = AgencyLevel(id="custom-1", name="自定义", description="", temperature=0.55, order=5)
    assert temperature_for(lv) == 0.55


def test_build_agency_block() -> None:
    """注入块：数字（默认档位 by order）/ 记录。职责边界：档位只含能动性，无心智内容。"""
    b = build_agency_block(3)
    assert "能动级别 3" in b and "建议扩展" in b
    assert build_agency_block(9) == ""
    lv = AgencyLevel(
        id="x",
        name="大胆但不血腥",
        description="自由发挥但规避血腥描写。",
        temperature=0.9,
        order=5,
    )
    b2 = build_agency_block(lv)
    assert "大胆但不血腥" in b2 and "用户心智" not in b2


def test_agency_store_crud_and_reset() -> None:
    """S35 核心：增删改 + 恢复默认 + adjust 按排序位。"""
    store = AgencyStore(Path(tempfile.mkdtemp()) / "agency.db")
    # 默认 5 档 + 当前 default-2
    assert len(store.list_levels()) == 5
    assert store.get_current().id == DEFAULT_ID
    # 增：自定义档位追加末尾
    lv = store.add_level("大胆但不血腥", "自由发挥但规避血腥描写。", 0.9)
    levels = store.list_levels()
    assert len(levels) == 6
    assert levels[-1].id == lv.id and levels[-1].order == 5
    # 选：切到自定义档位
    store.set_current(lv.id)
    assert store.get_current().id == lv.id
    # 改：名称/描述/温度
    store.update_level(lv.id, name="大胆克制", description="发挥但克制", temperature=0.8)
    got = store.get_level(lv.id)
    assert got is not None and got.name == "大胆克制" and got.temperature == 0.8
    # adjust 按排序位：自定义档位 order=5 → 升到 6 被钳制在末尾
    assert store.adjust(+1) == lv.id
    store.set_current("default-1")
    assert store.adjust(+1) == "default-2"  # 升一级
    # 删：删自定义档位
    assert store.delete_level(lv.id)
    assert store.get_level(lv.id) is None
    assert len(store.list_levels()) == 5
    # 恢复默认：自定义档位清除 + 当前回落 default-2
    store.add_level("临时档", "测试", 0.5)
    store.set_current("default-4")
    store.reset_defaults()
    assert len(store.list_levels()) == 5
    assert store.get_current().id == DEFAULT_ID
    assert all(x.is_default for x in store.list_levels())


def test_agency_delete_keeps_at_least_one() -> None:
    store = AgencyStore(Path(tempfile.mkdtemp()) / "agency.db")
    # 删到只剩 1 条时拒绝再删
    for lv in list(store.list_levels())[1:]:
        store.delete_level(lv.id)
    assert len(store.list_levels()) == 1
    assert not store.delete_level(store.list_levels()[0].id)
    assert len(store.list_levels()) == 1


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
