"""anyspark.template.plot — 关键点图谱（伏笔）测试。

覆盖 PlotStore CRUD/前缀匹配/render 分级/open_must/resolve_all +
PlotGenerator LLM 草案 + PlotResolver 自动回收 + _text_match 宽容匹配。
"""

import json
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.template.plot import (
    PLOT_CATEGORIES,
    PlotGenerator,
    PlotPoint,
    PlotResolver,
    PlotStore,
    _age_text,
    _text_match,
)


class FakeModel:
    """记录 prompt + 返回预设文本的假模型。"""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    model_name = "probe"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.prompts.append(messages[0].content or "")
        return ModelOutput(text=self._reply)


# ---------- PlotStore CRUD ----------


def test_plot_store_add_and_list() -> None:
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        p = store.add("main", "伏笔", "主角项链的来历", chapter_ref="第1章")
        assert p.category == "伏笔"
        assert p.status == "open"
        assert p.attention == "care"
        assert p.priority == "soft"  # 默认 soft
        assert p.chapter_ref == "第1章"

        pts = store.list_points("main")
        assert len(pts) == 1
        assert pts[0].content == "主角项链的来历"
    finally:
        store.close()


def test_plot_store_add_validates_category_and_enum() -> None:
    """非法 category/attention/priority 回退到默认值（不抛异常）。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        p = store.add(
            "main",
            category="不存在的类别",
            content="测试",
            attention="invalid",
            priority="invalid",
        )
        assert p.category == "主线冲突"  # 回退默认
        assert p.attention == "care"
        assert p.priority == "soft"
    finally:
        store.close()


def test_plot_store_book_isolation() -> None:
    """不同 book_id 的伏笔隔离。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("bookA", "伏笔", "A 的伏笔")
        store.add("bookB", "伏笔", "B 的伏笔")
        assert len(store.list_points("bookA")) == 1
        assert len(store.list_points("bookB")) == 1
        assert store.list_points("bookA")[0].content == "A 的伏笔"
    finally:
        store.close()


# ---------- 前缀匹配（agent 从 plot_list 拿截断 id）----------


def test_plot_store_prefix_match_get_update_delete() -> None:
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        p = store.add("main", "伏笔", "前缀匹配测试")
        full_id = p.id
        prefix = full_id[:8]  # 截断 id
        assert len(prefix) < len(full_id)

        # get 支持前缀
        got = store.get(prefix)
        assert got is not None
        assert got.id == full_id

        # update 支持前缀
        updated = store.update(prefix, status="resolved", resolved_chapter="第10章")
        assert updated is not None
        assert updated.status == "resolved"
        assert updated.resolved_chapter == "第10章"

        # delete 支持前缀
        store.delete(prefix)
        assert store.get(full_id) is None
    finally:
        store.close()


def test_plot_store_update_no_fields_returns_current() -> None:
    """update 不传任何字段 = 返回当前值（无变更）。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        p = store.add("main", "伏笔", "不变更测试")
        result = store.update(p.id)
        assert result is not None
        assert result.content == "不变更测试"
    finally:
        store.close()


# ---------- render 分级渲染 ----------


def test_render_empty_returns_empty_string() -> None:
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        assert store.render("main") == ""
    finally:
        store.close()


def test_render_must_hooks_listed_explicitly() -> None:
    """must 钩子（作者承诺）在 render 里明确列出 + 带 ★ 标记。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "主线冲突", "主角身世之谜", priority="must", chapter_ref="第1章")
        store.add("main", "伏笔", "路人甲的玉佩", priority="soft")
        rendered = store.render("main", current_order=5)
        assert "⚠ 主线钩子" in rendered
        assert "★" in rendered
        assert "主角身世之谜" in rendered
        # soft 只汇总数量
        assert "1 条细节线索" in rendered
    finally:
        store.close()


def test_render_ignores_attention_ignore() -> None:
    """attention=ignore 的条目不注入。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "伏笔", "忽略的线索", attention="ignore")
        assert store.render("main") == ""
    finally:
        store.close()


def test_render_age_text() -> None:
    """老龄化提示：开放 N 章。"""
    p = PlotPoint(
        id="x",
        book_id="main",
        category="伏笔",
        content="测试",
        planted_order=2,
    )
    assert "已开放 3 章" in _age_text(p, current_order=5)
    assert _age_text(p, current_order=0) == ""  # 未知章序
    assert _age_text(p, current_order=2) == ""  # 同章


def test_render_resolved_section() -> None:
    """已回收的条目列在底部，最多 max_resolved 条。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        for i in range(5):
            p = store.add("main", "伏笔", f"已回收{i}")
            store.update(p.id, status="resolved", resolved_chapter=f"第{i}章")
        rendered = store.render("main", max_resolved=2)
        assert "已回收" in rendered
        # 只显示最近 2 条
        assert "已回收4" in rendered
        assert "已回收3" in rendered
        assert "已回收0" not in rendered
    finally:
        store.close()


# ---------- open_must + resolve_all ----------


def test_open_must_returns_unresolved_hooks() -> None:
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "主线冲突", "未回收钩子", priority="must")
        store.add("main", "主线冲突", "已回收钩子", priority="must")
        store.add("main", "伏笔", "soft 细节", priority="soft")
        store.update(store.list_points("main")[1].id, status="resolved")

        musts = store.open_must("main")
        assert len(musts) == 1
        assert musts[0].content == "未回收钩子"
    finally:
        store.close()


