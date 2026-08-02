"""anyspark.core.protocol 测试（工具规格/校验/注册/执行）。"""

from anyspark.core.protocol import (
    ParamSpec,
    ToolRegistry,
    ToolSpec,
    execute,
)


# ---- ToolSpec.validate ----
def test_validate_missing_required() -> None:
    spec = ToolSpec(
        name="add",
        params=[
            ParamSpec(name="a", type="integer", required=True),
            ParamSpec(name="b", type="integer", required=True),
        ],
    )
    errs = spec.validate({"a": 1})
    assert any("b" in e for e in errs)


def test_validate_wrong_type() -> None:
    spec = ToolSpec(
        name="add",
        params=[ParamSpec(name="a", type="integer", required=True)],
    )
    errs = spec.validate({"a": "x"})
    assert len(errs) == 1


def test_validate_ok() -> None:
    spec = ToolSpec(
        name="add",
        params=[ParamSpec(name="a", type="integer", required=True)],
    )
    assert spec.validate({"a": 5}) == []


# ---- ToolRegistry + execute ----
def _make_registry() -> ToolRegistry:
    from anyspark.core.tools import (
        add_implementer,
        builtin_add_spec,
        builtin_echo_spec,
        echo_implementer,
    )

    reg = ToolRegistry()
    reg.register(builtin_echo_spec(), echo_implementer)
    reg.register(builtin_add_spec(), add_implementer)
    return reg


def test_execute_unknown_tool_fails() -> None:
    reg = ToolRegistry()
    from anyspark.core.types import ToolCall

    result = execute(reg, ToolCall(name="nope", arguments={}))
    assert result.ok is False
    assert "未知工具" in result.content


def test_execute_builtin_add() -> None:
    reg = _make_registry()
    from anyspark.core.types import ToolCall

    result = execute(reg, ToolCall(name="add", arguments={"a": 3, "b": 4}))
    assert result.ok is True
    assert result.data is not None
    assert result.data["result"] == 7


def test_execute_builtin_returns_natural_language() -> None:
    reg = _make_registry()
    from anyspark.core.protocol import backfill_content_tool_result
    from anyspark.core.types import ToolCall

    result = execute(reg, ToolCall(name="echo", arguments={"text": "hi"}))
    backfill = backfill_content_tool_result(result)
    assert backfill == "[工具 echo 成功] hi"
