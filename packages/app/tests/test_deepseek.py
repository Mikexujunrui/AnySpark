"""anyspark.models.deepseek 的纯函数映射测试（不访问网络）。"""

from anyspark.core.protocol import ParamSpec, ToolSpec
from anyspark.core.types import Message
from anyspark.models.deepseek import (
    to_openai_message,
    to_openai_tool,
)


def test_to_openai_message() -> None:
    m = Message(role="user", content="你好")
    assert to_openai_message(m) == {"role": "user", "content": "你好"}


def test_to_openai_message_assistant_reasoning() -> None:
    """思考模式：assistant 消息带 metadata.reasoning → reasoning_content 回传。"""
    m = Message(
        role="assistant",
        content="答案是42",
        metadata={"reasoning": "让我想想...6×7=42"},
    )
    result = to_openai_message(m)
    assert result["role"] == "assistant"
    assert result["content"] == "答案是42"
    assert result["reasoning_content"] == "让我想想...6×7=42"


def test_to_openai_message_assistant_no_reasoning() -> None:
    """无 reasoning 时不带 reasoning_content 字段。"""
    m = Message(role="assistant", content="你好")
    result = to_openai_message(m)
    assert "reasoning_content" not in result


def test_to_openai_tool_with_params() -> None:
    spec = ToolSpec(
        name="add",
        description="计算两个整数相加的和",
        params=[
            ParamSpec(name="a", type="integer", required=True, description="第一个加数"),
            ParamSpec(name="b", type="integer", required=False, description="可选"),
        ],
    )
    tool = to_openai_tool(spec)
    assert tool["type"] == "function"
    fn = tool["function"]
    assert fn["name"] == "add"
    assert fn["parameters"]["required"] == ["a"]
    assert fn["parameters"]["properties"]["a"]["type"] == "integer"


def test_to_openai_tool_no_params() -> None:
    spec = ToolSpec(name="list_books", description="列书")
    tool = to_openai_tool(spec)
    assert tool["function"]["parameters"]["required"] == []