def test_resolve_all_archives_open_points() -> None:
    """完整书导入归档——所有 open 标 resolved。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "伏笔", "未回收1")
        store.add("main", "伏笔", "未回收2")
        store.add("main", "伏笔", "已回收3")
        store.update(store.list_points("main")[2].id, status="resolved")

        n = store.resolve_all("main", chapter_ref="全书导入")
        assert n == 2  # 只归档 open 的，已 resolved 不计
        # 全部 resolved
        pts = store.list_points("main")
        assert all(p.status == "resolved" for p in pts)
        # resolve_all 只处理 open 的，已 resolved 的 resolved_chapter 不被覆盖
        open_pts = [p for p in pts if p.content.startswith("未回收")]
        assert all(p.resolved_chapter == "全书导入" for p in open_pts)
    finally:
        store.close()


# ---------- PlotGenerator ----------


def test_plot_generator_parses_json_array() -> None:
    """生成器解析 LLM 返回的 JSON 数组 → 落库。"""
    reply = json.dumps(
        [
            {"category": "主线冲突", "content": "主角复仇之路", "chapter_ref": "第1章"},
            {"category": "伏笔", "content": "神秘信物", "chapter_ref": "第2章"},
        ]
    )
    model = FakeModel(reply)
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        gen = PlotGenerator(model)
        points = gen.generate("main", store, settings="测试设定")
        assert len(points) == 2
        assert points[0].content == "主角复仇之路"
        assert points[0].category == "主线冲突"
        # 验证 prompt 含设定
        assert "测试设定" in model.prompts[0]
    finally:
        store.close()


def test_plot_generator_handles_markdown_fence() -> None:
    """LLM 返回带 ```json 代码块也能解析。"""
    reply = '```json\n[{"category": "伏笔", "content": " fenced 测试"}]\n```'
    model = FakeModel(reply)
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        points = PlotGenerator(model).generate("main", store)
        assert len(points) == 1
        assert points[0].content == "fenced 测试"
    finally:
        store.close()


def test_plot_generator_bad_json_returns_empty() -> None:
    """LLM 返回非 JSON = 空列表（不抛异常）。"""
    model = FakeModel("抱歉，我无法生成")
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        points = PlotGenerator(model).generate("main", store)
        assert points == []
    finally:
        store.close()


def test_plot_generator_skips_empty_content() -> None:
    """content 为空的条目跳过。"""
    reply = json.dumps(
        [
            {"category": "伏笔", "content": ""},
            {"category": "伏笔", "content": "有效条目"},
        ]
    )
    model = FakeModel(reply)
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        points = PlotGenerator(model).generate("main", store)
        assert len(points) == 1
        assert points[0].content == "有效条目"
    finally:
        store.close()


# ---------- PlotResolver ----------


def test_plot_resolver_matches_and_resolves() -> None:
    """回收器：LLM 输出与库中条目高度一致 → 标 resolved。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "伏笔", "主角的神秘项链")
        reply = json.dumps(
            {"resolved": [{"content": "主角的神秘项链", "evidence": "本章揭开项链来历"}]}
        )
        resolver = PlotResolver(FakeModel(reply))
        resolved = resolver.resolve("main", "第10章", "正文揭示项链是祖传之物", store)
        assert len(resolved) == 1
        assert "主角的神秘项链" in resolved[0]
        # 验证已落库
        pts = store.list_points("main")
        assert pts[0].status == "resolved"
    finally:
        store.close()


def test_plot_resolver_no_open_points_returns_empty() -> None:
    """无 open 关键点 → 不调模型直接返回空。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        model = FakeModel("不该被调用")
        resolver = PlotResolver(model)
        result = resolver.resolve("main", "第1章", "正文", store)
        assert result == []
        assert len(model.prompts) == 0  # 没调模型
    finally:
        store.close()


def test_plot_resolver_bad_json_returns_empty() -> None:
    """LLM 返回非 JSON = 空列表（静默失败）。"""
    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "伏笔", "测试伏笔")
        resolver = PlotResolver(FakeModel("无法解析"))
        result = resolver.resolve("main", "第1章", "正文", store)
        assert result == []
    finally:
        store.close()


def test_plot_resolver_model_exception_returns_empty() -> None:
    """模型抛异常 = 空列表（绝不影响写作主链路）。"""

    class _Boom:
        model_name = "boom"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            raise RuntimeError("模拟模型崩溃")

    store = PlotStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        store.add("main", "伏笔", "测试伏笔")
        resolver = PlotResolver(_Boom())
        assert resolver.resolve("main", "第1章", "正文", store) == []
    finally:
        store.close()


# ---------- _text_match ----------


def test_text_match_exact() -> None:
    assert _text_match("主角的项链", "主角的项链") is True


def test_text_match_substring() -> None:
    """双向包含匹配——容忍 LLM 复述的细微差异。"""
    assert _text_match("主角的项链", "主角的项链来历") is True
    assert _text_match("主角的项链来历", "主角的项链") is True


def test_text_match_different() -> None:
    assert _text_match("主角的项链", "反派的剑") is False


def test_text_match_ignores_punctuation() -> None:
    """标点符号不影响匹配。"""
    assert _text_match("主角，的项链。", "主角的项链") is True


def test_plot_categories_complete() -> None:
    """关键点类别 7 类齐全（地图 + 设计约束）。"""
    assert PLOT_CATEGORIES == (
        "主线冲突",
        "角色弧",
        "情感核",
        "世界规则",
        "情绪峰值",
        "伏笔",
        "节奏",
    )
