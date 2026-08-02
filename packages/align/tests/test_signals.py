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
