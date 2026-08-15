"""S128（PLAN-SKILL-UNIFY 阶段 2）测试：templates 并入 skill 表。

物理并入验证：
- L2 默认模板 + L3 外部数据迁移为 skill 表 type=plot（四要素+layer 存 ext）
- 迁移幂等（重复 build_app 不重复种入）
- 探索消费方读 skills.plot_skills()（只读 plot 类，纪律 2）
- /api/templates CRUD 走 skill 表（前端 TemplateItem 形状保持）
- L2 默认模板不可删（layer=default 保护）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class _ProbeModel:
    model_name = "probe"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="好的。")


def _client() -> TestClient:
    return TestClient(build_app(model=_ProbeModel(), db_path=Path(tempfile.mkdtemp()) / "t.db"))


def test_templates_migrated_into_plot_skills() -> None:
    """S128：L2 默认模板物理并入 skill 表 type=plot（四要素+layer 存 ext）。"""
    client = _client()
    skills = client.get("/api/skills").json()
    plot = [s for s in skills if s["type"] == "plot"]
    # L2 默认库 5 条全部并入
    assert len(plot) >= 5
    names = {s["name"] for s in plot}
    assert "废柴流开局·反差铺垫" in names and "三幕·先抑后扬" in names
    # 四要素进 ext：探索消费方（阶段 2 前 templates_external.all()[:12]）等价
    assert all(s["ext"] for s in plot)
    import json as _json

    first = _json.loads(plot[0]["ext"])
    assert first["granularity"] in ("全书", "卷", "章", "场景", "段落")
    assert first["layer"] in ("default", "external")


def test_templates_migration_idempotent() -> None:
    """S128：迁移幂等——重复 build_app（同库重启）不重复种入。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    c1 = TestClient(build_app(model=_ProbeModel(), db_path=db))
    n1 = len([s for s in c1.get("/api/skills").json() if s["type"] == "plot"])
    c1.close()
    c2 = TestClient(build_app(model=_ProbeModel(), db_path=db))
    n2 = len([s for s in c2.get("/api/skills").json() if s["type"] == "plot"])
    assert n1 == n2  # 幂等：重启不重复种入
    c2.close()


def test_api_templates_lists_plot_skills() -> None:
    """S128：/api/templates 读 skill 表 plot 类（前端 TemplateItem 形状保持）。"""
    client = _client()
    r = client.get("/api/templates")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 5
    # TemplateItem 形状：name/description/granularity/position/function/params/layer
    assert {
        "name",
        "description",
        "granularity",
        "position",
        "function",
        "params",
        "layer",
    } <= set(items[0])
    assert items[0]["granularity"]  # 四要素元数据
    assert any(t["layer"] == "default" for t in items)  # L2 默认层


def test_api_templates_import_and_delete_external() -> None:
    """S128：导入/删除外部模板走 skill 表（INSERT OR REPLACE 语义 + default 保护）。"""
    client = _client()
    # 导入自定义模板 → skill 表 type=plot + layer=external
    r = client.post(
        "/api/templates/import",
        json={
            "name": "双城镜像",
            "description": "两座城市互为镜像，主角在二者间穿梭",
            "granularity": "全书",
            "position": "发展",
            "function": "主线",
            "params": ["镜像关系"],
        },
    )
    assert r.status_code == 200
    assert r.json()["layer"] == "external"
    assert r.json()["name"] == "双城镜像"
    # 同名覆盖（INSERT OR REPLACE 语义）
    r2 = client.post(
        "/api/templates/import",
        json={
            "name": "双城镜像",
            "description": "新版说明",
            "granularity": "章",
            "position": "高潮",
            "function": "悬念",
            "params": ["镜像关系", "代价"],
        },
    )
    assert r2.status_code == 200 and r2.json()["description"] == "新版说明"
    assert len([t for t in client.get("/api/templates").json() if t["name"] == "双城镜像"]) == 1
    # 删除外部模板 → ok
    r3 = client.delete("/api/templates/双城镜像")
    assert r3.status_code == 200 and r3.json()["ok"] is True
    assert all(t["name"] != "双城镜像" for t in client.get("/api/templates").json())
    # 删除 L2 默认模板 → 拒绝（ok=False，默认库不可删）
    r4 = client.delete("/api/templates/废柴流开局·反差铺垫")
    assert r4.status_code == 200 and r4.json()["ok"] is False
    assert any(t["name"] == "废柴流开局·反差铺垫" for t in client.get("/api/templates").json())


def test_explore_cards_reads_plot_skills() -> None:
    """S128：探索方向来源=skill 表 plot 类（纪律 2：只读 plot，其他 type 不混入）。"""
    from anyspark.align import WritingSkillStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk.db")
    # 造 plot + writing + main 三类，验证 plot_skills() 只返回 plot
    store.add(name="护送式旅程", description="明线+暗线", content="c", type="plot")
    store.add(name="文笔技巧", description="d", content="c", type="writing")
    store.add(name="类型指导", description="d", content="c", type="main")
    plots = store.plot_skills()
    assert [s.name for s in plots] == ["护送式旅程"]  # 只读 plot 类
    assert len(plots) == 1


def test_plot_skill_draft_promote_into_exploration() -> None:
    """S128：拆书 plot 子条（S127 双落产出）确认后进探索模板源（/api/templates 可见）。"""
    from anyspark.align import WritingSkillStore

    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=_ProbeModel(), db_path=db))
    skills_store = WritingSkillStore(db)
    import json as _json

    d = skills_store.add_draft(
        name="时间回环·宿命闭环",
        description="主角反复回到起点，每轮携带记忆增量",
        content="剧情模式：主角反复回到起点。",
        type="plot",
        ext=_json.dumps(
            {
                "granularity": "全书",
                "position": "发展",
                "function": "悬念",
                "params": ["回环触发点"],
            }
        ),
        source="library",
    )
    assert d is not None
    r = client.post(f"/api/skills/drafts/{d['id']}/promote")
    assert r.status_code == 200
    templates = client.get("/api/templates").json()
    assert any(t["name"] == "时间回环·宿命闭环" for t in templates)
    # layer 缺省 → external（可删）
    t = next(t for t in templates if t["name"] == "时间回环·宿命闭环")
    assert t["layer"] == "external"
    assert t["granularity"] == "全书" and t["function"] == "悬念"
