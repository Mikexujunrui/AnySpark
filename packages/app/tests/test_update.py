"""S164/S171：版本检测——版本解析/比较/本地版本读取/未知版本不提示。"""

from __future__ import annotations

import re

from anyspark.server import update_checker as uc
from anyspark.server.update_checker import _is_newer, _parse_version, get_local_version


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
    v = get_local_version()
    assert v is not None
    assert re.match(r"^\d+\.\d+\.\d+$", v), f"版本格式应为 X.Y.Z，实际 {v}"


def test_local_version_reads_custom_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """S171：frozen 打包候选路径命中——pyproject.toml 在解包根（_MEIPASS）也能读到。"""
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "4.0.2"\n', encoding="utf-8")
    monkey_candidates = [tmp_path / "pyproject.toml"]
    # 直接验证候选读取逻辑（候选列表由模块级按 frozen/源码模式装配）
    from anyspark.server.update_checker import _read_version_from

    assert _read_version_from(monkey_candidates) == "4.0.2"


def test_local_version_none_when_no_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """S171：所有候选路径读不到 → 返回 None（而非 0.0.0）。"""
    from anyspark.server.update_checker import _read_version_from

    assert _read_version_from([tmp_path / "nope.toml"]) is None


def test_check_for_update_unknown_local_no_banner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """S171：本地版本读不到 → 不提示更新——即使 GitHub 有更新版本
    （避免打包资源缺失/路径异常时永远显示"发现新版本"横幅误导用户）。"""
    monkeypatch.setattr(uc, "get_local_version", lambda: None)
    monkeypatch.setattr(uc, "fetch_latest_release", lambda: {"tag_name": "v9.9.9"})
    info = uc.check_for_update()
    assert info["has_update"] is False
    assert info["current_version"] == "unknown"


def test_check_for_update_same_version_no_banner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """S171：本地版本 == 最新版本 → 不提示（相等不算更新）。"""
    monkeypatch.setattr(uc, "get_local_version", lambda: "4.0.2")
    monkeypatch.setattr(uc, "fetch_latest_release", lambda: {"tag_name": "v4.0.2"})
    info = uc.check_for_update()
    assert info["has_update"] is False
    assert info["current_version"] == "4.0.2"


def test_check_for_update_newer_version_banner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """S171：本地版本 < 最新版本 → 正常提示。"""
    monkeypatch.setattr(uc, "get_local_version", lambda: "4.0.1")
    monkeypatch.setattr(uc, "fetch_latest_release", lambda: {"tag_name": "v4.0.2"})
    info = uc.check_for_update()
    assert info["has_update"] is True
    assert info["latest_version"] == "v4.0.2"
