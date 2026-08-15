"""packages/app/tests 共享 fixture（S150：REPAIR-LIST C 类——消除 ToolContext 复制粘贴）。

此前每个测试文件复制 ~25 行 build_toolkit(ToolRegistry(), ToolContext(...))；
新增依赖字段时所有测试手动同步（S105 漏传过 book_id）。集中为 factory fixture：

    def test_x(make_toolkit, make_full_toolkit):
        reg = make_toolkit()                      # 最小装配（None 依赖）
        reg = make_toolkit(skills_store=store)    # 覆盖特定 store
        reg = make_full_toolkit(deps)             # 完整装配（对齐 agent_factory）
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


@pytest.fixture
def make_full_toolkit() -> Any:
    """完整装配 factory：make_full_toolkit(deps, **overrides) → registry（对齐 agent_factory）。"""

    def _make(deps: Any, **overrides: Any) -> ToolRegistry:
        ctx: dict[str, Any] = dict(
            chapters=deps.chapters,
            workspace=deps.workspace,
            model=deps.model,
            graph=deps.graph,
            plots=deps.plots,
            plans=deps.plans,
            settings=deps.settings,
            materials=deps.materials,
            ext_tools=deps.ext_tools,
            dim_store=deps.dim_store,
            manual=deps.manual,
            skills_store=deps.skills,
            style_prefs=None,
            workflow_store=deps.workflow_store,
            workflow_engine=deps.workflow_engine,
            workflow_generator=deps.workflow_generator,
            play_engine=deps.play_engine,
            review_panel=deps.review_panel,
            skill_generator=deps.skill_generator,
            signals=deps.signals,
            book_id="main",
            subagent_deps=deps,
            templates=[],
        )
        ctx.update(overrides)
        return build_toolkit(ToolRegistry(), ToolContext(**ctx))

    return _make
