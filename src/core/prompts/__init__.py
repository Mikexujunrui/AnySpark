# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Prompt template loader.

Loads LLM prompt templates from the ``prompts/`` directory. Templates are
plain UTF-8 text files with ``{placeholder}`` substitution markers.

Usage::

    from core.prompts import load_prompt
    system = load_prompt("extraction_system").replace("{schemas}", schema_text)

Templates are cached after first load so repeated calls are cheap.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent
_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt template by name (without extension).

    Returns the file content as a string.  Results are cached in memory.
    """
    if name in _cache:
        return _cache[name]

    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        logger.warning("Prompt template not found: %s", path)
        return ""

    content = path.read_text(encoding="utf-8")
    _cache[name] = content
    return content


def reload_prompt(name: str) -> str:
    """Force-reload a prompt template from disk (bypasses cache)."""
    _cache.pop(name, None)
    return load_prompt(name)
