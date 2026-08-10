"""S65 互动推演扩展包：扮演角色多轮选择推进的推演树（灵感来源 + 玩法）测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.play import PlayEngine, PlayStore, export_path_markdown
from anyspark.server.workspace import Workspace


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


def _payload(call: int) -> str:
    """第 N 次模型调用返回不同场景/选项（验证轮次推进）。"""
    return json.dumps(
        {
            "scene": f"第{call}个场景：雾城的雨夜，陈渡站在码头。",
            "options": [f"行动{call}-A", f"行动{call}-B", f"行动{call}-C"],
        },
        ensure_ascii=False,
    )


class _ScriptedModel:
    """按调用次数返回不同推演结果（创建/结算/回溯都走同一 respond）。"""

    model_name = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        return ModelOutput(text=_payload(self.calls))


def test_create_root_and_options() -> None:
    """创建会话：根节点 scene + 3 个候选行动（模型自由生成）。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n雾城侦探，沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    result = engine.create(role="陈渡", seed="码头雨夜，有人送来一封信")
    assert result["ended"] is False
    node = result["node"]
    assert node["depth"] == 0
    assert node["chosen_label"] == ""
    assert "第1个场景" in node["scene"]
    assert [o["label"] for o in node["options"]] == ["行动1-A", "行动1-B", "行动1-C"]
    assert all(o["is_custom"] is False for o in node["options"])

    session = store.get_session(result["session"]["id"])
    assert session is not None and session["status"] == "running"
    assert session["current_node_id"] == node["id"]


def test_choose_option_advances() -> None:
    """选择选项 → 结算生成子节点 + 新一批选项；路径含选择。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    created = engine.create(role="陈渡", seed="码头雨夜")
    sid = created["session"]["id"]
    opt = created["node"]["options"][0]

    result = engine.choose(sid, option_id=opt["id"])
    node = result["node"]
    assert result["ended"] is False
    assert node["depth"] == 1
    assert node["chosen_label"] == "行动1-A"
    assert "第2个场景" in node["scene"]
    assert [o["label"] for o in node["options"]] == ["行动2-A", "行动2-B", "行动2-C"]

    # 原选项已标记选中并连到子节点
    chosen = store.get_option(opt["id"])
    assert chosen is not None and chosen["chosen"] == 1
    assert chosen["child_node_id"] == node["id"]
    # 路径：根 → 当前
    path = store.path_to(node["id"])
    assert len(path) == 2
    assert path[1]["chosen_label"] == "行动1-A"


def test_choose_custom_text() -> None:
    """自定义输入：作为行动进入结算（自定义位是唯一硬编码入口）。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    created = engine.create(role="陈渡", seed="码头雨夜")
    sid = created["session"]["id"]

    result = engine.choose(sid, custom_text="我烧了那封信")
    node = result["node"]
    assert node["depth"] == 1
    assert node["chosen_label"] == "我烧了那封信"
    # 自定义位落库为 is_custom=1 且已选中
    opts = store.options_of(created["node"]["id"])
    custom = [o for o in opts if o["is_custom"] == 1]
    assert len(custom) == 1 and custom[0]["label"] == "我烧了那封信"
    assert custom[0]["child_node_id"] == node["id"]


def test_branch_regenerates_options() -> None:
    """回溯分叉：回到历史节点重新生成一批新选项（原选项保留）。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    created = engine.create(role="陈渡", seed="码头雨夜")
    sid = created["session"]["id"]
    root_id = created["node"]["id"]

    result = engine.branch(sid, root_id)
    assert result["node"]["id"] == root_id
    assert [o["label"] for o in result["node"]["options"]] == ["行动2-A", "行动2-B", "行动2-C"]
    # 原选项保留（历史记录）
    opts = store.options_of(root_id)
    assert len(opts) == 6  # 3 原始 + 3 分叉
    session = store.get_session(sid)
    assert session is not None and session["current_node_id"] == root_id


def test_stop_and_export() -> None:
    """终止 + 导出灵感卡 md（路径渲染，接写正文参考）。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    created = engine.create(role="陈渡", seed="码头雨夜，有人送来一封信", title="雨的码")
    sid = created["session"]["id"]
    engine.choose(sid, custom_text="我拆了信")

    md = export_path_markdown(store, sid)
    assert "# 雨的码" in md
    assert "扮演角色：**陈渡**" in md
    assert "**选择：** 我拆了信" in md
    assert "第1个场景" in md and "第2个场景" in md

    r = engine.stop(sid)
    assert r["status"] == "ended"
    session = store.get_session(sid)
    assert session is not None and session["status"] == "ended"


