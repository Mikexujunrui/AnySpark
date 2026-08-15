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
