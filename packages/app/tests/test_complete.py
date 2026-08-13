"""S13 补全项测试：网络搜索解析 / 时序校验 / L3 模式库 / 关键点图谱 / 氛围注入。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.server.tools_fetch import html_to_text
from anyspark.server.tools_web import (
    WebResult,
    _decode_bing_target,
    _detect_language,
    _extract_mcp_text,
    _is_junk,
    _mcp_provider_order,
    _parse_bing_block,
    _parse_exa_text,
    _parse_parallel_text,
    _parse_so_block,
    _prefer_engine,
    _results_relevant,
    render_results,
    search_web,
)
from anyspark.template import ExternalLibrary, PlotGenerator, PlotResolver, PlotStore

SO_HTML = (
    '<li class="res-list"><h3 class="res-title"><a href="https://example.com/a" '
    'data-mdurl="https://real.example.com/a">雾城历史考据</a></h3>'
    '<div class="res-list-summary">这是一座海边城市，常年有雾。</div></li>'
)
# S111 真实 360 摘要结构：容器 `>` 前缀 + 高亮 <em> + </span> 后的 g-linkinfo（末尾域名垃圾源）
SO_HTML_REAL = (
    '<li class="res-list"><h3 class="res-title"><a href="https://example.com/a" '
    'data-mdurl="https://real.example.com/a">雾城历史考据</a></h3>'
    '<div class="res-list-summary">关注距离<em>2026年诺贝尔文学奖</em>揭晓还有数月。</span>'
    '<p class="g-linkinfo"><cite><a href="https://www.so.com/link?m=xxx">news.sina.cn</a></cite></p></div></li>'
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


def test_so_summary_no_prefix_garbage() -> None:
    """S111：真实 360 摘要容器带 `>` 前缀 + g-linkinfo 尾部，不应残留进 snippet。"""
    r = _parse_so_block(SO_HTML_REAL)
    assert r is not None
    assert r.snippet.startswith("关注")  # 容器 `>` 前缀被吃掉，无行首垃圾
    assert ">关注" not in r.snippet
    assert "news.sina.cn" not in r.snippet  # g-linkinfo 域名不混入
    assert "2026年诺贝尔文学奖" in r.snippet  # <em> 高亮内容保留


def test_detect_language() -> None:
    assert _detect_language("2026年诺贝尔文学奖") == "zh"
    assert _detect_language("Laszlo Krasznahorkai Nobel Prize") == "en"


def test_prefer_engine() -> None:
    assert _prefer_engine("2026年诺贝尔文学奖") == "so"  # 中文 → 360
    assert _prefer_engine("quantum computing") == "bing"  # 英文 → Bing
    assert _prefer_engine("quantum computing", "zh") == "so"  # 显式语言覆盖
    assert _prefer_engine("中文", "en") == "bing"


def test_decode_bing_target() -> None:
    # 旧格式：URL 编码
    assert _decode_bing_target("https%3A%2F%2Freal.example.com%2Fb") == "https://real.example.com/b"
    # 新格式：base64（实测 cn.bing 的 ck/a 链接）
    import base64 as b64

    target = "https://www.reddit.com/r/fantasyfootball/hot/"
    enc = b64.b64encode(target.encode()).decode().rstrip("=")
    assert _decode_bing_target(enc) == target
    # 无法解码 → 空
    assert _decode_bing_target("not-a-url-or-base64!!") == ""


def test_results_relevant() -> None:
    # 相关：结果标题含 query 的 ≥2 个实词
    assert _results_relevant(
        "quantum computing breakthrough",
        [WebResult("Google's Quantum Computing Breakthrough", "https://x.com", "s")],
    )
    # 跑偏：结果与 query 无共享词（cn.bing 英文长查询偶发现象）
    assert not _results_relevant(
        "Laszlo Krasznahorkai Nobel Prize",
        [WebResult("/r/fantasyfootball - Good For Your Season", "https://reddit.com", "s")],
    )
    # 中文查询（无实词）不拦
    assert _results_relevant(
        "2026年诺贝尔文学奖", [WebResult("新浪新闻", "https://news.sina.cn", "s")]
    )
    # 空结果 → 不相关
    assert not _results_relevant("anything", [])


def test_is_junk() -> None:
    # 低质域名剔除
    assert _is_junk("https://ai.so.com/search/abc", "x")
    assert _is_junk("https://wenku.so.com/d/123", "x")
    assert _is_junk("https://www.ftxia.com/item.htm?id=1", "x")
    assert _is_junk("https://www.douyin.com/qishui/song/1", "x")
    assert _is_junk("https://www.so.com/s?q=重复搜索", "x")  # 站内重复搜索
    # 正常结果不误杀
    assert not _is_junk("https://news.sina.cn/sx/2026-04-09/a.dhtml", "x")
    assert not _is_junk("https://en.wikipedia.org/wiki/2026", "x")


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
    # 真实网络调用（MCP/360/Bing），失败应返回空列表而非抛异常
    results = search_web("AnySpark 小说写作", count=3)
    assert isinstance(results, list)
    # S111：低质过滤后不应出现问答框/文库
    assert not any("ai.so.com" in r.url or "wenku.so.com" in r.url for r in results)


# ---------------------------------------------------------------------------
# S112 MCP 层解析（Exa/Parallel 公开端点，无密钥）
# ---------------------------------------------------------------------------
EXA_TEXT = (
    "Title: 2026 Nobel Prize in Literature\n"
    "URL: https://en.wikipedia.org/wiki/2026_Nobel_Prize_in_Literature\n"
    "Published: N/A\n"
    "Author: N/A\n"
    "Highlights:\n"
    "The 2026 Nobel Prize will be announced on 8 October.\n"
    "\n---\n\n"
    "Title: 加拿大文学双星领跑\n"
    "URL: https://hea.china.com/articles/20260413.html\n"
    "Published: 2026-04-13T00:00:00.000Z\n"
    "Author: 看点时报\n"
    "Highlights:\n"
    "距离2026年诺奖揭晓尚有数月。\n"
)


def test_parse_exa_text() -> None:
    results = _parse_exa_text(EXA_TEXT, count=8)
    assert len(results) == 2
    r0, r1 = results
    assert r0.title == "2026 Nobel Prize in Literature"
    assert r0.published == ""  # N/A 归一为空
    assert "8 October" in r0.snippet
    assert r1.published == "2026-04-13T00:00:00.000Z"  # 元数据保留
    assert r1.author == "看点时报"


def test_parse_parallel_text() -> None:
    import json as _json

    text = _json.dumps(
        {
            "search_id": "s1",
            "results": [
                {
                    "url": "https://www.wsj.com/nobel-2025",
                    "title": "Krasznahorkai Wins Nobel",
                    "publish_date": "2025-10-09",
                    "excerpts": ["A Hungarian novelist received the prize."],
                },
                {"url": "https://x.com", "title": "", "excerpts": []},
            ],
        }
    )
    results = _parse_parallel_text(text, count=8)
    assert len(results) == 1  # 空标题被滤
    assert results[0].title == "Krasznahorkai Wins Nobel"
    assert results[0].published == "2025-10-09"
    assert "Hungarian novelist" in results[0].snippet


def test_extract_mcp_text() -> None:
    # 纯 JSON
    assert _extract_mcp_text('{"result":{"content":[{"type":"text","text":"hello"}]}}') == "hello"
    # SSE
    sse = 'event: message\ndata: {"result":{"content":[{"type":"text","text":"sse-ok"}]}}\n\n'
    assert _extract_mcp_text(sse) == "sse-ok"
    # 坏响应 → None
    assert _extract_mcp_text("not json") is None


def test_mcp_provider_order() -> None:
    assert _mcp_provider_order(None) == ["exa", "parallel"]  # auto 默认
    assert _mcp_provider_order("exa") == ["exa"]
    assert _mcp_provider_order("web") == []  # 跳过 MCP
    assert _mcp_provider_order("parallel") == ["parallel"]


def test_fetch_html_to_text() -> None:
    """S111：fetch_page 的 HTML→文本解析（噪音剔除/title 提取/实体解码）。"""
    html = (
        "<html><head><title>雾城设定 &amp; 考据</title><style>body{color:red}</style></head>"
        "<body><nav>导航栏垃圾</nav><p>雾城是一座&lt;海边&gt;城市，常年有雾。</p>"
        "<script>var x=1;</script><footer>版权信息</footer></body></html>"
    )
    title, text, truncated = html_to_text(html)
    assert title == "雾城设定 & 考据"
    assert "导航栏垃圾" not in text
    assert "版权信息" not in text
    assert "var x=1" not in text
    assert "雾城是一座<海边>城市" in text
    assert not truncated


def test_fetch_html_to_text_truncated() -> None:
    html = "<html><body>" + "字" * 500 + "</body></html>"
    _, text, truncated = html_to_text(html, max_chars=100)
    assert truncated
    assert len(text) == 100


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
