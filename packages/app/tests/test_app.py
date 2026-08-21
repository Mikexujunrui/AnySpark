"""anyspark.server.app — FastAPI 路由测试（注入 fake model，不走网络）。"""

import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.app import build_app


class FakeWritingModel:
    """fake model：第一次回 tool_call 调 write_chapter，第二次回最终文本，
    第三次（后台图谱抽取）回抽取 JSON。"""

    def __init__(self) -> None:
        self.calls = 0
        self.model_name = "fake-model"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                tool_calls=[
                    ToolCall(
                        name="write_chapter",
                        arguments={"title": "第一章", "content": "雨夜，陈渡抵达雾城站。"},
                    )
                ]
            )
        if self.calls == 2:
            return ModelOutput(text="第一章已写好。")
        # 后台图谱抽取（S7）：返回实体 JSON
        return ModelOutput(
            text='{"entities": [{"name": "陈渡", "type": "角色", "aliases": [], '
            '"description": "雨夜抵达雾城的侦探"}, {"name": "雾城", "type": "地点", '
            '"aliases": [], "description": "故事发生的城市"}], '
            '"relations": [{"from": "陈渡", "to": "雾城", "type": "抵达", '
            '"description": "陈渡抵达雾城"}], "events": []}'
        )


class FakeExtractModel:
    """fake model：始终返回图谱抽取 JSON（手动抽取路由测试用）。"""

    def __init__(self) -> None:
        self.model_name = "fake-extract"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='{"entities": [{"name": "沈歆", "type": "角色", "aliases": ["沈姑娘"], '
            '"description": "陈渡的妹妹"}, {"name": "雾城钟表铺", "type": "地点", '
            '"aliases": [], "description": "城西的钟表铺"}], '
            '"relations": [{"from": "沈歆", "to": "陈渡", "type": "兄妹", '
            '"description": "亲兄妹"}], '
            '"events": [{"time_point": "第二章", "label": "兄妹相认", '
            '"description": "沈歆在钟表铺等陈渡", "involved": ["沈歆", "陈渡"]}]}'
        )


def _make_client() -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=FakeWritingModel(), db_path=db)
    return TestClient(app)


def test_health() -> None:
    client = _make_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data  # S202：health 带版本号（关于页展示）


