"""anyspark.align.signals — 信号采集测试。"""

import tempfile
from pathlib import Path

from anyspark.align import SignalCollector, SignalStore


def _store() -> tuple[SignalStore, SignalCollector]:
    s = SignalStore(Path(tempfile.mkdtemp()) / "test.db")
    return s, SignalCollector(s)


def test_collect_modified_with_delta() -> None:
    store, col = _store()
    try:
        sig = col.modified("第一版文本", "第一版文本改了很多很多", context="稿纸")
        assert sig.kind == "modified"
        assert sig.delta > 0
        assert sig.context == "稿纸"
    finally:
        store.close()


def test_collect_custom_statement() -> None:
    store, col = _store()
    try:
        sig = col.custom("我不要第三人称视角", context="对话")
        assert sig.kind == "custom"
        assert "第三人称" in sig.content
    finally:
        store.close()


def test_recent_returns_newest_first() -> None:
    store, col = _store()
    try:
        col.accepted("A")
        col.deleted("B")
        recent = store.recent(book_id="main")
        assert recent[0].kind == "deleted"  # 最新在前
        assert len(recent) == 2
    finally:
        store.close()


def test_delta_ratio_bounds() -> None:
    from anyspark.align.signals import _delta_ratio

    assert _delta_ratio("", "") == 0.0
    assert _delta_ratio("abc", "") == 1.0
    assert _delta_ratio("abc", "abc") == 0.0
    d = _delta_ratio("abc", "abXc")
    assert 0 < d < 1


def test_unprocessed_cursor_and_mark() -> None:
    """增量游标：未提炼信号按时间序取、标记后推进、recent() 兼容。"""
    store, col = _store()
    try:
        col.accepted("A")
        col.deleted("B")
        col.custom("C")
        pending = store.unprocessed(book_id="main")
        assert len(pending) == 3
        # 时间序（rowid 升序）：最早未提炼先处理
        assert [s.kind for s in pending] == ["accepted", "deleted", "custom"]
        store.mark_processed([pending[0].id])
        rest = store.unprocessed(book_id="main")
        assert len(rest) == 2
        assert rest[0].kind == "deleted"  # 已提炼的不再返回
        # recent() 语义不变：仍返回全部（含已提炼）
        assert len(store.recent(book_id="main")) == 3
        # 幂等：重复标记不报错
        store.mark_processed([pending[0].id, "no-such-id"])
        assert len(store.unprocessed(book_id="main")) == 2
    finally:
        store.close()


def test_unprocessed_limit_and_book_scope() -> None:
    """分批上限与书隔离。"""
    store, col = _store()
    try:
        for i in range(5):
            col.accepted(f"m{i}")
        assert len(store.unprocessed(limit=3, book_id="main")) == 3
        assert len(store.unprocessed(limit=3, book_id="other")) == 0  # 书隔离
        assert len(store.unprocessed(book_id="main")) == 5
    finally:
        store.close()


def test_old_schema_migration() -> None:
    """旧库（无 processed 列）打开后自动补列，不丢数据。"""
    import sqlite3
    import tempfile
    from pathlib import Path

    db = Path(tempfile.mkdtemp()) / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE signals (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
        "content TEXT NOT NULL, context TEXT NOT NULL DEFAULT '', "
        "delta REAL NOT NULL DEFAULT 0, book_id TEXT NOT NULL DEFAULT 'main', "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO signals (id, kind, content, created_at) "
        "VALUES ('x1', 'accepted', '旧信号', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    store = SignalStore(db)
    try:
        # 旧数据保留且游标可用（processed 默认 0=未提炼）
        pending = store.unprocessed(book_id="main")
        assert len(pending) == 1
        assert pending[0].content == "旧信号"
        store.mark_processed([pending[0].id])
        assert len(store.unprocessed(book_id="main")) == 0
    finally:
        store.close()
