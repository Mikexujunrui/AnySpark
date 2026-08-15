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
