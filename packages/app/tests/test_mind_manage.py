"""S73d 心智纠正工具测试：mind_update / mind_delete（用户明确要求时 agent 代执行）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import ManualEntry, ManualStore
from anyspark.server.tools_domain import make_mind_manage_implementer


def _manual() -> ManualStore:
    db = Path(tempfile.mkdtemp()) / "t.db"
    return ManualStore(db)


def _seed(manual: ManualStore) -> str:
    e = manual.add(
        ManualEntry(
            content="避免使用破折号",
            source="auto",
            confidence=0.8,
            category="habit",
            scope="project",
            book_id="main",
        )
    )
    return e.id


def test_mind_update_content_and_category() -> None:
    manual = _manual()
    eid = _seed(manual)
    specs, impls = make_mind_manage_implementer(manual)
    assert [s.name for s in specs] == ["mind_update", "mind_delete"]
    upd = impls[0]

    # 按 id 改内容 + 分类
    r = upd(specs[0], {"query": eid, "content": "避免使用破折号和省略号", "category": "habit"})
    assert r.ok is True, r.content
    updated = manual.get(eid)
    assert updated is not None and "省略号" in updated.content

    # 按关键词定位改
    r2 = upd(specs[0], {"query": "破折号", "content": "避免破折号"})
    assert r2.ok is True

    # 多命中 → 提示精确定位
    manual.add(ManualEntry(content="对话避免破折号", source="user", category="style"))
    r3 = upd(specs[0], {"query": "破折号", "content": "x"})
    assert r3.ok is False and "匹配到" in r3.content

    # 未找到
    r4 = upd(specs[0], {"query": "不存在的词", "content": "x"})
    assert r4.ok is False and "未找到" in r4.content


def test_mind_delete_and_locked() -> None:
    manual = _manual()
    eid = _seed(manual)
    specs, impls = make_mind_manage_implementer(manual)
    dele = impls[1]

    # 删除（返回被删内容）
    r = dele(specs[1], {"query": eid})
    assert r.ok is True
    assert "破折号" in r.content
    assert manual.get(eid) is None

    # 锁定条目不可改（用户主权）
    e2 = manual.add(
        ManualEntry(
            content="锁定条目", source="user", confidence=0.9, locked=True, category="style"
        )
    )
    r2 = impls[0](specs[0], {"query": e2.id, "content": "改了"})
    assert r2.ok is False and "锁定" in r2.content
    # 但锁定状态本身可以切换（用户明确要求）
    r3 = impls[0](specs[0], {"query": e2.id, "locked": False})
    assert r3.ok is True
    e2_after = manual.get(e2.id)
    assert e2_after is not None and e2_after.locked is False
