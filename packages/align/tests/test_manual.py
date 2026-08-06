"""anyspark.align.manual — 说明书存储测试。"""

import tempfile
from pathlib import Path

from anyspark.align import ManualEntry, ManualStore, render_manual


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test.db"


def test_manual_crud() -> None:
    store = ManualStore(_db())
    try:
        e = store.add(ManualEntry(content="不要破折号", source="user", confidence=0.9, locked=True))
        got = store.get(e.id)
        assert got is not None
        assert got.content == "不要破折号"
        assert got.locked is True

        store.delete(e.id)
        assert store.get(e.id) is None
    finally:
        store.close()


def test_locked_entry_cannot_update() -> None:
    store = ManualStore(_db())
    try:
        e = store.add(ManualEntry(content="原有", locked=True))
        updated = store.update(e.id, content="被锁不可改")
        assert updated is not None
        assert updated.content == "原有"  # 锁定条目拒绝修改
    finally:
        store.close()


def test_project_vs_global_scope() -> None:
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="项目偏好", scope="project", book_id="bookA"))
        store.add(ManualEntry(content="全局偏好", scope="global"))
        project = store.list("project", "bookA")
        global_list = store.list("global")
        assert [e.content for e in project] == ["项目偏好"]
        assert [e.content for e in global_list] == ["全局偏好"]
    finally:
        store.close()


def test_render_manual_readable() -> None:
    entries = [
        ManualEntry(content="主角对话要克制", confidence=0.8),
        ManualEntry(content="禁血腥描写", locked=True, confidence=0.95),
    ]
    text = render_manual(entries)
    assert "主角对话要克制" in text
    assert "[锁定]" in text
    assert "置信度" in text


def test_merge_add_same_theme_merges() -> None:
    """S55 合并：同类别+关键词重叠 → 合并进现有条目（治碎片）。"""
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style"))
        _, did_merge = store.merge_add(
            ManualEntry(content="对话要克制，也少用感叹号", category="style")
        )
        assert did_merge is True
        entries = store.list("project")
        assert len(entries) == 1  # 合并后仍只有一条
        assert "感叹号" in entries[0].content
        assert entries[0].confidence >= 0.5
    finally:
        store.close()


def test_merge_add_disjoint_adds_new() -> None:
    """S55 不重叠：关键词交集不足 → 普通新增。"""
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="对话要克制", category="style"))
        _, did_merge = store.merge_add(ManualEntry(content="我习惯晚上写作", category="habit"))
        assert did_merge is False
        assert len(store.list("project")) == 2  # 不同类别不同主题 → 两条
    finally:
        store.close()


def test_merge_add_locked_not_merged() -> None:
    """S55 锁定条目不合并（用户主权）。"""
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style", locked=True))
        _, did_merge = store.merge_add(
            ManualEntry(content="叙事要克制，少用感叹号", category="style")
        )
        assert did_merge is False
        assert len(store.list("project")) == 2  # 锁定条目不合并 → 新增
    finally:
        store.close()


def test_merge_add_different_category_no_merge() -> None:
    """S55 不同类别不合并（即使关键词相同）。"""
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="对话要克制", category="style"))
        _, did_merge = store.merge_add(ManualEntry(content="对话要克制", category="habit"))
        assert did_merge is False
        assert len(store.list("project")) == 2
    finally:
        store.close()


def test_dedupe_cleans_legacy_duplicates() -> None:
    """S55 dedupe：清理历史重复（同类别+关键词重叠≥2 → 合并+删冗余）。"""
    store = ManualStore(_db())
    try:
        # 模拟历史 3 条重复（S53c 实测发现的脏数据形态）
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style", confidence=0.5))
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style", confidence=0.6))
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style", confidence=0.4))
        # 一条不重复的
        store.add(ManualEntry(content="习惯晚上写作", category="habit"))
        removed = store.dedupe()
        assert removed == 2  # 合并掉 2 条冗余
        entries = store.list("project")
        assert len(entries) == 2  # 1 条合并后的感叹号 + 1 条习惯
        sighao = [e for e in entries if "感叹号" in e.content]
        assert len(sighao) == 1
        assert sighao[0].confidence == 0.6  # 取最高置信度
    finally:
        store.close()


def test_dedupe_keeps_locked() -> None:
    """S55 dedupe：锁定条目不合并（用户主权）。"""
    store = ManualStore(_db())
    try:
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style", locked=True))
        store.add(ManualEntry(content="叙事克制，少用感叹号", category="style"))
        removed = store.dedupe()
        assert removed == 0  # 锁定条目不合并
        assert len(store.list("project")) == 2
    finally:
        store.close()
