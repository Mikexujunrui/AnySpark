"""anyspark.core.loop 测试 — 验证最小循环走通（读提示→调工具→回填→输出）。"""

from __future__ import annotations

from anyspark.core import (
    Agent,
    Message,
    Model,
    ModelOutput,
    ToolRegistry,
    ToolSpec,
    register_builtins,
)


class ScriptedModel:
    """脚本化模型：按脚本依次返回 ModelOutput（先工具后终答）。"""

    def __init__(self, outputs: list[ModelOutput]) -> None:
        self._script = list(outputs)
        self.answered_prompts: list[list[Message]] = []

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        self.answered_prompts.append(list(messages))
        return self._script.pop(0)


def _no_tool(text: str) -> ModelOutput:
    return ModelOutput(text=text)


def _make_agent(model: Model) -> Agent:
    registry = ToolRegistry()
    register_builtins(registry)
    return Agent(model=model, registry=registry)


def test_loop_runs_without_tools() -> None:
    agent = _make_agent(ScriptedModel([_no_tool("直接给出的答案")]))
    turn = agent.run("问题")
    assert turn.text == "直接给出的答案"
    assert turn.tool_calls == []
    # 会话落盘：user + assistant（system 指令是否内联由适配器决定，此处未提供 system_prompt）
    msgs = agent.store.messages(agent.store.list_conversations()[0].id)
    assert [m.role for m in msgs] == ["user", "assistant"]


def test_context_compressor_is_applied() -> None:
    """S8：token 预算压缩回调（app 注入）在每轮模型调用前生效。"""
    calls: list[list[Message]] = []

    def compressor(messages: list[Message]) -> list[Message]:
        calls.append(list(messages))
        # 模拟压缩：只保留 system + 最后一条
        return messages[:1] + messages[-1:]

    model = ScriptedModel([_no_tool("压缩后回答")])
    agent = Agent(
        model=model,
        registry=ToolRegistry(),
        system_prompt="系统指令",
        context_compressor=compressor,
    )
    turn = agent.run("长对话问题")
    assert turn.text == "压缩后回答"
    assert len(calls) == 1
    assert calls[0][0].role == "system"  # 压缩器拿到完整 prompt（含 system）
    # 模型实际收到的消息是压缩后的（system + 最后一条）
    assert len(model.answered_prompts[0]) == 2


def test_one_tool_then_final_output() -> None:
    from anyspark.core import ToolCall

    agent = _make_agent(
        ScriptedModel(
            [
                ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})]),
                _no_tool("结果是 3"),
            ]
        )
    )
    agent.store.create("c1")
    turn = agent.run("帮我算一下", "c1")

    assert turn.tool_calls[0].name == "add"
    assert turn.text == "结果是 3"
    # 工具结果已回填进上下文（role=tool 的消息存在）
    roles = [m.role for m in agent.store.messages("c1")]
    assert "tool" in roles
    # 工具结果自然语言回填
    tool_msgs = [m for m in agent.store.messages("c1") if m.role == "tool"]
    assert "1 + 2 = 3" in tool_msgs[0].content


def test_loop_emits_done_event() -> None:
    events: list[str] = []
    from anyspark.core import Event

    agent = _make_agent(ScriptedModel([_no_tool("答案")]))
    agent.events.on("done", lambda e: events.append(e.type if isinstance(e, Event) else str(e)))
    agent.run("问题")
    assert "done" in events


def test_max_iterations_guard() -> None:
    from anyspark.core import ToolCall

    # 模型永远调工具，应触发生成上限终止
    always_tool = ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})])
    agent = _make_agent(ScriptedModel([always_tool] * 100))
    agent.max_tool_iterations = 3
    turn = agent.run("无限循环测试")
    assert "达到最大工具迭代次数" in turn.text


def test_system_prompt_prepended_when_set() -> None:
    scripted = ScriptedModel([_no_tool("ok")])
    agent = _make_agent(scripted)
    agent.system_prompt = "你是演示助手。"
    agent.run("问题")
    prompts = scripted.answered_prompts
    assert prompts[0][0].role == "system"
    assert "演示助手" in prompts[0][0].content