def test_missing_role_card_raises() -> None:
    """无角色卡 → 报错（对齐 role_play 先例）。"""
    store = PlayStore(_db())
    engine = PlayEngine(store, _ScriptedModel(), _ws())
    try:
        engine.create(role="不存在的人", seed="场景")
        raise AssertionError("应抛 ValueError")
    except ValueError as exc:
        assert "角色卡不存在" in str(exc)


def test_max_depth_blocked() -> None:
    """到达最大深度后拒绝继续推进。"""
    store = PlayStore(_db())
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    engine = PlayEngine(store, _ScriptedModel(), ws)

    created = engine.create(role="陈渡", seed="码头雨夜", max_depth=1)
    sid = created["session"]["id"]
    opt = created["node"]["options"][0]
    # depth=1 在最大深度内，允许
    r1 = engine.choose(sid, option_id=opt["id"])
    assert r1["node"]["depth"] == 1
    # 再走一步 depth=2 > max_depth → 拒绝
    opt2 = r1["node"]["options"][0]
    try:
        engine.choose(sid, option_id=opt2["id"])
        raise AssertionError("应抛 ValueError（超过最大深度）")
    except ValueError as exc:
        assert "最大深度" in str(exc)


def test_api_flow() -> None:
    """API 全链路：建卡 → 创建 → 列表 → 选择 → 树 → 导出 → 终止。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    db = _db()
    ws = _ws()
    model = _ScriptedModel()
    client = TestClient(build_app(model=model, db_path=db, workspace=ws))

    # 建角色卡
    r = client.post("/api/role/card", json={"name": "陈渡", "content": "# 陈渡\n沉默的雾城侦探。"})
    assert r.status_code == 200

    # 创建会话
    r = client.post(
        "/api/play/sessions",
        json={"role": "陈渡", "seed": "码头雨夜，有人送来一封信", "title": "雾城信"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    sid = d["session"]["id"]
    assert d["ended"] is False
    assert len(d["node"]["options"]) == 3

    # 列表
    r = client.get("/api/play/sessions")
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())

    # 选择选项
    opt_id = d["node"]["options"][0]["id"]
    r = client.post(f"/api/play/sessions/{sid}/choose", json={"option_id": opt_id})
    assert r.status_code == 200, r.text
    assert r.json()["node"]["depth"] == 1

    # 自定义选择
    r = client.post(f"/api/play/sessions/{sid}/choose", json={"custom_text": "我把信扔进江里"})
    assert r.status_code == 200, r.text
    assert r.json()["node"]["chosen_label"] == "我把信扔进江里"

    # 树详情
    r = client.get(f"/api/play/sessions/{sid}")
    assert r.status_code == 200
    tree = r.json()
    assert len(tree["tree"]["nodes"]) == 3
    assert len(tree["path"]) == 3

    # 导出灵感卡
    r = client.get(f"/api/play/sessions/{sid}/export")
    assert r.status_code == 200
    assert "雾城信" in r.json()["markdown"]

    # 终止
    r = client.post(f"/api/play/sessions/{sid}/stop")
    assert r.status_code == 200
    assert r.json()["status"] == "ended"


def test_api_errors() -> None:
    """错误路径：无角色卡 404 / 会话不存在 404 / 非法选项 400。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    db = _db()
    client = TestClient(build_app(model=_ScriptedModel(), db_path=db, workspace=_ws()))

    # 无角色卡
    r = client.post("/api/play/sessions", json={"role": "路人甲", "seed": "场景"})
    assert r.status_code == 404

    # 会话不存在
    r = client.get("/api/play/sessions/nope")
    assert r.status_code == 404

    # 选择非法选项
    ws = _ws()
    ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n沉默寡言。")
    client2 = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=ws))
    r2 = client2.post("/api/play/sessions", json={"role": "陈渡", "seed": "场景"})
    sid = r2.json()["session"]["id"]
    r3 = client2.post(f"/api/play/sessions/{sid}/choose", json={"option_id": "不存在"})
    assert r3.status_code == 404
