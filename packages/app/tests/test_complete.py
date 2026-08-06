"""S13 补全项测试：网络搜索解析 / 时序校验 / L3 模式库 / 关键点图谱 / 氛围注入。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.server.tools_web import (
    WebResult,
    _parse_bing_block,
    _parse_so_block,
    render_results,
    search_web,
)
from anyspark.template import ExternalLibrary, PlotGenerator, PlotResolver, PlotStore

SO_HTML = (
    '<li class="res-list"><h3 class="res-title"><a href="https://example.com/a" '
    'data-mdurl="https://real.example.com/a">雾城历史考据</a></h3>'
    '<div class="res-list-summary">这是一座海边城市，常年有雾。</div></li>'
)
BING_HTML = (
    '<li class="b_algo"><h2><a href="https://cn.bing.com/ck/a?u=https%3A%2F%2Freal.example.com%2Fb">'
    "怀表年代</a></h2><p>十九世纪末的怀表特征。</p></li>"
)


# ---------------------------------------------------------------------------
# 网络搜索解析
# ---------------------------------------------------------------------------
def test_parse_so_block() -> None:
    r = _parse_so_block(SO_HTML)
    assert r is not None
    assert r.title == "雾城历史考据"
    assert r.url == "https://real.example.com/a"  # data-mdurl 优先
    assert "海边城市" in r.snippet


def test_parse_bing_block() -> None:
    r = _parse_bing_block(BING_HTML)
    assert r is not None
    assert r.title == "怀表年代"
    assert r.url == "https://real.example.com/b"  # ck/a 跳转解出真实 URL
    assert "怀表特征" in r.snippet


def test_render_results() -> None:
    results = [WebResult("标题", "https://x.com", "摘要")]
    text = render_results(results, "雾城")
    assert "雾城" in text and "https://x.com" in text
    assert render_results([], "无") == "无结果" or "无结果" in render_results([], "无")


def test_search_web_returns_or_empty() -> None:
    # 真实网络调用（360/Bing），失败应返回空列表而非抛异常
    results = search_web("AnySpark 小说写作", count=3)
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# 时序校验（确定性规则）
# ---------------------------------------------------------------------------
def test_temporal_check_detects_future_entity() -> None:
    from anyspark.graph import GraphStore, GraphVerifier

    g = GraphStore(Path(tempfile.mkdtemp()) / "g.db")
    # 陈渡第 1 章首现，沈歆第 3 章才首现
    g.upsert_entity("main", "陈渡", "角色", [], "主角", "第一章", 1)
    g.upsert_entity("main", "沈歆", "角色", [], "妹妹", "第三章", 3)
    v = GraphVerifier(g)
    # 截止第 2 章的时空点提到沈歆 → 时序警告
    warns = v.check_temporal("main", "陈渡和沈歆在码头见面", up_to_order=2)
    assert any("沈歆" in w and "时序警告" in w for w in warns)
    # 截止第 3 章则正常
    assert v.check_temporal("main", "陈渡和沈歆见面", up_to_order=3) == []
    # 未提及实体不触发
    assert v.check_temporal("main", "今天下雨", up_to_order=2) == []


# ---------------------------------------------------------------------------
# L3 外部模式库
# ---------------------------------------------------------------------------
def test_external_library_import_and_merge() -> None:
    lib = ExternalLibrary(Path(tempfile.mkdtemp()) / "t.db")
    assert len(lib.all()) >= 5  # L2 默认库
    t = lib.import_template(
        "双城镜像",
        "两座城市互为镜像，主角在二者间穿梭",
        granularity="全书",
        position="发展",
        function="主线",
        params=["镜像关系"],
    )
    assert t.layer == "external"
    ext = lib.list_external()
    assert len(ext) == 1 and ext[0].name == "双城镜像"
    assert any(x.name == "双城镜像" for x in lib.all())  # 合并
    lib.delete("双城镜像")
    assert lib.list_external() == []


# ---------------------------------------------------------------------------
# 关键点图谱
# ---------------------------------------------------------------------------
class FakePlotModel:
    model_name = "fake-plot"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='[{"category": "主线冲突", "content": "陈渡追查父亲死因", "chapter_ref": "第3章"},'
            '{"category": "伏笔", "content": "怀表刻着沈青山"}]'
        )


class FakeResolveModel:
    """回收响应：本章揭开了"怀表刻着沈青山"。"""

    model_name = "fake-resolve"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='{"resolved": [{"content": "怀表刻着沈青山", '
            '"evidence": "本章发现怀表内部刻着沈青山的名字"}]}'
        )


def test_plot_generate_and_store() -> None:
    store = PlotStore(Path(tempfile.mkdtemp()) / "p.db")
    gen = PlotGenerator(FakePlotModel())
    points = gen.generate("main", store, "雾城侦探故事")
    assert len(points) == 2
    assert points[0].category == "主线冲突"
    listed = store.list_points()
    assert len(listed) == 2
    # 状态流转 + 关注度（S17：attention 字段 + update 取代 update_status）
    p = store.update(listed[0].id, status="resolved")
    assert p is not None and p.status == "resolved"
    p2 = store.update(listed[1].id, attention="ignore")
    assert p2 is not None and p2.attention == "ignore"
    rendered = store.render()
    assert "关键点图谱" in rendered and "✓" in rendered
    # ignore 条目不注入
    assert listed[1].content not in rendered
    store.delete(listed[1].id)
    assert len(store.list_points()) == 1


def test_plot_auto_resolve() -> None:
    """S17 伏笔自动回收：章节文本匹配揭开 open 关键点 → resolved；未涉及的不动。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "r.db")
    gen = PlotGenerator(FakePlotModel())
    gen.generate("main", store, "")
    resolver = PlotResolver(FakeResolveModel())
    resolved = resolver.resolve(
        "main", "第4章", "怀表内部刻着沈青山的名字，陈渡终于明白了。", store
    )
    assert resolved == ["怀表刻着沈青山"]
    points = {p.content: p for p in store.list_points()}
    assert points["怀表刻着沈青山"].status == "resolved"
    assert points["怀表刻着沈青山"].chapter_ref == "第4章"
    # 未涉及的伏笔仍 open
    assert points["陈渡追查父亲死因"].status == "open"


