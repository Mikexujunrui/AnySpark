# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tool registry and validation.

Key components:
- ``Tool`` dataclass — tool metadata(name, description, parameters, doc, handler, flags)
- ``ToolRegistry`` — lookup with fuzzy name matching(case/separator/prefix)
- ``validate_tool_input()`` — delegates to Pydantic-based ``validate_with_pydantic()``
- ``build_tool_docs()`` — generates markdown tool documentation from ``Tool.doc`` fields
- ``_apply_tool_meta()`` — merges ``TOOL_META`` behavioral flags into registered tools

See ``tools/executor.py`` for the dispatch table wiring handlers to Tool objects.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .pydantic_validation import validate_with_pydantic
from .token_counter import _get_encoder, count_tokens
from .tool_meta import TOOL_META

logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 200000
MAX_TOOL_OUTPUT_TOKENS = 80000
DOOM_LOOP_THRESHOLD = 3


def truncate_tool_output(output: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if not output:
        return output
    tokens = count_tokens(output)
    if len(output) <= max_chars and tokens <= MAX_TOOL_OUTPUT_TOKENS:
        return output

    total_chars = len(output)
    if tokens > MAX_TOOL_OUTPUT_TOKENS:
        encoder = _get_encoder()
        encoded = encoder.encode(output)
        truncated = encoder.decode(encoded[:MAX_TOOL_OUTPUT_TOKENS])
    else:
        truncated = output[:max_chars]
    return (
        f"{truncated}\n\n"
        f"[输出已截断: 原始 {total_chars} 字符 / {tokens} tokens。"
        f"如需查看完整内容，请使用 read_document 工具指定 offset/limit 分段读取]"
    )


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    handler: Callable = None
    dangerous: bool = False
    doc: str = ""
    streaming: bool = False
    mutates_kb: bool = False
    touches_chapter: bool = False
    context_aware: bool = False

    def to_llm(self) -> dict:
        props = {}
        required = []
        for k, v in self.parameters.items():
            if isinstance(v, dict):
                is_required = v.get("required", True)
                prop = {pk: pv for pk, pv in v.items() if pk != "required"}
                props[k] = prop
                if is_required:
                    required.append(k)
            else:
                props[k] = {"type": "string", "description": str(v)}
                required.append(k)
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return {"name": self.name, "description": self.description, "parameters": schema}

    def to_doc(self) -> str:
        if self.doc:
            body = self.doc
        else:
            body = self.description
        return f"### {self.name}\n{body}\n"


def validate_tool_input(tool: Tool, args: dict) -> tuple[dict, list[str]]:
    return validate_with_pydantic(tool.name, tool.parameters, args)


class DoomLoopDetector:
    def __init__(self, threshold: int = DOOM_LOOP_THRESHOLD):
        self._history: list[str] = []
        self._tool_names: list[str] = []
        self._threshold = threshold
        # Same-tool consecutive streak: only flag if the *exact same tool* is
        # called many times in a row WITHOUT interleaving other tools.
        # Legitimate batch operations (e.g. update_entity x10) are allowed
        # as long as args differ, but if the model calls one tool 12+ times
        # straight it's likely stuck even if args vary slightly.
        self._consecutive_same_tool_max = 25  # 提升阈值以支持批量大纲/实体操作

    def record_call(self, tool_name: str, arguments: str) -> bool:
        sig = f"{tool_name}:{arguments}"
        self._history.append(sig)
        self._tool_names.append(tool_name)

        # Pattern 1: exact same call repeated N times in a row
        if len(self._history) >= self._threshold:
            recent = self._history[-self._threshold :]
            if len(set(recent)) == 1:
                logger.warning(f"Doom loop detected: {tool_name} called {self._threshold} times with same args")
                return True

        # Pattern 2: same tool called consecutively without any other tool in between.
        # Only triggers when the model is truly stuck on one tool (12+ straight calls).
        # Legitimate batch ops like update_entity×8 won't trigger (< 12).
        if len(self._tool_names) >= self._consecutive_same_tool_max:
            tail = self._tool_names[-self._consecutive_same_tool_max :]
            if len(set(tail)) == 1:
                logger.warning(
                    f"Doom loop detected: {tool_name} called {self._consecutive_same_tool_max} "
                    f"times consecutively (no other tool interleaved)"
                )
                return True

        return False

    def reset(self):
        self._history.clear()
        self._tool_names.clear()


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def list_tools(self, exclude_dangerous: bool = False) -> list[dict]:
        tools: list[Tool] = list(self._tools.values())
        if exclude_dangerous:
            tools = [t for t in tools if not t.dangerous]
        return [t.to_llm() for t in tools]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name, with fuzzy fallback for casing/separator
        mismatches (e.g. ``Write_Chapter`` → ``write_chapter``,
        ``search-knowledge`` → ``search_knowledge``).

        Strategy: exact → lowercase → normalized (``-``→``_``) → prefix."""
        tool = self._tools.get(name)
        if tool:
            return tool
        # Lowercase fallback
        lower = name.lower()
        for key, t in self._tools.items():
            if key.lower() == lower:
                return t
        # Separator normalization (- → _)
        normalized = lower.replace("-", "_")
        for key, t in self._tools.items():
            if key.lower() == normalized:
                return t
        # Prefix match (first 8 chars, handles truncated names)
        if len(name) >= 8:
            prefix = name[:8].lower()
            for key, t in self._tools.items():
                if key.lower().startswith(prefix):
                    return t
        return None

    def resolve_name(self, name: str) -> str | None:
        """Return the canonical tool name for a possibly-misspelled input,
        or None if no match. Useful for logging/repair feedback."""
        tool = self.get(name)
        return tool.name if tool else None

    def filter_by_names(self, names: set[str], exclude: bool = False) -> list[dict]:
        if exclude:
            return [t.to_llm() for t in self._tools.values() if t.name not in names]
        return [t.to_llm() for t in self._tools.values() if t.name in names]

    def filter_by_permission(self, allowed: set[str] | None = None, denied: set[str] | None = None) -> list[dict]:
        result = []
        for t in self._tools.values():
            if denied and t.name in denied:
                continue
            if allowed and t.name not in allowed:
                continue
            result.append(t.to_llm())
        return result


registry = ToolRegistry()

# Tool-set constants and behavioural metadata are now defined in tool_meta.py
# and imported above. Re-export them for backward compatibility.


# Apply TOOL_META to registered tools
# ──────────────────────────────────────────────────────────────────────────
def _apply_tool_meta() -> None:
    for _name, _meta in TOOL_META.items():
        _t = registry._tools.get(_name)
        if _t is None:
            logger.warning("TOOL_META references unknown tool: %s", _name)
            continue
        for _k, _v in _meta.items():
            setattr(_t, _k, _v)


def tools_with(flag: str) -> set[str]:
    """Return the set of tool names that have ``flag`` set True. Convenience for
    code paths that still want a set (e.g. logging)."""
    return {t.name for t in registry._tools.values() if getattr(t, flag, False)}


# ──────────────────────────────────────────────────────────────────────────
# Dynamic tool-documentation builder
# ──────────────────────────────────────────────────────────────────────────


def build_tool_docs(tool_names: set[str] | None = None) -> str:
    """Return a markdown section documenting one or more tools.

    When *tool_names* is ``None`` (default), all registered tools are included.
    Each tool's ``to_doc()`` output is appended, grouped by category when
    ``tool_meta.TOOL_CATEGORIES`` is available.
    """
    if tool_names is None:
        tools = list(registry._tools.values())
    else:
        tools = [t for t in registry._tools.values() if t.name in tool_names]
    tools.sort(key=lambda t: t.name)

    lines: list[str] = []
    for tool in tools:
        doc = tool.to_doc().strip()
        if doc:
            lines.append(doc)
    return "\n\n".join(lines)


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
]
