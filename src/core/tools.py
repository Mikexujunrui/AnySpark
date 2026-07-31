"""Tool registry and validation — facade module.

Re-exports the infrastructure from :mod:`core.tool_registry` and triggers
tool registration from :mod:`core.tool_defs`, then applies behavioral
metadata (TOOL_META). Keeping the import path ``core.tools`` stable lets all
existing callers work unchanged.
"""

from __future__ import annotations

from .tool_defs import *  # noqa: F401,F403 — registers tools at import time
from .tool_registry import (  # noqa: F401
    DOOM_LOOP_THRESHOLD,
    MAX_TOOL_OUTPUT_CHARS,
    MAX_TOOL_OUTPUT_TOKENS,
    TOOL_META,
    DoomLoopDetector,
    Tool,
    ToolRegistry,
    _apply_tool_meta,
    build_tool_docs,
    registry,
    tools_with,
    truncate_tool_output,
    validate_tool_input,
)

_apply_tool_meta()

__all__ = [
    "Tool",
    "ToolRegistry",
    "DoomLoopDetector",
    "registry",
    "truncate_tool_output",
    "validate_tool_input",
    "tools_with",
    "build_tool_docs",
    "MAX_TOOL_OUTPUT_CHARS",
    "MAX_TOOL_OUTPUT_TOKENS",
    "DOOM_LOOP_THRESHOLD",
    "TOOL_META",
]
