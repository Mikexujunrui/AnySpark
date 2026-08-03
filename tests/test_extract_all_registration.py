# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Regression test: extract_all_chapters must be fully wired.

User report: "extract_all_chapters 未注册（批量提取工具在当前环境不可用）",
740-chapter full extraction fell back to per-chapter extraction. Root cause:
the handler existed but was never imported/registered in the executor dispatch
tables. This test pins all three registration layers so a re-regression fails CI.
"""

import core.tool_defs  # noqa: F401  (importing the package registers all tools)
from core.tool_registry import registry
from tools.executor import _DISPATCH, _STREAMING_DISPATCH, _build_dispatch, _register_streaming


def test_tool_definition_registered():
    tool = registry.get("extract_all_chapters")
    assert tool is not None, "extract_all_chapters 应在 tool registry 中注册"
    assert tool.parameters is not None, "extract_all_chapters 应有参数定义"
    assert tool.description, "extract_all_chapters 应有描述"


def test_executor_dispatch_registered():
    _build_dispatch()
    assert _DISPATCH.get("extract_all_chapters") is not None, "extract_all_chapters 应注册到 executor dispatch"


def test_executor_streaming_registered():
    _register_streaming()
    assert (
        _STREAMING_DISPATCH.get("extract_all_chapters") is not None
    ), "extract_all_chapters 应注册到 streaming dispatch（带进度）"


def test_tool_meta_flagged_streaming():
    from core.tool_meta import TOOL_META

    meta = TOOL_META.get("extract_all_chapters")
    assert meta is not None, "extract_all_chapters 应有 TOOL_META 条目"
    assert meta.get("streaming") is True, "extract_all_chapters 应标记 streaming=True"
    assert meta.get("mutates_kb") is True, "extract_all_chapters 应标记 mutates_kb=True"


def test_handler_signature_matches_streaming_protocol():
    """The handler must accept (loop, args, kb, book_id, msg, queue) so the
    streaming dispatch can pass a progress queue."""
    import inspect

    from tools.impl.knowledge import _extract_all_chapters

    sig = inspect.signature(_extract_all_chapters)
    params = list(sig.parameters)
    for expected in ("loop", "args", "kb", "book_id", "queue"):
        assert expected in params, f"handler 缺少参数 {expected}: {params}"
