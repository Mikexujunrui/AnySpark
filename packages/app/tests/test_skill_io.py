"""S118 提案 D：内容生态基础设施——skill 文件导入导出（上传区判别路由 + 格式闭环）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from anyspark.server.skill_io import parse_skill_file, render_skill_file

# ---------------------------------------------------------------------------
# skill 文件格式（front-matter 五段式）
# ---------------------------------------------------------------------------


def test_parse_skill_file_basic() -> None:
    md = """---
name: 悬念钩子
type: writing
tags: 悬疑,节奏
description: 每章结尾用未解问题钩住读者
---
每章结尾停在一个未解决的问题上。
---
例：他推开门，走廊尽头站着一个人。
"""
    s = parse_skill_file(md)
    assert s is not None
    assert s["name"] == "悬念钩子"
    assert s["type"] == "writing"  # S127：type 键
    assert s["tags"] == "悬疑,节奏"
    assert "未解决的问题" in s["content"]
    assert "走廊尽头" in s["example"]


def test_parse_skill_file_legacy_target_key() -> None:
    """S127：旧文件 target 键兼容（type 优先，target 回落）。"""
    md = """---
name: 旧文件
target: main
tags: 结构
---
正文内容
"""
    s = parse_skill_file(md)
    assert s is not None and s["type"] == "main"
    # type 优先于 target
    md2 = "---\nname: 新文件\ntype: plot\ntarget: main\n---\n正文\n"
    s2 = parse_skill_file(md2)
    assert s2 is not None and s2["type"] == "plot"


def test_parse_skill_file_not_skill() -> None:
    # 普通 md 笔记（无 front-matter）→ None（不误判）
    assert parse_skill_file("# 笔记\n\n随便写点什么") is None
    # 无 name → None
    assert parse_skill_file("---\ntags: x\n---\ncontent") is None
    # 无 content → None
    assert parse_skill_file("---\nname: 空\n---\n") is None
    # 空文本 → None
    assert parse_skill_file("") is None


def test_parse_skill_file_target_fallback() -> None:
    md = "---\nname: X\ntype: 非法值\n---\n正文内容\n"
    s = parse_skill_file(md)
    assert s is not None and s["type"] == "writing"
    # 旧文件 target 键非法值同样回落
    md2 = "---\nname: X2\ntarget: 非法值\n---\n正文内容\n"
    s2 = parse_skill_file(md2)
    assert s2 is not None and s2["type"] == "writing"


def test_render_parse_roundtrip() -> None:
    """导出格式 = 导入判别格式（闭环）。S127：type 键往返。"""
    orig = {
        "name": "对白机锋",
        "description": "用潜台词代替直白信息",
        "content": "对白里只给一半信息，让读者自己补。",
        "example": "「你来了。」「我来过。」",
        "tags": "对白,张力",
        "type": "writing",
    }
    rendered = render_skill_file(**orig)
    parsed = parse_skill_file(rendered)
    assert parsed is not None
    assert parsed["name"] == orig["name"]
    assert parsed["description"] == orig["description"]
    assert parsed["content"] == orig["content"]
    assert parsed["example"] == orig["example"]
    assert parsed["tags"] == orig["tags"]
    assert parsed["type"] == orig["type"]


def test_render_plot_type_roundtrip() -> None:
    """S127：plot 类型 skill 导出导入闭环（四要素在 content/description）。"""
    rendered = render_skill_file(
        name="时间回环", description="剧情模式说明", content="主线以回环组织。", type="plot"
    )
    assert "type: plot" in rendered
    parsed = parse_skill_file(rendered)
    assert parsed is not None and parsed["type"] == "plot"


def test_render_pack_id_roundtrip() -> None:
    """S130：书名包子条导出带 pack_id → 导入还原（整包引用路由前提）。"""
    rendered = render_skill_file(
        name="斗破苍穹·文笔",
        description="文笔技法",
        content="短句直给推进",
        type="writing",
        pack_id="斗破苍穹",
    )
    assert "pack_id: 斗破苍穹" in rendered
    parsed = parse_skill_file(rendered)
    assert parsed is not None
    assert parsed["type"] == "writing" and parsed["pack_id"] == "斗破苍穹"
    # 无 pack_id 文件 → 空串（独立子条）
    plain = parse_skill_file(render_skill_file(name="独立", content="c"))
    assert plain is not None and plain["pack_id"] == ""


# ---------------------------------------------------------------------------
# ingest 判别路由 + export 端点（build_app 真实链路）
# ---------------------------------------------------------------------------


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _probe_model() -> Any:
    class _P:
        model_name = "probe"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="ok")

    return _P()


def test_ingest_skill_file_to_draft() -> None:
    """上传 skill 文件 → ingest 识别 kind=skill → 草稿 → promote 转正。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app
    from anyspark.server.workspace import Workspace

    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")
    # 上传 skill 文件（base64）
    import base64

    skill_md = render_skill_file(
        name="导入测试技法",
        description="上传判别测试",
        content="写作时先定节奏，再填内容。",
        type="writing",
    )
    r = ws.save_upload("main", "test_skill.skill.md", skill_md.encode())
    assert r.exists()

    client = TestClient(build_app(model=_probe_model(), db_path=_db()))
    up = client.post(
        "/api/upload",
        json={
            "filename": "test_skill.skill.md",
            "data_b64": base64.b64encode(skill_md.encode()).decode(),
            "book_id": "main",
        },
    )
    assert up.status_code == 200, up.text

    ing = client.post("/api/ingest", json={"filename": "test_skill.skill.md", "book_id": "main"})
    assert ing.status_code == 200, ing.text
    data = ing.json()
    assert data["kind"] == "skill"
    assert data["title"] == "导入测试技法"

    # 草稿区出现待确认项
    drafts = client.get("/api/skills/drafts").json()
    assert any(d["name"] == "导入测试技法" for d in drafts)
    did = next(d["id"] for d in drafts if d["name"] == "导入测试技法")

    # 人工确认转正
    promoted = client.post(f"/api/skills/drafts/{did}/promote")
    assert promoted.status_code == 200
    skills = client.get("/api/skills").json()
    assert any(s["name"] == "导入测试技法" for s in skills)


def test_ingest_plain_md_not_skill() -> None:
    """普通 md 上传不误判为 skill（走原拆章/摘要卡分支）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_probe_model(), db_path=_db()))
    import base64

    body = "# 我的笔记\n\n随便记录一些想法，不是技能文件。"
    client.post(
        "/api/upload",
        json={
            "filename": "note.md",
            "data_b64": base64.b64encode(body.encode()).decode(),
            "book_id": "main",
        },
    )
    r = client.post("/api/ingest", json={"filename": "note.md", "book_id": "main"})
    assert r.status_code == 200
    assert r.json()["kind"] in ("card", "chapters")  # 不是 skill


def test_export_skill_file() -> None:
    """GET /api/skills/{id}/export 返回 front-matter md（分享闭环）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_probe_model(), db_path=_db()))
    # 创建一个 skill
    created = client.post(
        "/api/skills",
        json={
            "name": "导出测试技法",
            "description": "导出测试",
            "content": "短句推进，长句收束。",
            "example": "他走。雨停。",
            "tags": "节奏",
            "target": "writing",
        },
    )
    assert created.status_code == 200
    sid = created.json()["id"]

    r = client.get(f"/api/skills/{sid}/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    # 导出内容可被 parse_skill_file 重新识别（闭环）
    s = parse_skill_file(r.text)
    assert s is not None
    assert s["name"] == "导出测试技法"
    assert s["content"] == "短句推进，长句收束。"
    assert s["example"] == "他走。雨停。"