def test_logs_export() -> None:
    """S202：
    日志导出端点返回当天日志（无日志文件时 count=0 且不报错）。
    """
    client = _make_client()
    resp = client.get("/api/logs/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "count" in data
    assert isinstance(data.get("lines"), list)


def test_chat_writes_chapter() -> None:
    client = _make_client()
    resp = client.post("/api/chat", json={"message": "写第一章"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"]
    # 写入的章节可见
    chapters = client.get("/api/chapters").json()
    assert chapters, "应有被写入的章节"
    assert chapters[0]["title"] == "第一章"
    assert "雨夜，陈渡" in chapters[0]["content"]


def test_chat_auto_extracts_graph() -> None:
    """S7：write_chapter 落盘后自动抽取图谱（独立 worker 异步执行，S21）。"""
    import time

    client = _make_client()
    resp = client.post("/api/chat", json={"message": "写第一章"})
    assert resp.status_code == 200
    # 后台 worker 异步抽取：轮询等待实体入库（fake 模型快，正常 <3s）
    names: set[str] = set()
    deadline = time.time() + 8
    while time.time() < deadline:
        entities = client.get("/api/graph/entities").json()
        names = {e["name"] for e in entities}
        if "陈渡" in names and "雾城" in names:
            break
        time.sleep(0.5)
    assert "陈渡" in names and "雾城" in names
    # 注入块非空（当前时空点已知事实）
    ctx = client.get("/api/graph/context").json()
    assert "已固化事实" in ctx["block"]


def test_graph_api_manual_extract() -> None:
    """S7：手动抽取路由（补抽/重抽），实体/关系/事件入库可见。"""
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=FakeExtractModel(), db_path=db)
    client = TestClient(app)
    r = client.post(
        "/api/graph/extract",
        json={"chapter_ref": "第二章", "text": "沈歆在雾城钟表铺等他，兄妹相认。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entities"] >= 2 and body["relations"] >= 1 and body["events"] >= 1
    entities = client.get("/api/graph/entities").json()
    names = {e["name"] for e in entities}
    assert "沈歆" in names and "雾城钟表铺" in names
    relations = client.get("/api/graph/relations").json()
    assert any(rr["rel_type"] == "兄妹" for rr in relations)
    events = client.get("/api/graph/events").json()
    assert any(ev["label"] == "兄妹相认" for ev in events)
    # 事件引用的缺失实体（陈渡）被自动补建
    assert "陈渡" in {e["name"] for e in client.get("/api/graph/entities").json()}


def test_graph_extract_rejects_content_fragment_ref() -> None:
    """S146（评审 4.1）：chapter_ref 传正文片段（含换行/超长）→ 400。"""
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=FakeExtractModel(), db_path=db)
    client = TestClient(app)
    r = client.post(
        "/api/graph/extract",
        json={"chapter_ref": "环境描写：江心楼顶层\n底层有一扇门开着", "text": "正文"},
    )
    assert r.status_code == 400


def test_chat_stream_sse_frames() -> None:
    """S8：/api/chat/stream 返回 SSE 帧（事件协议 → 传输层）。

    fake model 无逐字流，但事件帧完整：turn_start → tool_call → text → done。
    """
    client = _make_client()
    r = client.post("/api/chat/stream", json={"message": "写第一章"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: turn_start" in body
    # S98：turn_start 带轮次信息（前端进度条用真实轮次进度）
    turn_frame = next(f for f in body.split("\n\n") if f.startswith("event: turn_start"))
    import json as _json

    _tp = _json.loads(turn_frame.split("data: ", 1)[1])
    assert _tp.get("turn_index", 0) >= 1
    # S108：max_iterations 可为 None（对齐 pi 去硬上限，None=不限制）
    _mi = _tp.get("max_iterations")
    assert _mi is None or _mi >= 1
    assert "event: tool_call" in body
    assert "event: text" in body
    assert "event: done" in body
    assert "conversation_id" in body
    # 图谱抽取也照常触发（后台任务）
    entities = client.get("/api/graph/entities").json()
    assert any(e["name"] == "陈渡" for e in entities)


def test_chat_stream_book_isolation_agent_assembly() -> None:
    """S105：make_agent 装配层多书隔离——新书会话的 list_chapters 不得返回 main 章节。

    回归：ToolContext.book_id 漏传（默认 main）→ 工具全部落到旧书。
    """

    class LeakDetectModel:
        model_name = "leak-detect"

        def __init__(self) -> None:
            self.calls = 0

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                # 第一轮：调 list_chapters 工具
                return ModelOutput(tool_calls=[ToolCall(name="list_chapters", arguments={})])
            # 第二轮：检查工具结果是否含 main 章节标题（泄漏即标记）
            tool_texts = [m.content for m in messages if m.role == "tool"]
            leaked = any("main专属章" in t for t in tool_texts)
            return ModelOutput(text="LEAK!" if leaked else "OK-NO-LEAK")

    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=LeakDetectModel(), db_path=db))
    # 准备：main 书一章（新书不该看到）+ 新书一章
    assert (
        client.post(
            "/api/chapters",
            json={"book_id": "main", "title": "main专属章", "content": "旧书内容"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/chapters",
            json={"book_id": "newbook", "title": "新书第一章", "content": "新书内容"},
        ).status_code
        == 200
    )
    # 新书会话发消息 → AI 调 list_chapters → 应只见新书章节
    r = client.post(
        "/api/chat/stream",
        json={"message": "看看有什么章节", "book_id": "newbook"},
    )
    assert r.status_code == 200
    assert "OK-NO-LEAK" in r.text, f"新书会话读到 main 章节（工具未按书隔离）: {r.text[:300]}"


def test_chat_stream_done_payload_parts() -> None:
    """S82：done 帧附本轮 parts——工具调用卡片（type=tool_call）+ 思考过程（type=reasoning）。"""

    class ThinkingModel:
        model_name = "thinking-model"

        def __init__(self) -> None:
            self.calls = 0

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return ModelOutput(
                    text="",
                    reasoning="先确认第一章开场基调，决定用雨夜氛围。",
                    tool_calls=[
                        ToolCall(
                            name="write_chapter",
                            arguments={"title": "第一章", "content": "雨夜，陈渡抵达雾城站。"},
                        )
                    ],
                    usage={"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500},
                )
            return ModelOutput(
                text="第一章已写好。",
                reasoning="已核对设定，正文落盘完成。",
                usage={"prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000},
            )

    client = TestClient(build_app(model=ThinkingModel(), db_path=Path(tempfile.mkdtemp()) / "t.db"))
    r = client.post("/api/chat/stream", json={"message": "写第一章"})
    assert r.status_code == 200
    body = r.text
    assert "event: done" in body
    # done 帧 payload 带 parts
    done_frames = [f for f in body.split("\n\n") if f.startswith("event: done")]
    assert done_frames, "缺 done 帧"
    payload = done_frames[-1].split("data: ", 1)[1]
    import json

    parsed = json.loads(payload)
    parts = parsed.get("parts", [])
    kinds = {p.get("type") for p in parts}
    assert "tool_call" in kinds, f"parts 缺 tool_call: {parts}"
    assert "reasoning" in kinds, f"parts 缺 reasoning: {parts}"
    tc = next(p for p in parts if p.get("type") == "tool_call")
    assert tc["name"] == "write_chapter"
    assert tc.get("arguments", {}).get("title") == "第一章"
    rn = next(p for p in parts if p.get("type") == "reasoning")
    assert "氛围" in rn["text"]
    # S99：token 消耗汇总（每轮 usage 累加：1500 + 1000）
    usage = parsed.get("token_usage", {})
    assert usage.get("total_tokens") == 2500, f"token_usage 未正确累加: {usage}"
    assert usage.get("prompt_tokens") == 2000
    assert usage.get("completion_tokens") == 500
    # S100：done 帧带模型名（前端按模型定价估算成本）
    assert parsed.get("model") == "thinking-model"


def test_chat_stream_error_frame() -> None:
    """S8：异常转 error 帧，不中断连接。"""

    class BoomModel:
        model_name = "boom"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            raise RuntimeError("模型爆炸")

    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=BoomModel(), db_path=db)
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"message": "hi"})
    assert r.status_code == 200
    assert "event: error" in r.text
    assert "模型爆炸" in r.text


def test_agency_api_and_injection() -> None:
    """S9+S35：能动档位 API（current + levels 记录集）+ 兼容旧 level 数字。"""
    client = _make_client()
    # 默认档位 2
    r = client.get("/api/agency")
    assert r.status_code == 200
    body = r.json()
    assert body["current"]["id"] == "default-2"
    assert len(body["levels"]) == 5
    # 设置档位 0（只听写）并回读（旧数字语义 = 排序位）
    r2 = client.post("/api/agency", json={"level": 0})
    assert r2.json()["current"]["order"] == 0
    # 越界钳制：order 99 不存在 → 404（旧版钳制为 4，S35 改为明确报错）
    assert client.post("/api/agency", json={"level": 99}).status_code == 404


def test_agency_crud_api() -> None:
    """S35：新增/修改/删除/恢复默认档位 API。"""
    client = _make_client()
    # 新增自定义档位
    r = client.post(
        "/api/agency/add",
        json={"name": "大胆但不血腥", "description": "自由发挥但规避血腥", "temperature": 0.9},
    )
    assert r.status_code == 200
    lid = r.json()["level"]["id"]
    assert len(r.json()["levels"]) == 6
    # 选中自定义档位
    client.post("/api/agency", json={"level_id": lid})
    assert client.get("/api/agency").json()["current"]["id"] == lid
    # 修改
    rp = client.patch(f"/api/agency/{lid}", json={"name": "大胆克制", "temperature": 0.8})
    assert rp.json()["level"]["name"] == "大胆克制"
    assert rp.json()["level"]["temperature"] == 0.8
    # 删除
    assert client.delete(f"/api/agency/{lid}").status_code == 200
    assert len(client.get("/api/agency").json()["levels"]) == 5
    # 恢复默认
    client.post("/api/agency/add", json={"name": "临时", "description": "", "temperature": 0.5})
    client.post("/api/agency", json={"level": 4})
    rr = client.post("/api/agency/reset")
    assert rr.status_code == 200
    assert len(rr.json()["levels"]) == 5
    assert rr.json()["current"]["id"] == "default-2"


def test_signal_adjusts_agency() -> None:
    """S9：反馈自动调节——接受升级、拒绝降级（S35 按排序位移动）。"""
    client = _make_client()
    client.post("/api/agency", json={"level": 2})
    client.post("/api/signals", json={"kind": "accepted", "content": "这段很好"})
    assert client.get("/api/agency").json()["current"]["order"] == 3
    client.post("/api/signals", json={"kind": "rejected", "content": "这段不对"})
    client.post("/api/signals", json={"kind": "deleted", "content": "删掉"})
    assert client.get("/api/agency").json()["current"]["order"] == 1


def test_bias_api_and_render() -> None:
    """S9：AI 倾向档案 CRUD。"""
    client = _make_client()
    r = client.post("/api/bias", json={"content": "我这个模型写对话偏克制", "source": "ai"})
    assert r.status_code == 200
    bid = r.json()["id"]
    entries = client.get("/api/bias").json()
    assert len(entries) == 1
    assert entries[0]["source"] == "ai"
    # S102：人类手动修改（内容 + 来源）
    r2 = client.patch(
        f"/api/bias/{bid}", json={"content": "改成：写作偏克制但描写放得开", "source": "user"}
    )
    assert r2.status_code == 200
    updated = r2.json()
    assert updated["content"] == "改成：写作偏克制但描写放得开"
    assert updated["source"] == "user"
    assert client.get("/api/bias").json()[0]["content"] == "改成：写作偏克制但描写放得开"
    # 不存在的 id → 404
    assert (
        client.patch("/api/bias/nonexist", json={"content": "x", "source": "ai"}).status_code == 404
    )
    client.delete(f"/api/bias/{bid}")
    assert client.get("/api/bias").json() == []


class FakeTextModel:
    """固定文本回复（S10 交互端点测试）。"""

    def __init__(self, text: str = "固定回复文本") -> None:
        self._text = text
        self.model_name = "fake-text"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text=self._text)


def _make_client_with(model: Any) -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=model, db_path=db)
    return TestClient(app)


