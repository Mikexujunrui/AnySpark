"""anyspark.core.loop 测试 — 验证最小循环走通（读提示→调工具→回填→输出）。"""

from __future__ import annotations

from anyspark.core import Agent, Message, Model, ToolRegistry, register_builtins


class ScriptedModel:
    """脚本化模型：按脚本依次输出文本，先调工具再给最终答案。"""

    def __init__(self, script: list[str]) -> None:
        self._script = list(script)
        self.answered_prompts: list[list[Message]] = []

    def respond(self, messages: list[Message], tool_descriptions: str) -> str:
        self.answered_prompts.append(list(messages))
        return self._script.pop(0)


def _make_agent(model: Model) -> Agent:
    registry = ToolRegistry()
    register_builtins(registry)
    return Agent(model=model, registry=registry)


def test_loop_runs_without_tools() -> None:
    agent = _make_agent(ScriptedModel(["直接给出的答案"]))
    turn = agent.run("问题")
    assert turn.text == "直接给出的答案"
    assert turn.tool_calls == []
    # 会话落盘：user + assistant（system 指令在模型 prompt 内联，不重复落盘）
    msgs = agent.store.messages(agent.store.list_conversations()[0].id)
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant"]


def test_one_tool_then_final_output() -> None:
    # 第一次输出调工具，第二次输出最终答案
    agent = _make_agent(ScriptedModel(["`add(a=1, b=2)`", "结果是 3"]))
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

    agent = _make_agent(ScriptedModel(["答案"]))
    agent.events.on("done", lambda e: events.append(e.type if isinstance(e, Event) else str(e)))
    agent.run("问题")
    assert "done" in events


def test_max_iterations_guard() -> None:
    # 模型永远调工具，应触发生成上限终止
    agent = _make_agent(ScriptedModel(["`add(a=1, b=2)`"] * 100))
    agent.max_tool_iterations = 3
    turn = agent.run("无限循环测试")
    assert "达到最大工具迭代次数" in turn.text
