"""S164：版本检测——版本解析/比较/本地版本读取。"""

from __future__ import annotations

from anyspark.server.update_checker import (
    _is_newer,
    _parse_version,
    get_local_version,
)


def test_parse_version() -> None:
    assert _parse_version("v4.0.0") == (4, 0, 0)
    assert _parse_version("4.0.0") == (4, 0, 0)
    assert _parse_version("v3.2.7-beta") == (3, 2, 7)  # 尾部非数字后缀忽略
    assert _parse_version("") == (0, 0, 0)
    assert _parse_version("4.1") == (4, 1, 0)  # 缺段补 0


def test_is_newer() -> None:
    assert _is_newer("v4.1.0", "v4.0.0")
    assert _is_newer("v4.0.0", "v3.2.7")
    assert not _is_newer("v4.0.0", "v4.0.0")  # 相等不算更新
    assert not _is_newer("v4.0.0-beta", "v4.0.0")  # 后缀不影响主版本比较
    assert not _is_newer("v3.9.9", "v4.0.0")


def test_local_version_reads_pyproject() -> None:
    """本地版本应能读到（格式 X.Y.Z；不写死具体值——版本号随发布递增）。"""
    import re

    v = get_local_version()
    assert re.match(r"^\d+\.\d+\.\d+$", v), f"版本格式应为 X.Y.Z，实际 {v}"
