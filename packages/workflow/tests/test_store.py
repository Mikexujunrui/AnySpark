"""WorkflowStore 持久化层测试（S188 补缺）：草稿生命周期 / builtin 保护 / 节点状态。

覆盖 test_workflow.py 未触及的 14 个 store 方法：
- is_builtin / mark_builtin_by_name / delete_template（builtin 保护）
- add_draft / list_drafts / get_draft / promote_draft / reject_draft / delete_draft（草稿闸门）
- update_node_state / increment_attempts / append_result / node_status / node_output（断点恢复基础）
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from anyspark.workflow import WorkflowDef, WorkflowStore


def _wf_dict(name: str = "测试流程") -> dict[str, Any]:
    return {
        "name": name,
        "description": "测试用",
        "nodes": [
            {"id": "start", "kind": "script", "label": "开始", "params": {"function": "noop"}},
            {"id": "end", "kind": "script", "label": "结束", "params": {"function": "noop"}},
        ],
        "edges": [{"source": "start", "target": "end"}],
    }


@pytest.fixture()
def store(tmp_path: Any) -> Iterator[WorkflowStore]:
    db_path = tmp_path / "test_workflow.db"
    s = WorkflowStore(str(db_path))
    yield s
    # SQLite 连接随进程结束自动释放；tmp_path 由 pytest 管理


# ---------------------------------------------------------------------------
# builtin 保护（is_builtin / mark_builtin_by_name / delete_template）
# ---------------------------------------------------------------------------


class TestBuiltinProtection:
    def test_user_template_not_builtin(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("用户流程"))
        store.add_template(wf)
        assert store.is_builtin(wf.id) is False

    def test_builtin_template_flagged(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("预置流程"))
        store.add_template(wf, builtin=True)
        assert store.is_builtin(wf.id) is True

    def test_mark_builtin_by_name(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("迁移流程"))
        store.add_template(wf)
        assert store.is_builtin(wf.id) is False
        store.mark_builtin_by_name("迁移流程")
        assert store.is_builtin(wf.id) is True

    def test_mark_builtin_nonexistent_name_noop(self, store: WorkflowStore) -> None:
        # 不存在的名称不影响已有模板
        store.mark_builtin_by_name("不存在")
        # 无异常即通过

    def test_delete_user_template_succeeds(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("可删流程"))
        store.add_template(wf)
        assert store.delete_template(wf.id) is True
        assert store.get_template(wf.id) is None

    def test_delete_nonexistent_returns_false(self, store: WorkflowStore) -> None:
        assert store.delete_template("nonexistent-id") is False


# ---------------------------------------------------------------------------
# 草稿生命周期（add/list/get/promote/reject/delete）
# ---------------------------------------------------------------------------


class TestDraftLifecycle:
    def test_add_and_list_draft(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("草稿1"))
        store.add_draft(wf, hint="AI 生成")
        drafts = store.list_drafts()
        assert len(drafts) == 1
        assert drafts[0]["name"] == "草稿1"
        assert drafts[0]["hint"] == "AI 生成"
        assert drafts[0]["status"] == "draft"

    def test_get_draft(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("草稿2"))
        store.add_draft(wf)
        result = store.get_draft(wf.id)
        assert result is not None
        assert result.name == "草稿2"

    def test_get_draft_nonexistent(self, store: WorkflowStore) -> None:
        assert store.get_draft("nonexistent") is None

    def test_promote_draft_to_template(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("待转正"))
        store.add_draft(wf)
        promoted = store.promote_draft(wf.id)
        assert promoted is not None
        assert promoted.name == "待转正"
        # 模板表有记录
        assert store.get_template(wf.id) is not None
        # 草稿状态变为 promoted
        drafts = store.list_drafts()
        assert drafts[0]["status"] == "promoted"

    def test_promote_nonexistent_returns_none(self, store: WorkflowStore) -> None:
        assert store.promote_draft("nonexistent") is None

    def test_reject_draft(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("待拒绝"))
        store.add_draft(wf)
        assert store.reject_draft(wf.id) is True
        drafts = store.list_drafts()
        assert drafts[0]["status"] == "rejected"

    def test_reject_nonexistent_returns_false(self, store: WorkflowStore) -> None:
        assert store.reject_draft("nonexistent") is False

    def test_delete_draft(self, store: WorkflowStore) -> None:
        wf = WorkflowDef.from_dict(_wf_dict("待删除"))
        store.add_draft(wf)
        assert store.delete_draft(wf.id) is True
        assert store.get_draft(wf.id) is None

    def test_delete_draft_nonexistent(self, store: WorkflowStore) -> None:
        assert store.delete_draft("nonexistent") is False

    def test_multiple_drafts_ordered_by_created_desc(self, store: WorkflowStore) -> None:
        import time

        wf1 = WorkflowDef.from_dict(_wf_dict("草稿A"))
        store.add_draft(wf1)
        time.sleep(0.01)
        wf2 = WorkflowDef.from_dict(_wf_dict("草稿B"))
        store.add_draft(wf2)
        drafts = store.list_drafts()
        assert len(drafts) == 2
        # 最新的在前
        assert drafts[0]["name"] == "草稿B"


# ---------------------------------------------------------------------------
# 节点状态管理（断点恢复基础）
# ---------------------------------------------------------------------------


class TestNodeState:
    @pytest.fixture()
    def task_id(self, store: WorkflowStore) -> str:
        """创建一个带节点的任务。"""
        wf = WorkflowDef.from_dict(_wf_dict("节点测试"))
        store.add_template(wf)
        return store.create_task(wf, book_id="main", template_id=wf.id)

    def test_node_status_initial_pending(self, store: WorkflowStore, task_id: str) -> None:
        # create_task 初始化所有节点为 pending
        assert store.node_status(task_id, "start") == "pending"
        assert store.node_status(task_id, "end") == "pending"

    def test_node_status_nonexistent_pending(self, store: WorkflowStore, task_id: str) -> None:
        assert store.node_status(task_id, "nonexistent") == "pending"

    def test_node_output_initial_empty(self, store: WorkflowStore, task_id: str) -> None:
        assert store.node_output(task_id, "start") == ""

    def test_update_node_state(self, store: WorkflowStore, task_id: str) -> None:

        task = store.get_task(task_id)
        assert task is not None
        wf = store.get_template(task["template_id"])
        assert wf is not None
        node = wf.nodes[0]
        store.update_node_state(task_id, node, "done", output="结果文本", token_usage=100)
        assert store.node_status(task_id, node.id) == "done"
        assert store.node_output(task_id, node.id) == "结果文本"

    def test_update_node_state_with_error(self, store: WorkflowStore, task_id: str) -> None:

        task = store.get_task(task_id)
        assert task is not None
        wf = store.get_template(task["template_id"])
        assert wf is not None
        node = wf.nodes[0]
        store.update_node_state(task_id, node, "failed", error="执行失败")
        task = store.get_task(task_id)
        assert task is not None
        states = {s["node_id"]: s for s in task["node_states"]}
        assert states[node.id]["error"] == "执行失败"
        assert states[node.id]["status"] == "failed"

    def test_increment_attempts(self, store: WorkflowStore, task_id: str) -> None:
        # 初始 attempts=0
        store.increment_attempts(task_id, "start")
        store.increment_attempts(task_id, "start")
        task = store.get_task(task_id)
        assert task is not None
        states = {s["node_id"]: s for s in task["node_states"]}
        assert states["start"]["attempts"] == 2

    def test_increment_attempts_nonexistent(self, store: WorkflowStore, task_id: str) -> None:
        result = store.increment_attempts(task_id, "nonexistent")
        assert result == 0

    def test_append_result(self, store: WorkflowStore, task_id: str) -> None:
        store.append_result(task_id, "chapter_text", "章节内容")
        store.append_result(task_id, "title", "第一章")
        task = store.get_task(task_id)
        assert task is not None
        assert task["results"]["chapter_text"] == "章节内容"
        assert task["results"]["title"] == "第一章"

    def test_append_result_overwrites(self, store: WorkflowStore, task_id: str) -> None:
        store.append_result(task_id, "key", "旧值")
        store.append_result(task_id, "key", "新值")
        task = store.get_task(task_id)
        assert task is not None
        assert task["results"]["key"] == "新值"

    def test_update_node_state_preserves_attempts(self, store: WorkflowStore, task_id: str) -> None:

        task = store.get_task(task_id)
        assert task is not None
        wf = store.get_template(task["template_id"])
        assert wf is not None
        node = wf.nodes[0]
        store.increment_attempts(task_id, node.id)
        store.increment_attempts(task_id, node.id)
        # update_node_state 不传 attempts 时保留当前值
        store.update_node_state(task_id, node, "done")
        task = store.get_task(task_id)
        assert task is not None
        states = {s["node_id"]: s for s in task["node_states"]}
        assert states[node.id]["attempts"] == 2
