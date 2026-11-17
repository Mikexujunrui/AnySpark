"""UserSkeletonStore 测试（S195）：用户自定义骨架检测项持久化。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from anyspark.check import SKELETON_CHECKS
from anyspark.server.check_store import UserSkeletonStore


@pytest.fixture()
def store(tmp_path: Any) -> Iterator[UserSkeletonStore]:
    db_path = tmp_path / "test_skeleton.db"
    s = UserSkeletonStore(db_path)
    yield s


def test_addition_and_list(store: UserSkeletonStore) -> None:
    store.add("自定义", "检查XX是否与第N章一致")
    items = store.list_additions()
    assert len(items) == 1
    assert items[0].category == "自定义"
    assert "XX" in items[0].description


def test_delete_addition(store: UserSkeletonStore) -> None:
    item_id = store.add("临时", "临时检测项")
    assert store.delete_addition(item_id) is True
    assert len(store.list_additions()) == 0


def test_delete_addition_by_category(store: UserSkeletonStore) -> None:
    store.add("类别A", "检测A")
    store.add("类别A", "检测A2")  # 同名 category 可多条
    assert store.delete_addition_by_category("类别A") is True
    assert len(store.list_additions()) == 0


def test_deletion_and_restore(store: UserSkeletonStore) -> None:
    store.add_deletion("一致性")
    deletions = store.list_deletions()
    assert "一致性" in deletions

    store.remove_deletion("一致性")
    deletions = store.list_deletions()
    assert "一致性" not in deletions


def test_merged_checks(store: UserSkeletonStore) -> None:
    # 默认 7 项
    merged = store.merged_checks(list(SKELETON_CHECKS))
    assert len(merged) == 7

    # 删除一个默认项
    store.add_deletion("一致性")
    merged = store.merged_checks(list(SKELETON_CHECKS))
    assert len(merged) == 6
    assert all(m.category != "一致性" for m in merged)

    # 添加一个用户项
    store.add("节奏感", "检查段落长短交替是否单调")
    merged = store.merged_checks(list(SKELETON_CHECKS))
    assert len(merged) == 7  # 6 + 1
    assert any(m.category == "节奏感" for m in merged)


def test_deletion_idempotent(store: UserSkeletonStore) -> None:
    store.add_deletion("一致性")
    store.add_deletion("一致性")  # 重复删除不报错
    assert len(store.list_deletions()) == 1


def test_remove_nonexistent_deletion(store: UserSkeletonStore) -> None:
    # 删除不存在的标记返回 False
    assert store.remove_deletion("不存在") is False


def test_check_tool_accepts_custom_checks() -> None:
    """check_text 工具与路由同源：调用方注入的自定义检测项生效。

    S246 接线补缺的回归防护——agent 自查必须看得见用户自定义检测项，
    否则工具与 /api/check 两条通道行为分裂。
    """
    import json

    from anyspark.check.skeleton import SkeletonCheckItem
    from anyspark.core.protocol import ToolSpec
    from anyspark.core.types import Message, ModelOutput, ToolResult
    from anyspark.server.tools_check import make_check_implementer

    class FakeCheckModel:
        model_name = "fake-check"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            prompt = messages[0].content if messages else ""
            if "自定义项" in prompt:
                return ModelOutput(
                    text=json.dumps(
                        [{"message": "命中", "evidence": "第1段", "severity": "hard"}],
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                )
            return ModelOutput(text="[]", tool_calls=[])

    custom = [SkeletonCheckItem("自定义项", "检测自定义问题")]
    _, impl = make_check_implementer(FakeCheckModel(), checks=custom)
    spec = ToolSpec(name="check_text", description="t", params=[])
    r = impl(spec, {"text": "测试正文。"})
    assert isinstance(r, ToolResult)
    assert r.ok is True and "命中" in r.content
