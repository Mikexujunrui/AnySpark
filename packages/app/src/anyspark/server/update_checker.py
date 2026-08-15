"""anyspark.server.update_checker — 版本检测（S164，参考 v3 update_checker）。

比较本地版本（根 pyproject.toml）与 GitHub 最新 Release（公开 API），
供前端启动时提示"发现新版本"。纯只读：只 GET releases/latest，
从不修改本地；结果内存缓存 300s（GitHub 未认证限流 60 req/h）。

版本比较：tag 形如 v4.0.0 → (4,0,0) 元组比较，尾部非数字后缀忽略。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）

# GitHub 仓库与 API（公开只读）
GITHUB_REPO = "Mikexujunrui/AnySpark"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

# 本地版本来源：根 pyproject.toml（源码模式）或 frozen 资源根（PyInstaller datas 已打入）
_PROJECT_ROOT = Path(__file__).resolve().parents[5]  # packages/app/src/anyspark/server → 仓库根
_PYPROJECT_CANDIDATES = [
    _PROJECT_ROOT / "pyproject.toml",
    Path(__file__).resolve().parent / "pyproject.toml",
]

_cache: dict[str, Any] = {}
_CACHE_TTL = 300  # 秒


def get_local_version() -> str:
    """读本地版本（根 pyproject.toml [project].version）。读不到回退 0.0.0。"""
    import tomllib

    for p in _PYPROJECT_CANDIDATES:
        if not p.exists():
            continue
        try:
            with open(p, "rb") as fh:
                data = tomllib.load(fh)
            v = cast(str, data.get("project", {}).get("version", "0.0.0"))
            return v
        except Exception:
            continue
    return "0.0.0"


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
    """
    current = get_local_version()
    release = fetch_latest_release()
    if release is None:
        return {
            "current_version": current,
            "latest_version": None,
            "has_update": False,
            "release_url": RELEASES_PAGE,
            "release_notes": None,
            "published_at": None,
        }
    tag = str(release.get("tag_name", ""))
    return {
        "current_version": current,
        "latest_version": tag,
        "has_update": _is_newer(tag, current),
        "release_url": str(release.get("html_url") or RELEASES_PAGE),
        "release_notes": str(release.get("body") or "")[:500],
        "published_at": release.get("published_at"),
    }
