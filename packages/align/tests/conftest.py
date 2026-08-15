"""packages/align/tests 共享 fixture（S150：REPAIR-LIST C 类——消除 ToolContext 复制粘贴）。

与 packages/app/tests/conftest.py 的 make_toolkit 同构（最小装配 factory）；
align 包测试独立使用，不跨包引用 app 测试。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from anyspark.core import ToolRegistry
from anyspark.server.toolkit import ToolContext, build_toolkit
from anyspark.server.tools_extensions import ExtensionToolStore


@pytest.fixture
def make_toolkit() -> Any:
    """最小装配 factory：make_toolkit(**overrides) → registry（默认全 None 依赖）。"""

    def _make(**overrides: Any) -> ToolRegistry:
        base: dict[str, Any] = dict(
            chapters=None,
            workspace=None,
            model=None,
            graph=None,
            plots=None,
            plans=None,
            settings=None,
            materials=None,
            ext_tools=ExtensionToolStore(Path(tempfile.mkdtemp()) / "ext.db"),
            book_id="main",
        )
        base.update(overrides)
        return build_toolkit(ToolRegistry(), ToolContext(**base))

    return _make