def test_direction_api() -> None:
    """S10：方向声明（阶段 5，摩擦前置）。"""
    client = _make_client_with(FakeTextModel("我准备写：主角推开钟表铺的门"))
    r = client.post(
        "/api/chat/direction",
        json={"prompt": "写主角发现怀表", "context": "陈渡是老周的徒弟"},
    )
    assert r.status_code == 200
    assert "方向声明" in r.json()["direction"]
    assert "钟表铺" in r.json()["direction"]


def test_candidates_api() -> None:
    """S10：候选卡堆（并行 N 个差异化候选）。"""
    client = _make_client_with(FakeTextModel("雨夜，路灯在积水里碎成一片"))
    r = client.post("/api/chat/candidates", json={"prompt": "写雨夜追车", "n": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["candidates"]) == 2
    for c in body["candidates"]:
        assert c["style"] and c["text"]


def test_rewrite_api() -> None:
    """S10：改写渐变条（保原味↔大幅改）。"""
    client = _make_client_with(FakeTextModel("改写后的正文"))
    for mode in ("subtle", "balanced", "bold"):
        r = client.post(
            "/api/chat/rewrite",
            json={"text": "原文在这里", "mode": mode},
        )
        assert r.status_code == 200
        assert r.json()["mode"] == mode
        assert r.json()["rewritten"]


def test_wrapup_api() -> None:
    """S10：一章收尾（阶段 6：一致性摘要 + 下一章衔接提示）。"""
    client = _make_client()  # FakeWritingModel 先写一章
    client.post("/api/chat", json={"message": "写第一章"})
    chapters = client.get("/api/chapters").json()
    assert chapters
    cid = chapters[0]["id"]
    r = client.post(f"/api/chapters/{cid}/wrapup")
    assert r.status_code == 200
    body = r.json()
    assert body["chapter_id"] == cid
    assert body["summary"] or body["next_hint"]  # 至少一项有内容


def test_create_chapter_api() -> None:
    """F1：手动新建空章节（order_index=末尾+1，库+md 双写）。"""
    client = _make_client()
    r = client.post("/api/chapters", json={"title": "手建章"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "手建章"
    assert body["content"] == ""
    assert body["order_index"] == 0  # 空库第一章
    # 再建一章 → order 递增
    r2 = client.post("/api/chapters", json={"title": "手建章二"})
    assert r2.json()["order_index"] == 1
    # 空标题 422
    assert client.post("/api/chapters", json={"title": "  "}).status_code == 422


def test_delete_chapter_api() -> None:
    """F1：章节删除（库 + md 双写删除），删后 404、列表减少。"""
    client = _make_client()  # FakeWritingModel 先写一章
    client.post("/api/chat", json={"message": "写第一章"})
    chapters = client.get("/api/chapters").json()
    assert chapters
    cid = chapters[0]["id"]
    r = client.delete(f"/api/chapters/{cid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 已删：列表少一章，再删 404
    assert client.get("/api/chapters").json() == []
    assert client.delete(f"/api/chapters/{cid}").status_code == 404


def test_chat_uses_same_conversation_for_continuation() -> None:
    client = _make_client()
    first = client.post("/api/chat", json={"message": "写第一章"}).json()
    conv_id = first["conversation_id"]
    second = client.post("/api/chat", json={"message": "续写", "conversation_id": conv_id})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id


def test_manual_crud_via_api() -> None:
    client = _make_client()
    # 新增
    r = client.post("/api/manual", json={"content": "不要破折号", "confidence": 0.9})
    assert r.status_code == 200
    entry_id = r.json()["id"]
    assert r.json()["source"] == "user"
    # 列出
    entries = client.get("/api/manual?scope=project").json()
    assert any(e["id"] == entry_id for e in entries)
    # 锁定
    r2 = client.patch(f"/api/manual/{entry_id}", json={"locked": True})
    assert r2.status_code == 200
    assert r2.json()["locked"] is True
    # 删除
    r3 = client.delete(f"/api/manual/{entry_id}")
    assert r3.status_code == 200
    entries = client.get("/api/manual?scope=project").json()
    assert not any(e["id"] == entry_id for e in entries)


def test_record_signal_via_api() -> None:
    client = _make_client()
    r = client.post(
        "/api/signals",
        json={"kind": "modified", "content": "原文", "new_content": "新文", "context": "稿纸"},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "modified"
    assert r.json()["context"] == "稿纸"


def test_check_rule_via_api() -> None:
    client = _make_client()
    r = client.post(
        "/api/check/rule",
        json={"rule": "不要破折号", "text": "他——她走了。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["hits"]  # 命中破折号


def test_check_unknown_rule_via_api() -> None:
    client = _make_client()
    r = client.post("/api/check/rule", json={"rule": "今天天气不错", "text": "abc"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_templates_list() -> None:
    client = _make_client()
    r = client.get("/api/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) >= 5
    assert templates[0]["granularity"]  # 四要素元数据


def test_steer_api_rejects_idle_session() -> None:
    """S25 steer 端点：会话未运行时返回 ok=False（不虚构成功）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=":memory:"))
    r = client.post("/api/chat/steer", json={"conversation_id": "nonexistent", "message": "插话"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_signal_triggers_manual_refine() -> None:
    """S28 对齐闭环修复：POST /api/signals → 后台提炼 → 说明书自动出现条目。"""
    import time

    from fastapi.testclient import TestClient

    from anyspark.core import ModelOutput
    from anyspark.server.app import build_app

    class RefineModel:
        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            return ModelOutput(
                text='[{"content": "避免血腥描写", "confidence": 0.8, "activity": "high"}]'
            )

    client = TestClient(build_app(model=RefineModel(), db_path=":memory:"))
    r = client.post(
        "/api/signals",
        json={
            "kind": "modified",
            "content": "这段太血腥了，改含蓄一点",
            "new_content": "改了版本",
            "context": "第一章",
        },
    )
    assert r.status_code == 200
    # 后台提炼是异步的：轮询等待 manual 出现自动条目
    for _ in range(20):
        time.sleep(0.3)
        entries = client.get("/api/manual").json()
        if any(e["content"] == "避免血腥描写" for e in entries):
            break
    assert any(e["content"] == "避免血腥描写" for e in entries), "信号未被提炼成说明书条目"
    # 来源为 auto（自动提炼），scope 为 project
    auto = next(e for e in entries if e["content"] == "避免血腥描写")
    assert auto["source"] == "auto"


def test_plot_priority_and_resolve_all() -> None:
    """S31 A/B 分级：主动登记 must 钩子（注入明确列出）、soft 细节（只汇总）、
    完整书导入归档（resolve_all 全回收，不输出回收率）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=":memory:"))
    # 主动登记：一条 must 钩子 + 一条 soft 线索
    r1 = client.post(
        "/api/plot/item",
        json={
            "content": "怀表背面刻有一串数字",
            "category": "伏笔",
            "chapter_ref": "第1章",
            "priority": "must",
        },
    )
    assert r1.status_code == 200 and r1.json()["priority"] == "must"
    client.post(
        "/api/plot/item",
        json={"content": "走廊画像总是目送哈利", "category": "伏笔", "chapter_ref": "第3章"},
    )
    # 生成式草案仍为 soft（默认）
    # 注入渲染分级：must 明确列出、soft 只汇总
    from anyspark.template import PlotStore

    # 归档：完整书导入 → 全回收
    r2 = client.post("/api/plot/import-resolve")
    assert r2.status_code == 200 and r2.json()["resolved"] == 2
    pts = client.get("/api/plot").json()
    assert all(p["status"] == "resolved" for p in pts)
    assert all(p["resolved_chapter"] == "全书导入" for p in pts)
    # 归档后注入块：open 全无（已回收）
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp()) / "p.db"
    store = PlotStore(tmp)
    store.add("main", "伏笔", "测试钩子", "第1章", priority="must")
    rendered = store.render()
    assert "主线钩子" in rendered and "★" in rendered  # must 明确列出
    store.add("main", "伏笔", "测试细节", "第2章")
    rendered2 = store.render()
    assert "另有 1 条细节线索" in rendered2  # soft 只汇总
    assert store.open_must("main") and len(store.open_must("main")) == 1


def test_wrapup_lists_open_hooks() -> None:
    """S31：一章收尾列出仍未回收的主线钩子（提醒非门禁）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=":memory:"))
    # 先登记 must 钩子
    client.post(
        "/api/plot/item",
        json={"content": "怀表密码必须解开", "category": "伏笔", "priority": "must"},
    )
    # 写一章
    client.post("/api/chat", json={"message": "写《第1章》50字：陈渡发现怀表"})
    chs = client.get("/api/chapters").json()
    assert chs
    wrap = client.post(f"/api/chapters/{chs[-1]['id']}/wrapup", json={})
    assert wrap.status_code == 200
    assert any(h["content"] == "怀表密码必须解开" for h in wrap.json()["open_hooks"])


def test_plot_aging_open_duration() -> None:
    """S31 老龄化：登记章 planted_order → 注入/wrapup 显示开放时长（中性事实，不设阈值）。"""
    import tempfile
    from pathlib import Path

    from anyspark.template import PlotStore

    tmp = Path(tempfile.mkdtemp()) / "aging.db"
    store = PlotStore(tmp)
    # 第 2 章登记的 must 钩子
    store.add("main", "伏笔", "怀表密码", "第2章", priority="must", planted_order=2)
    # 注入渲染：当前第 6 章 → 标"已开放 4 章"
    rendered = store.render(current_order=6)
    assert "已开放 4 章" in rendered
    # 未知当前章（0）→ 不标年龄
    assert "已开放" not in store.render(current_order=0)
    # wrapup 用的 open_must 带 current_order 计算 open_since
    hooks = store.open_must("main", current_order=6)
    assert hooks and hooks[0].planted_order == 2


def test_plot_planted_order_via_api() -> None:
    """S31：登记 API 接受 planted_order，返回并持久化。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=":memory:"))
    r = client.post(
        "/api/plot/item",
        json={
            "content": "门后有人",
            "category": "伏笔",
            "chapter_ref": "第1章",
            "priority": "must",
            "planted_order": 1,
        },
    )
    assert r.status_code == 200
    assert r.json()["planted_order"] == 1
    # 列表返回 planted_order
    pts = client.get("/api/plot").json()
    assert pts[0]["planted_order"] == 1


def test_batch_api_removed_workflow_replaces() -> None:
    """S140（PLAN-SCALE-SAFETY 阶段 D）：/api/batch/* 已收编为 workflow 模板。

    内存 batch 路由移除（归一不降级：批量改写/审读由「批量改写」「批量审读」
    预置模板 + 前端工作流模式执行，带断点/续跑/回滚）；旧端点应 404，
    模板仍在。
    """
    client = _make_client()
    # 旧内存 batch 端点已移除（SPA mount 对不存在 POST 返回 405/404）
    assert client.post("/api/batch/review", json={"chapter_ids": ["x"]}).status_code in (404, 405)
    assert client.post(
        "/api/batch/rewrite", json={"chapter_ids": ["x"], "instruction": "改写"}
    ).status_code in (404, 405)
    assert client.get("/api/batch/notexist").status_code == 404
    # 替代机制：预置模板仍在（归一不降级）
    wfs = client.get("/api/workflows").json()
    names = {w["name"] for w in wfs}
    assert "批量改写" in names and "批量审读" in names


def test_settings_extract_api() -> None:
    """S42：从图谱提炼设定草案（fake 模型返回空草案不报错）。"""
    client = _make_client()
    r = client.post("/api/settings/extract", json={"book_id": "main"})
    assert r.status_code == 200
    body = r.json()
    assert "draft" in body and "raw" in body


def test_chapter_patch_api() -> None:
    """S44：定点编辑 API——插入/删除/替换指定位置，不重写整章。"""
    client = _make_client()
    # 写一章
    r = client.post("/api/chat", json={"message": "写《第一章》100字：陈渡在灯塔发现日记"})
    assert r.status_code == 200
    chs = client.get("/api/chapters").json()
    assert chs
    cid = chs[-1]["id"]
    orig = chs[-1]["content"]
    # 取一个锚点段落
    paras = [p for p in orig.split("\n") if p.strip()]
    assert paras, "章节应有内容"
    anchor = paras[0][:8]
    # 插入：锚点段后插入新段
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={"operations": [{"type": "insert", "anchor": anchor, "content": "新增段。"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "新增段" in body["results"][0].get("inserted", "")
    after_insert = client.get("/api/chapters").json()[-1]["content"]
    assert "新增段" in after_insert
    assert len(after_insert) > len(orig)
    # 删除：删掉新增段
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={"operations": [{"type": "delete", "anchor": "新增段"}]},
    )
    assert r.json()["ok"] is True
    after_del = client.get("/api/chapters").json()[-1]["content"]
    assert "新增段" not in after_del
    # 替换：替换锚点段
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={"operations": [{"type": "replace", "anchor": anchor, "content": "替换后的开头。"}]},
    )
    assert r.json()["ok"] is True
    after_rep = client.get("/api/chapters").json()[-1]["content"]
    assert "替换后的开头" in after_rep
    # 未命中锚点 → ok=False
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={"operations": [{"type": "delete", "anchor": "不存在的锚点"}]},
    )
    assert r.json()["ok"] is False
    # 404
    assert client.post("/api/chapters/nonexist/patch", json={"operations": []}).status_code == 404


class NoopModel:
    """极简 fake：不实际调用（消息编辑/保存不走模型）。"""

    model_name = "noop"

    def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="")


def test_edit_agent_text_keeps_tool_pairing_e2e() -> None:
    """S193/C 契约：用户在界面编辑 AI 输出文本后保存——消息不因 content 变更被重排、
    工具配对不残留残缺（S190 守卫兜底，绝不 400）。纯工具轮声明（空 content）按配对 id
    精确插回其 tool 结果之前，编辑文本只改该条消息本身。"""
    from anyspark.store import SqliteConversationStore

    db = Path(tempfile.mkdtemp()) / "t.db"
    app = build_app(model=NoopModel(), db_path=db)
    client = TestClient(app)

    # 自然配对历史：工具轮声明（空 content，GET 过滤）+ tool 结果 + 终结回复（可编辑）
    store = SqliteConversationStore(db)
    conv = store.create()
    store.append(conv.id, Message(role="user", content="写第一章"))
    store.append(
        conv.id,
        Message(
            role="assistant",
            content="",  # 纯工具轮声明（S145b 前端过滤）
            metadata={"tool_calls": [{"name": "write_chapter", "arguments": {}, "id": "c1"}]},
        ),
    )
    store.append(conv.id, Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}))
    store.append(conv.id, Message(role="assistant", content="第一章写好了。"))
    store.close()

    # 前端拉取历史（纯工具轮声明被过滤 → 前端看不到、不可编辑、不可改）
    got = client.get(f"/api/conversations/{conv.id}/messages")
    assert got.status_code == 200
    history = got.json()
    assert all(m["role"] != "assistant" or m["content"] for m in history)  # 无空声明泄漏
    assert any("第一章写好了" in (m["content"] or "") for m in history)

    # 编辑终结回复文本后整体保存（只发 role+content）
    edited = [dict(m) for m in history]
    for m in edited:
        if m["role"] == "assistant" and m["content"] and "第一章写好了" in m["content"]:
            m["content"] = "（用户改写：第一章已完成）"
    resp = client.post(f"/api/conversations/{conv.id}/messages", json={"messages": edited})
    assert resp.status_code == 200, f"保存应 200: {resp.text}"

    # GET 读回：编辑文本生效（空 content 的伴侣声明被 S145b 过滤，不在此展示）
    after = client.get(f"/api/conversations/{conv.id}/messages").json()
    assert any("用户改写" in (m["content"] or "") for m in after), "编辑文本应生效"
    assert not any("第一章写好了" in (m["content"] or "") for m in after)  # 旧文本被替换

    # store 层验证配对完整：工具轮声明（空 content）在 tool 结果之前，顺序正确
    store2 = SqliteConversationStore(db)
    stored = store2.messages(conv.id)
    store2.close()
    roles = [m.role for m in stored]
    assert roles == ["user", "assistant", "tool", "assistant"], f"顺序应保持: {roles}"
    # 声明与 tool 结果配对（c1），且 tool 紧跟其声明
    assert stored[1].metadata["tool_calls"][0]["id"] == "c1"
    assert stored[2].metadata["tool_call_id"] == "c1"
    # 编辑的终结回复保留
    assert "用户改写" in stored[3].content
