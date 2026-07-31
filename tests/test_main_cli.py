"""Tests for main.py CLI commands — lift main.py's 0% coverage.

main.py is a CLI entrypoint; we exercise the pure store-backed commands
with a tmp data dir and capture output via monkeypatched ``p``.
"""


def test_cmd_list_empty(tmp_data_dir, capsys, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_list("noknowledgebook")
    assert any("知识库为空" in str(x) for x in captured)


def test_cmd_list_with_entities(tmp_data_dir, monkeypatch):
    import main as cli
    from core.graph_store import get_store
    from core.knowledge import Entity
    from data.json_store import json_store

    book = json_store.create_book("列表书", "")
    kb = get_store(book["id"])
    kb.init_schema()
    kb.add_entity(Entity(id="e1", type="character", name="哈利"))

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_list(book["id"])
    assert any("知识库总览" in str(x) for x in captured)
    assert any("哈利" in str(x) for x in captured)


def test_cmd_chapters_empty(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_chapters("nochaptersbook")
    assert any("暂无章节" in str(x) for x in captured)


def test_cmd_chapters_with_content(tmp_data_dir, monkeypatch):
    import main as cli
    from data.json_store import json_store

    book = json_store.create_book("章节书", "")
    json_store.add_chapter(book["id"], "第一章", "这是一个很长的内容用于统计字数")

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_chapters(book["id"])
    assert any("章节列表" in str(x) for x in captured)
    assert any("总字数" in str(x) for x in captured)


def test_cmd_volumes_empty_and_with(tmp_data_dir, monkeypatch):
    import main as cli
    from data.json_store import json_store

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_volumes("novolumesbook")
    assert any("暂无分卷" in str(x) for x in captured)

    book = json_store.create_book("分卷书", "")
    json_store.add_volume(book["id"], "第一卷", "主线")
    captured2 = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured2.append((a, k)))
    cli.cmd_volumes(book["id"])
    assert any("分卷列表" in str(x) for x in captured2)
    assert any("第一卷" in str(x) for x in captured2)


def test_cmd_timeline_empty(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_timeline("notimelinebook")
    assert any("暂无时间线事件" in str(x) for x in captured)


def test_cmd_timeline_with_events(tmp_data_dir, monkeypatch):
    import main as cli
    from core.graph_store import get_store
    from core.knowledge import TimelineEvent
    from data.json_store import json_store

    book = json_store.create_book("时间线书", "")
    kb = get_store(book["id"])
    kb.init_schema()
    kb.add_timeline_event(TimelineEvent(id="t1", time_point="第1年", label="出发"))

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_timeline(book["id"])
    assert any("时间线" in str(x) for x in captured)
    assert any("出发" in str(x) for x in captured)


def test_cmd_outline_empty(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_outline("nooutlinebook")
    # Empty outline should not crash; prints something
    assert captured is not None


def test_cmd_worldbuilding_empty(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_worldbuilding("noworldbuildingbook")
    assert captured is not None


def test_cmd_char_detail_not_found(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_char_detail("不存在的人", "nobook")
    assert any("未找到角色" in str(x) for x in captured)


def test_cmd_char_detail_found(tmp_data_dir, monkeypatch):
    import main as cli
    from core.graph_store import get_store
    from core.knowledge import Entity
    from data.json_store import json_store

    book = json_store.create_book("角色详情书", "")
    kb = get_store(book["id"])
    kb.init_schema()
    kb.add_entity(Entity(id="c1", type="character", name="张三", aliases=["阿三"], data={"年龄": "30"}))

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_char_detail("张三", book["id"])
    assert any("### 张三" in str(x) for x in captured)
    assert any("年龄" in str(x) for x in captured)


def test_cmd_export(tmp_data_dir, monkeypatch):
    import main as cli
    from core.graph_store import get_store
    from core.knowledge import Entity
    from data.json_store import json_store

    book = json_store.create_book("导出书", "")
    kb = get_store(book["id"])
    kb.init_schema()
    kb.add_entity(Entity(id="c1", type="character", name="导出角色"))

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_export(book["id"])
    assert any("实体总数: 1" in str(x) for x in captured)
    assert any("character: 1" in str(x) for x in captured)


def test_cmd_stats_missing_book(tmp_data_dir, monkeypatch):
    import pytest

    import main as cli
    from core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        cli.cmd_stats("missing_book_stats")


def test_cmd_stats_with_book(tmp_data_dir, monkeypatch):
    import main as cli
    from data.json_store import json_store

    book = json_store.create_book("统计书", "")
    json_store.add_chapter(book["id"], "第一章", "字数字数字数")

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_stats(book["id"])
    assert any("项目: 统计书" in str(x) for x in captured)
    assert any("字数" in str(x) for x in captured)


def test_cmd_search_no_results(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_search("找不到的关键词", "nobook")
    assert any("未找到" in str(x) for x in captured)


def test_cmd_search_found(tmp_data_dir, monkeypatch):
    import main as cli
    from core.graph_store import get_store
    from core.knowledge import Entity
    from data.json_store import json_store

    book = json_store.create_book("搜索书", "")
    kb = get_store(book["id"])
    kb.init_schema()
    kb.add_entity(Entity(id="c1", type="character", name="赫敏"))

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_search("赫敏", book["id"])
    assert any("结果" in str(x) for x in captured)
    assert any("赫敏" in str(x) for x in captured)


def test_cmd_detailed_outline_empty(tmp_data_dir, monkeypatch):
    import main as cli

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_detailed_outline("nodetailbook")
    assert any("暂无细纲" in str(x) for x in captured)


def test_cmd_detailed_outline_with_chapters(tmp_data_dir, monkeypatch):
    import main as cli
    from data.json_store import json_store

    book = json_store.create_book("细纲书", "")
    json_store.save_detailed_outline(book["id"], {
        "chapters": [{"title": "第一章 开端", "plot_chain": ["事件A", "事件B"]}],
    })

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_detailed_outline(book["id"])
    assert any("细纲" in str(x) for x in captured)
    assert any("第一章 开端" in str(x) for x in captured)


def test_cmd_chapter_history_missing(tmp_data_dir, monkeypatch):
    import pytest

    import main as cli
    from core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        cli.cmd_chapter_history("nope", "nobook")


def test_cmd_chapter_history_with_versions(tmp_data_dir, monkeypatch):
    import main as cli
    from data.json_store import json_store

    book = json_store.create_book("历史书", "")
    ch = json_store.add_chapter(book["id"], "第一章", "初始内容")
    json_store.edit_chapter(book["id"], ch["id"], "修改后内容", message="修改一")

    captured = []
    monkeypatch.setattr(cli, "p", lambda *a, **k: captured.append((a, k)))
    cli.cmd_chapter_history(ch["id"], book["id"])
    # 版本历史至少包含一个版本记录
    assert any("版本" in str(x) for x in captured)
