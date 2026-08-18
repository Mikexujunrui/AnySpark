"""anyspark.server.update_checker — 版本检测（S164，参考 v3 update_checker）。

比较本地版本（根 pyproject.toml）与 GitHub 最新 Release（公开 API），
供前端启动时提示"发现新版本"。纯只读：只 GET releases/latest，
从不修改本地；结果内存缓存 300s（GitHub 未认证限流 60 req/h）。

版本比较：tag 形如 v4.0.0 → (4,0,0) 元组比较，尾部非数字后缀忽略。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, cast

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）

# GitHub 仓库与 API（公开只读）
GITHUB_REPO = "Mikexujunrui/AnySpark"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

# 本地版本来源：根 pyproject.toml（源码模式）或 frozen 资源根（PyInstaller datas 已打入）
# S171：frozen 模式 __file__ 指向 _MEIPASS 解包目录，parents[5] 失效（指向解包目录外）；
# anyspark.spec datas 把 pyproject.toml 打进解包根（_MEIPASS/pyproject.toml）。
_frozen_root = (
    Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", "")
    else None
)
_PYPROJECT_CANDIDATES = [
    p
    for p in (
        _frozen_root / "pyproject.toml" if _frozen_root is not None else None,
        Path(__file__).resolve().parents[5] / "pyproject.toml",  # 源码模式：仓库根
        Path(__file__).resolve().parent / "pyproject.toml",
    )
    if p is not None
]

_cache: dict[str, Any] = {}
_CACHE_TTL = 300  # 秒


def _read_version_from(candidates: list[Path]) -> str | None:
    """从候选 pyproject 路径读 [project].version；全部读不到返回 None。"""
    import tomllib

    for p in candidates:
        if not p.exists():
            continue
        try:
            with open(p, "rb") as fh:
                data = tomllib.load(fh)
            v = cast(str, data.get("project", {}).get("version", ""))
            return v or None
        except Exception:
            continue
    return None


def get_local_version() -> str | None:
    """读本地版本（根 pyproject.toml [project].version）。读不到返回 None。"""
    return _read_version_from(_PYPROJECT_CANDIDATES)


def _parse_version(v: str) -> tuple[int, int, int]:
    """v4.0.0 / 4.0.0-beta → (4,0,0)；尾部非数字忽略。"""
    v = (v or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def _is_newer(latest: str, current: str) -> bool:
    """latest 严格大于 current 才算有更新。"""
    return _parse_version(latest) > _parse_version(current)


def fetch_latest_release() -> dict[str, Any] | None:
    """GET GitHub releases/latest；404（无 Release）/网络失败 → None；结果缓存 300s。"""
    now = time.time()
    if _cache and now - _cache.get("_ts", 0) < _CACHE_TTL:
        return cast(dict[str, Any] | None, _cache.get("data"))
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(RELEASES_API, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 404:
            data = None
        else:
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    _cache.clear()
    _cache["_ts"] = now
    _cache["data"] = data
    return cast(dict[str, Any] | None, data)


def check_for_update() -> dict[str, Any]:
    """完整检查：{current_version, latest_version, has_update, release_url, ...}。

    只读操作，应用更新交给用户（跳转 Release 页自行下载）。
    S171：本地版本读不到（None）时不提示更新——unknown 不参与比较，
    避免打包资源缺失/路径异常时永远显示"发现新版本"横幅误导用户。
    """
    current = get_local_version()
    release = fetch_latest_release()
    if release is None:
        return {
            "current_version": current or "unknown",
            "latest_version": None,
            "has_update": False,
            "release_url": RELEASES_PAGE,
            "release_notes": None,
            "published_at": None,
        }
    tag = str(release.get("tag_name", ""))
    return {
        "current_version": current or "unknown",
        "latest_version": tag,
        # 本地版本未知 → 不提示（unknown 不参与比较，避免永远显示横幅）
        "has_update": _is_newer(tag, current) if current is not None else False,
        "release_url": str(release.get("html_url") or RELEASES_PAGE),
        "release_notes": str(release.get("body") or "")[:500],
        "published_at": release.get("published_at"),
    }
