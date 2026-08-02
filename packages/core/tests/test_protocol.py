"""anyspark.core.protocol 测试（工具调用协议的解析/校验/执行）。"""

from anyspark.core.protocol import (
    ParamSpec,
    ToolRegistry,
    ToolSpec,
    execute,
    parse_tool_calls,
)


# ---- parse_tool_calls ----
def test_parse_named_args() -> None:
    calls = parse_tool_calls("请计算 `add(a=1, b=2)` 的结果。")
    assert len(calls) == 1
    assert calls[0].name == "add"
    assert calls[0].arguments == {"a": 1, "b": 2}


def test_parse_string_values_with_quotes() -> None:
    calls = parse_tool_calls('`echo(text="你好世界")`')
    assert len(calls) == 1
    assert calls[0].arguments == {"text": "你好世界"}


def test_parse_no_calls_returns_empty() -> None:
    assert parse_tool_calls("没有任何工具调用") == []


def test_parse_multiple_calls() -> None:
    calls = parse_tool_calls("先 `add(a=1, b=2)` 再 `add(a=10, b=20)`")
    assert len(calls) == 2
    assert calls[1].arguments["a"] == 10


def test_parse_commas_inside_quotes_not_split() -> None:
    calls = parse_tool_calls('`echo(text="a, b, c")`')
    assert calls[0].arguments["text"] == "a, b, c"


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