def test_plot_resolve_ignores_attention_ignore() -> None:
    """attention=ignore 的条目不参与回收（用户标注不需要=不惦记）。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "i.db")
    gen = PlotGenerator(FakePlotModel())
    gen.generate("main", store, "")
    for p in store.list_points():
        if p.content == "怀表刻着沈青山":
            store.update(p.id, attention="ignore")
    resolver = PlotResolver(FakeResolveModel())
    resolved = resolver.resolve("main", "第4章", "怀表内部刻着沈青山的名字", store)
    assert resolved == []
    points = {p.content: p for p in store.list_points()}
    assert points["怀表刻着沈青山"].status == "open"  # ignore 不回收


# ---------------------------------------------------------------------------
# 氛围注入（S15 起归属 align.mood——B 类交互载体与 agency/bias 同包）
# ---------------------------------------------------------------------------
def test_mood_block() -> None:
    from anyspark.align import build_mood_block

    assert build_mood_block({}) == ""
    assert build_mood_block(None) == ""
    # S50：数值语义化——80→较强，30→轻微（裸数值不进模型）
    block = build_mood_block({"tension": 80, "calm": 30})
    assert "紧张感：较强" in block and "舒缓感：轻微" in block
    assert "80/100" not in block and "30/100" not in block  # 工程量纲不裸传
    # 越界钳制：500→强烈（不出现 500/100）
    b2 = build_mood_block({"dread": 500})
    assert "压抑感：强烈" in b2 and "500" not in b2
    # 注入块标题（机制 4：本段氛围要求）
    assert "本段氛围要求" in block
