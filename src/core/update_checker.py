# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Update checker — compares the local project version against the latest
GitHub Release, so the frontend can notify users when a new version ships.

The check is a pure read operation (GET to the public GitHub Releases API);
it never modifies the local install. Results are cached for a few minutes
to stay well within GitHub's unauthenticated rate limit (60 req/h).
"""

import logging
import time
import tomllib

import httpx

from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PYPROJECT = PROJECT_ROOT / "pyproject.toml"

# GitHub repository used as the release source (owner/name).
GITHUB_REPO = "Mikexujunrui/AnySpark"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

# In-memory cache so repeated checks within a short window don't hit GitHub.
_cache: dict = {}
_CACHE_TTL = 300  # seconds


def get_local_version() -> str:
    """Read the current project version from ``pyproject.toml``."""
    try:
        with open(PYPROJECT, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "0.0.0")
    except Exception as e:
        logger.warning("Failed to read local version from %s: %s", PYPROJECT, e)
        return "0.0.0"


def _parse_version(v: str) -> tuple:
    """Parse a version string like ``v1.2.3`` into a comparable ``(1, 2, 3)`` tuple.

    Trailing non-numeric suffixes (e.g. ``-beta``) are ignored so that
    ``1.0.0-beta`` parses as ``(1, 0, 0)``.
    """
    v = (v or "").strip().lstrip("vV")
    parts = []
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
    return tuple(parts[:3])


def _is_newer(latest: str, current: str) -> bool:
    """Return True only when ``latest`` is strictly greater than ``current``."""
    return _parse_version(latest) > _parse_version(current)


def fetch_latest_release() -> dict | None:
    """Fetch the latest published GitHub release.

    Returns ``None`` when the repository has no releases yet (HTTP 404) or
    when the network call fails. A successful result is cached briefly.
    """
    now = time.time()
    if _cache and now - _cache.get("_ts", 0) < _CACHE_TTL:
        return _cache.get("data")

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(
                RELEASES_API,
                headers={"Accept": "application/vnd.github+json"},
            )
        if resp.status_code == 404:
            _cache.clear()
            _cache["_ts"] = now
            _cache["data"] = None
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Failed to fetch latest release from GitHub: %s", e)
        return None

    _cache.clear()
    _cache["_ts"] = now
    _cache["data"] = data
    return data


def check_for_update() -> dict:
    """Compare the local version with the latest GitHub release.

    The returned dict always contains ``current_version`` and ``has_update``;
    the remaining fields are populated when a release exists. This is a
    read-only operation — applying an update is left to the user.
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
            "error": None,
            "message": "尚无正式发布版本",
        }

    tag = release.get("tag_name", "")
    return {
        "current_version": current,
        "latest_version": tag,
        "has_update": _is_newer(tag, current),
        "release_url": release.get("html_url", RELEASES_PAGE),
        "release_notes": release.get("body") or "",
        "published_at": release.get("published_at"),
        "error": None,
    }
