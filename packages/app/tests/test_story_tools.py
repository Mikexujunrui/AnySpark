"""S242（DESIGN §12.46）：AI 自主规划写入渠道测试。

三工具（story_node_add / plan_register / setting_register）+ 预置模板「叙事树提炼」
（章题轨迹 → 树形草案 → 落库）。"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.align.plan import StoryPlanStore
from anyspark.align.storytree import StoryTreeStore
from anyspark.align.worldsettings import WorldSettingStore
from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.server.app import build_app
from anyspark.server.tools_plot import (
    make_plan_implementer,
    make_setting_implementer,
    make_setting_register_implementer,
    make_story_tree_implementer,
)


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Any, name: str = "t", /, **kwargs: Any) -> ToolResult:
    """直接调用 implementer（模拟 Agent 工具调用）；name 位置限定，
    避免与工具自身叫 name 的参数撞名（如 setting_register 的 name）。"""
    spec = ToolSpec(name=name, description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


# ---------------------------------------------------------------------------
# story_node_add：叙事树写入（空树→根；缺省接主线末尾；分支/校验）
# ---------------------------------------------------------------------------
def test_story_node_add_grows_line() -> None:
    tree = StoryTreeStore(_db())
    _, impl = make_story_tree_implementer(tree)

    r1 = _call(impl, "story_node_add", content="主角抵达雾城")
    assert r1.ok is True
    assert r1.data is not None and r1.data["kind"] == "root"  # 空树首节点=根

    r2 = _call(impl, "story_node_add", content="发现怀表秘密")
    assert r2.ok is True
    nodes = tree.list_nodes("main")
    assert len(nodes) == 2
    root = next(n for n in nodes if n.content == "主角抵达雾城")
    n2 = next(n for n in nodes if n.content == "发现怀表秘密")
    assert n2.parent_id == root.id  # 缺省接主线末尾
    assert n2.chosen is True  # 缺省随 kind=main


def test_story_node_add_branch_and_validation() -> None:
    tree = StoryTreeStore(_db())
    _, impl = make_story_tree_implementer(tree)
    _call(impl, "story_node_add", content="根：开篇")

    r = _call(impl, "story_node_add", content="可能分叉：旧友线索", kind="candidate")
    assert r.ok is True and r.data is not None and r.data["kind"] == "candidate"
    nodes = tree.list_nodes("main")
    branch = next(n for n in nodes if "旧友线索" in n.content)
    assert branch.chosen is False  # candidate 缺省未走过

    # 非法 kind / 不存在的父节点 / 空内容
    assert _call(impl, "story_node_add", content="x", kind="boss").ok is False
    assert _call(impl, "story_node_add", content="x", parent_id="nope").ok is False
    assert _call(impl, "story_node_add", content="   ").ok is False


# ---------------------------------------------------------------------------
# plan_register：计划登记（新建 / 同章重登=更新且保留 done 状态）
# ---------------------------------------------------------------------------
def test_plan_register_create_and_update() -> None:
    plans = StoryPlanStore(_db())
    specs, impls = make_plan_implementer(plans)
    assert len(specs) == 3  # S242：list/mark_done/＋register
    register = impls[2]

    r = _call(register, "plan_register", chapter_order=3, title="第三章", content="酒会潜入")
    assert r.ok is True and "已登记" in r.content

    # 同章重登 = 更新内容（不重复建条）
    r2 = _call(
        register, name="plan_register", chapter_order=3, title="第三章", content="改：直接闯入"
    )
    assert r2.ok is True and "已更新" in r2.content
    entries = plans.list("main")
    assert len(entries) == 1 and "闯入" in entries[0].content

    # done 状态保留：标完成后再重登，不被打回 planned
    plans.add(4, "第四章", "x")
    target = next(p for p in plans.list("main") if p.chapter_order == 4)
    plans.update(target.id, status="done")
    r3 = _call(register, "plan_register", chapter_order=4, title="第四章", content="y")
    assert r3.ok is True
    assert next(p for p in plans.list("main") if p.chapter_order == 4).status == "done"

    # 非法参数
    assert _call(register, "plan_register", chapter_order=0, title="t", content="c").ok is False
    assert _call(register, "plan_register", chapter_order="abc", title="t", content="c").ok is False


# ---------------------------------------------------------------------------
# setting_register：设定入档（source=agent / 缺省值 / 与 read_setting 查证闭环）
# ---------------------------------------------------------------------------
def test_setting_register_and_query_hit() -> None:
    settings = WorldSettingStore(_db())
    _, reg = make_setting_register_implementer(settings)

    r = _call(
        reg,
        "setting_register",
        name="换形药",
        content="换形药可暂时改变外貌，超时当众现形",
        category="能力体系",
    )
    assert r.ok is True
    e = settings.list("main")[0]
    assert e.source == "agent" and e.name == "换形药" and e.category == "能力体系"

    # 缺省：name 取内容前 12 字，category=世界观
    r2 = _call(reg, "setting_register", content="湖女诅咒：不成为超凡者就会死")
    assert r2.ok is True
    e2 = next(x for x in settings.list("main") if x.name.startswith("湖女诅咒"))
    assert e2.category == "世界观"

    # 查证闭环：登记后 read_setting 可命中
    _, query = make_setting_implementer(settings)
    rq = _call(query, keyword="换形药")
    assert rq.ok is True and "现形" in rq.content


# ---------------------------------------------------------------------------
# 预置模板「叙事树提炼」e2e：章题轨迹 → fake 模型出草案 → 落库
# ---------------------------------------------------------------------------
def test_tree_extract_template_runs() -> None:
    class FakeTreeModel:
        model_name = "fake-tree"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            draft = [
                {
                    "id": "n1",
                    "parent": None,
                    "kind": "main",
                    "chosen": True,
                    "content": "开篇：主角登场雾城",
                },
                {
                    "id": "n2",
                    "parent": "n1",
                    "kind": "main",
                    "chosen": True,
                    "content": "中段：发现怀表秘密",
                },
                {
                    "id": "n3",
                    "parent": "n1",
                    "kind": "subplot",
                    "chosen": False,
                    "content": "支线：旧友线索",
                },
            ]
            return ModelOutput(text=json.dumps(draft, ensure_ascii=False), tool_calls=[])

    db = Path(tempfile.mkdtemp()) / "tree.db"
    client = TestClient(build_app(model=FakeTreeModel(), db_path=db))

    from anyspark.store.sqlite import ChapterStore

    cs = ChapterStore(str(db))
    for i in range(1, 4):
        cs.upsert("main", f"第{i}章 标题{i}", f"内容{i}", i)

    # 模板已预置（build_app 种子）
    tpls = client.get("/api/workflows").json()
    tpl = next(t for t in tpls if t["name"] == "叙事树提炼")

    task_id = client.post(f"/api/workflows/{tpl['id']}/run", json={"book_id": "main"}).json()[
        "task_id"
    ]
    t: dict[str, Any] = {}
    for _ in range(30):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert t["status"] == "done", t.get("error")

    tree = StoryTreeStore(str(db))
    nodes = tree.list_nodes("main")
    assert len(nodes) == 3
    roots = [n for n in nodes if n.parent_id is None]
    assert len(roots) == 1 and roots[0].kind == "root"  # 无父节点归一为根
    branch = next(n for n in nodes if "旧友线索" in n.content)
    assert branch.chosen is False


# TestClient 延迟导入（与 test_workflow_api 同款，避免模块级拉起 httpx）
