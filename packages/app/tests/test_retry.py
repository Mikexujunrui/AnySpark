"""anyspark.server — S11 流程基建（重试）+ 安全底线（沙箱/越界/超长）+ 工具测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from anyspark.server.retry import retry_with_backoff
from anyspark.server.tools_writing import (
    WritingTools,
    _extract_docx_text,
    _resolve_sandbox_path,
)


# ---------------------------------------------------------------------------
# 指数退避重试
# ---------------------------------------------------------------------------
def test_retry_succeeds_on_first() -> None:
    calls = 0

    def fn() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert retry_with_backoff(fn, retries=3, base=0.01) == 42
    assert calls == 1


def test_retry_recovers_after_failures() -> None:
    calls = 0

    def fn() -> int:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("网络抖动")
        return 7

    assert retry_with_backoff(fn, retries=4, base=0.01) == 7
    assert calls == 3


def test_retry_gives_up_and_raises() -> None:
    def fn() -> int:
        raise TimeoutError("超时")

    with pytest.raises(TimeoutError):
        retry_with_backoff(fn, retries=2, base=0.01)


def test_retry_does_not_swallow_business_errors() -> None:
    def fn() -> int:
        raise ValueError("业务错误不重试")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, retries=3, base=0.01)


# ---------------------------------------------------------------------------
# 沙箱越界保护
# ---------------------------------------------------------------------------
def test_sandbox_resolves_relative_only() -> None:
    assert _resolve_sandbox_path("notes/setting.md") is not None
    assert _resolve_sandbox_path("C:/Windows/evil.txt") is None  # 绝对路径拒绝
    assert _resolve_sandbox_path("../secret.db") is None  # .. 越界拒绝
    assert _resolve_sandbox_path("/etc/passwd") is None


def test_file_tools_sandbox_read_write() -> None:

    # 用独立沙箱目录测试（避免污染真实 data/sandbox）
    tmp = Path(tempfile.mkdtemp())
    import anyspark.server.tools_writing as tw

    orig = tw.SANDBOX_DIR
    tw.SANDBOX_DIR = tmp
    try:
        tools = WritingTools.__new__(WritingTools)  # 只测文件工具，跳过 store
        spec = make_spec("write_file")
        r = tools.write_file(
            spec,
            {"path": "notes/a.md", "content": "雾城设定：永远下雨。"},
        )
        assert r.ok and (tmp / "notes" / "a.md").exists()
        r2 = tools.read_file(spec, {"path": "notes/a.md"})
        assert r2.ok and "雾城设定" in r2.content
        # 越界
        r3 = tools.read_file(spec, {"path": "../evil.txt"})
        assert not r3.ok and "越界" in r3.content
        # 超长
        r4 = tools.write_file(spec, {"path": "big.txt", "content": "x" * 60000})
        assert not r4.ok and "超长" in r4.content
    finally:
        tw.SANDBOX_DIR = orig


def make_spec(name: str) -> Any:
    from anyspark.core.protocol import ToolSpec

    return ToolSpec(name=name)


def test_docx_extract_lightweight() -> None:
    # 构造一个最小 docx（zip 包 document.xml）
    import zipfile

    tmp = Path(tempfile.mkdtemp()) / "t.docx"
    xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>第二段</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(tmp, "w") as zf:
        zf.writestr("word/document.xml", xml)
    text = _extract_docx_text(tmp)
    assert "第一段" in text and "第二段" in text


def test_read_chapter_cache_dedup() -> None:
    """S21 已读缓存：同一请求内重复读同一章命中缓存；写后缓存失效。"""
    import tempfile

    from anyspark.server.tools_writing import WritingTools
    from anyspark.store import ChapterStore

    tmp = Path(tempfile.mkdtemp())
    store = ChapterStore(tmp / "c.db")
    store.upsert("main", "第一章", "雨夜，陈渡抵达雾城。", 0)
    tools = WritingTools.__new__(WritingTools)
    tools._chapters = store
    tools._book_id = "main"
    tools._read_cache = {}

    spec = make_spec("read_chapter")
    r1 = tools.read_chapter(spec, {"title": "第一章"})
    r2 = tools.read_chapter(spec, {"title": "第一章"})
    assert r1.ok and r2.ok
    assert "已读缓存" in r2.content  # 第二次命中缓存
    # 写后缓存失效：再读应读到新内容（无缓存标记）
    tools.write_chapter(
        make_spec("write_chapter"), {"title": "第一章", "content": "改写后的正文。"}
    )
    r3 = tools.read_chapter(spec, {"title": "第一章"})
    assert "已读缓存" not in r3.content
    assert "改写后的正文" in r3.content
