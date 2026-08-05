"""S48-P2 领域工具：图谱查证/伏笔登记/计划推进/设定查证（agent 可自主调用）测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from anyspark.align.plan import StoryPlanStore
from anyspark.align.worldsettings import WorldSettingStore
from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.graph import GraphStore
from anyspark.server.app import build_app
from anyspark.server.tools_domain import (
    make_graph_query_implementer,
    make_plan_implementer,
    make_plot_implementer,
    make_setting_implementer,
)
from anyspark.template.plot import PlotStore


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Any, name: str = "t", **kwargs: Any) -> ToolResult:
    """直接调用 implementer（模拟 Agent 工具调用）。"""
    spec = ToolSpec(name=name, description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


def test_graph_query_finds_entity_with_state() -> None:
    db = _db()
    graph = GraphStore(db)
    graph.upsert_entity("main", "陈渡", "角色", aliases=["陈侦探"], description="雾城侦探")
    graph.upsert_entity("main", "雾城", "地点", description="江边之城")
    _, impl = make_graph_query_implementer(graph)
    r = _call(impl, query="陈渡")
    assert r.ok is True
    assert "陈渡" in r.content
    assert "角色" in r.content
    # 别名模糊命中
    r2 = _call(impl, query="陈侦探")
    assert "陈渡" in r2.content
    # 未找到
    r3 = _call(impl, query="不存在的人")
    assert r3.ok is False


def test_plot_register_and_list() -> None:
    plots = PlotStore(_db())
    specs, impls = make_plot_implementer(plots)
    register, list_impl = impls
    assert len(specs) == 2

    r = _call(register, content="怀表背面刻有一串数字", priority="must")
    assert r.ok is True
    assert "主线承诺" in r.content
    r2 = _call(register, content="雾城钟楼的地基", priority="soft")
    assert r2.ok is True

    rl = _call(list_impl)
    assert "怀表背面刻有一串数字" in rl.content  # must 展开列出
    assert "另有 1 条细节线索开放中" in rl.content  # soft 只汇总数量（S31 设计）


def test_plan_list_and_mark_done() -> None:
    plans = StoryPlanStore(_db())
    plans.add(1, "第一章 雾城", "雨夜抵达")
    plans.add(2, "第二章 灯塔", "发现怀表")
    _, impls = make_plan_implementer(plans)
    list_impl, done_impl = impls

    rl = _call(list_impl)
    assert "第一章 雾城" in rl.content
    assert "第二章 灯塔" in rl.content

    rd = _call(done_impl, title="第一章 雾城")
    assert rd.ok is True
    assert plans.list("main")[0].status == "done"
    # 未找到
    rnf = _call(done_impl, title="不存在的章")
    assert rnf.ok is False


def test_read_setting() -> None:
    settings = WorldSettingStore(_db())
    settings.add("雾城侦探，右手有旧伤。", "人物卡", "陈渡")
    settings.add("越接近诡异，越要审视自身。", "规则", "猎人准则")
    _, impl = make_setting_implementer(settings)

    r = _call(impl, keyword="假死")
    assert r.ok is False
    r2 = _call(impl, keyword="陈渡")
    assert "雾城侦探" in r2.content
    r3 = _call(impl, keyword="列出")
    assert "人物卡" in r3.content and "规则" in r3.content


def test_chat_enable_domain_switch() -> None:
    """enable_domain 默认开（注册领域工具）；false 时 agent 看不到（tools 为空）。"""

    class _ProbeModel:
        model_name = "probe"

        def __init__(self) -> None:
            self.last_tools: list[str] = []

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.last_tools = [getattr(t, "name", "") for t in tools or []]
            return ModelOutput(text="已写《第1章》并保存。")

    db = _db()
    model = _ProbeModel()

    app = build_app(model=model, db_path=db)
    from fastapi.testclient import TestClient

    c = TestClient(app)
    # 默认：领域工具已注册
    c.post("/api/chat", json={"message": "写《第1章》20字：雨夜。"})
    assert "graph_query" in model.last_tools
    assert "plot_register" in model.last_tools
    assert "plan_list" in model.last_tools
    assert "read_setting" in model.last_tools
    # 关闭：领域工具不注册，写作工具仍在
    c.post(
        "/api/chat",
        json={"message": "写《第2章》20字：灯塔。", "enable_domain": False},
    )
    assert "graph_query" not in model.last_tools
    assert "write_chapter" in model.last_tools
