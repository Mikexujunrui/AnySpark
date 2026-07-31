"""Tool definition data, split by domain from the former monolithic
``core/tools.py``. Importing this package registers every tool into the
shared :data:`core.tool_registry.registry` in a stable order.
The order below mirrors the original file (first appearance per domain).
"""

from __future__ import annotations

from . import (
    agent,  # noqa: F401
    chapters,  # noqa: F401
    knowledge,  # noqa: F401
    planning,  # noqa: F401
    reference,  # noqa: F401
    style,  # noqa: F401
    transform,  # noqa: F401
    volume,  # noqa: F401
    workflow,  # noqa: F401
)

__all__ = [
    "knowledge",
    "chapters",
    "agent",
    "planning",
    "transform",
    "volume",
    "workflow",
    "style",
    "reference",
]
