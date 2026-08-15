"""S48-P4 角色推演：多路探索 + 判别选优（低成本多探索，选最好的作为参考）测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.explore.roleplay import (
    ROLE_STRATEGIES,
    RolePlayEngine,
    _parse_judge,
    run_roleplay,
)
from anyspark.graph import GraphStore
from anyspark.server.app import build_app
from anyspark.server.workspace import Workspace


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


class _ScriptedModel:
    """按系统提示内容返回不同响应（推演路数返回不同文本，判别返回指定编号）。"""

    model_name = "scripted"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        prompt = messages[0].content or ""
        self.calls.append(prompt[:30])
        if "候选推演" in prompt:
            return ModelOutput(text="编号：2 因为最有张力")
        if "冲突与张力" in prompt:
            return ModelOutput(text="（戏剧）陈渡摔了怀表。")
        if "违背直觉" in prompt:
            return ModelOutput(text="（反常）陈渡笑了。")
        if "话少意深" in prompt:
            return ModelOutput(text="（克制）陈渡沉默。")
        return ModelOutput(text="（可能）陈渡握紧了怀表。")


def test_strategies_four_kinds() -> None:
    names = [s["name"] for s in ROLE_STRATEGIES]
    assert names == ["最可能反应", "最戏剧化反应", "最反常反应", "最克制反应"]


def test_roleplay_multi_explore_and_select() -> None:
    """多路隔离推演 + 判别选优（最后选择最好的）。"""
    model = _ScriptedModel()
    result = run_roleplay(
        model,
        role_card="# 陈渡\n雾城侦探，沉默寡言。",
        state="刚发现怀表刻着亡父的名字",
        scenario="顾欣桐告诉他真相的那一刻",
        n=4,
    )
    assert len(result.candidates) == 4  # 四路都产出
    assert result.best is not None
    assert result.best.strategy == "最戏剧化反应"  # 判别器选编号2（候选序：可能/戏剧/反常/克制）
    assert "陈渡摔了怀表" in result.best.text
    # 各路策略不同（多样性）
    texts = {c.text for c in result.candidates}
    assert len(texts) >= 3


def test_parse_judge() -> None:
    assert _parse_judge("编号：3 因为…", 4) == 2
    assert _parse_judge("编号: 1", 4) == 0
    assert _parse_judge("不好说", 4) is None
    assert _parse_judge("编号：9", 4) is None  # 越界


def test_roleplay_api_with_graph_state() -> None:
    """API：角色卡文件优先 + 图谱 state 兜底；返回 best + 备选。"""
    from fastapi.testclient import TestClient

    db = _db()
    ws = _ws()
    model = _ScriptedModel()
    client = TestClient(build_app(model=model, db_path=db, workspace=ws))

    # 无角色卡 → 404
    r = client.post("/api/role/play", json={"role": "陈渡", "scenario": "对峙"})
    assert r.status_code == 404

    # 建角色卡 + 图谱实体（带 state）
    client.post("/api/role/card", json={"name": "陈渡", "content": "# 陈渡\n沉默的雾城侦探。"})
    g = GraphStore(db)
    g.upsert_entity("main", "陈渡", "角色", description="侦探，重伤未愈")

    r = client.post("/api/role/play", json={"role": "陈渡", "scenario": "顾欣桐说出真相"})
    assert r.status_code == 200
    d = r.json()
    assert d["best"] is not None and d["best"]["text"]
    assert len(d["candidates"]) == 4


def test_roleplay_engine_empty_fallback() -> None:
    """全部候选为空 → 空结果不崩。"""

    class _EmptyModel:
        model_name = "empty"

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            return ModelOutput(text="")

    engine = RolePlayEngine(_EmptyModel(), n=4)
    result = engine.play("# 角色", "", "场景")
    assert result.best is None and result.candidates == []


def test_role_card_isolated_by_book() -> None:
    """S152f：角色卡按项目（book_id）写入 + 读卡端点按项目读取。

    此前 POST /api/role/card 硬编码 write_card("main", ...)——跨项目角色卡
    写错书；本测试锁住隔离语义 + GET /api/card 读取闭环。
    """
    from fastapi.testclient import TestClient

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 项目 A 写卡
    r = client.post(
        "/api/role/card",
        json={"name": "陈渡", "content": "身世成谜的年轻侦探", "book_id": "book-a"},
    )
    assert r.status_code == 200, r.text
    # 项目 B 写同名卡（不同内容）
    client.post(
        "/api/role/card",
        json={"name": "陈渡", "content": "港口的老船长", "book_id": "book-b"},
    )
    # 读卡：各自项目读到各自内容（文件按项目目录隔离）
    a = client.get("/api/card?kind=角色卡&name=陈渡&book_id=book-a").json()
    b = client.get("/api/card?kind=角色卡&name=陈渡&book_id=book-b").json()
    assert a["content"] == "身世成谜的年轻侦探"
    assert b["content"] == "港口的老船长"
    # main 项目无卡
    m = client.get("/api/card?kind=角色卡&name=陈渡").json()
    assert m["content"] == ""


def test_role_play_book_scoped() -> None:
    """S162：/api/role/play 读角色卡按 book_id（此前固定 main，跨项目角色卡读不到）。"""
    from fastapi.testclient import TestClient

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # book-a 项目建卡（main 无此卡）
    r = client.post(
        "/api/role/card",
        json={"name": "陈渡", "content": "身世成谜的年轻侦探", "book_id": "book-a"},
    )
    assert r.status_code == 200, r.text

    # 不带 book_id（默认 main）→ 404（main 无卡）
    r = client.post("/api/role/play", json={"role": "陈渡", "scenario": "对峙"})
    assert r.status_code == 404
    # 带 book_id=book-a → 200（读对项目卡）
    r = client.post(
        "/api/role/play",
        json={"role": "陈渡", "scenario": "顾欣桐说出真相", "book_id": "book-a"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["best"] is not None and len(d["candidates"]) == 4
