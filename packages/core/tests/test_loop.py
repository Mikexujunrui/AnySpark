"""anyspark.core.loop 测试 — 验证最小循环走通（读提示→调工具→回填→输出）。"""

from __future__ import annotations

from collections.abc import Callable

from anyspark.core import (
    Agent,
    Message,
    Model,
    ModelOutput,
    ToolRegistry,
    ToolSpec,
    register_builtins,
)
from anyspark.core.events import Event


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


class StreamScriptedModel:
    """流式模型（S21 移植 pi 模式）：respond_stream 逐段发 text_delta 事件。"""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        return ModelOutput(text="".join(self._chunks))

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Event], None],
    ) -> ModelOutput:
        for c in self._chunks:
            on_event(Event(type="text_delta", payload={"content": c}))
        on_event(Event(type="done", payload={}))
        return ModelOutput(text="".join(self._chunks))


def test_loop_streams_text_delta_events() -> None:
    """S21 流式核心：模型实现 respond_stream 时，Agent 循环逐段 emit text_delta。"""
    from anyspark.core.events import Event

    deltas: list[str] = []
    model = StreamScriptedModel(["雾", "城", "侦探"])
    agent = _make_agent(model)
    agent.events.on(
        "text_delta",
        lambda e: deltas.append(e.payload["content"] if isinstance(e, Event) else str(e)),
    )
    turn = agent.run("问题")
    assert turn.text == "雾城侦探"
    assert deltas == ["雾", "城", "侦探"]


def test_loop_falls_back_to_respond_when_no_stream() -> None:
    """S21：模型无 respond_stream 时回退非流式 respond（向后兼容）。"""
    scripted = ScriptedModel([_no_tool("非流式答案")])
    turn = _make_agent(scripted).run("问题")
    assert turn.text == "非流式答案"


def test_loop_parallel_tools_preserve_order() -> None:
    """S21 工具并行：一次多个工具调用并行执行，结果按调用顺序回填。"""
    from anyspark.core import ToolCall

    # 第一轮：两个工具调用（add + echo）；第二轮：终答
    model = ScriptedModel(
        [
            ModelOutput(
                tool_calls=[
                    ToolCall(name="add", arguments={"a": 1, "b": 2}),
                    ToolCall(name="echo", arguments={"text": "并行执行"}),
                ]
            ),
            _no_tool("完成"),
        ]
    )
    turn = _make_agent(model).run("测试")
    assert turn.text == "完成"
    assert [c.name for c in turn.tool_calls] == ["add", "echo"]
    assert turn.tool_results[0].ok and turn.tool_results[1].ok
    # 回填顺序与调用顺序一致
    assert turn.tool_results[0].data == {"result": 3}


def test_loop_cancellation_token() -> None:
    """S21 协作式取消：token.cancel() 后 Agent 在检查点提前终止。"""
    from anyspark.core import CancellationToken, ToolCall

    # 模型永远要调工具（循环不会自然结束），token 取消应提前终止
    always_tool = ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})])
    model = ScriptedModel([always_tool] * 100)
    token = CancellationToken()
    agent = _make_agent(model)

    events: list[str] = []
    agent.events.on("aborted", lambda e: events.append("aborted"))

    # 预先取消 → 第一轮检查点即终止
    token.cancel()
    turn = agent.run("问题", token=token)
    assert "中断" in turn.text
    assert "aborted" in events


def test_cancellation_appends_assistant_message() -> None:
    """S22（D5）：取消终止时 append assistant 消息——上下文保持 user/assistant 配对，
    用户随后发"继续"不会出现 user 接 user 的失衡上下文（移植 pi 的 aborted 消息保留）。"""
    from anyspark.core import CancellationToken, ToolCall

    always_tool = ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})])
    token = CancellationToken()
    agent = _make_agent(ScriptedModel([always_tool] * 100))
    token.cancel()
    agent.run("问题", token=token)
    msgs = agent.store.messages(agent.store.list_conversations()[0].id)
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant"]  # 平衡：user 后有 assistant（已中断）
    assert "中断" in msgs[-1].content


def test_model_failure_keeps_context_balanced() -> None:
    """S22（D1）：模型调用抛异常（重试耗尽）→ 不冒泡不毒化上下文——
    append assistant 失败消息保持配对，Turn.error 带错误说明。"""

    class _ExplodingModel:
        def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
            raise ConnectionError("上游断连")

    agent = _make_agent(_ExplodingModel())
    turn = agent.run("问题")
    assert turn.error is not None
    assert "生成失败" in turn.text
    # 上下文平衡：user, assistant(生成失败)
    msgs = agent.store.messages(agent.store.list_conversations()[0].id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert "生成失败" in msgs[-1].content
    # 用户再发一条 → user, assistant(失败), user 正常续聊
    conv_id = agent.store.list_conversations()[0].id
    agent.run("继续", conv_id)
    roles = [m.role for m in agent.store.messages(agent.store.list_conversations()[0].id)]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_truncated_tool_calls_rejected() -> None:
    """S22（D3）：输出被 token 上限截断（truncated）→ 整批工具调用**不执行**，
    回填"被截断请重发"错误，循环继续（模型下一轮重发完整调用）。
    仅靠 _malformed 不够：截断可能产生 JSON 合法但语义残缺的参数。"""
    from anyspark.core import ToolCall

    # 第一轮：truncated + 工具调用（应被拒绝，不执行 add）；第二轮：终答
    model = ScriptedModel(
        [
            ModelOutput(
                truncated=True,
                tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})],
            ),
            _no_tool("最终回答"),
        ]
    )
    agent = _make_agent(model)
    turn = agent.run("测试")
    assert turn.text == "最终回答"
    # 被拒绝的调用进入了 turn 记录（回填了错误）但 add 实际未执行
    assert len(turn.tool_calls) == 1
    assert turn.tool_results[0].ok is False
    assert "截断" in turn.tool_results[0].content
    # 模型第二次调用时拿到了错误回填（tool 消息）
    tool_msgs = [
        m for m in agent.store.messages(agent.store.list_conversations()[0].id) if m.role == "tool"
    ]
    assert len(tool_msgs) == 1
    assert "截断" in tool_msgs[0].content


def test_tool_calls_paired_with_ids() -> None:
    """S23 协议完整化：工具调用声明与结果**配对落 store**——
    assistant 消息带原生 tool_calls 声明（metadata），tool 消息带 tool_call_id。
    上下文序列为 user → assistant(声明) → tool(配对) → assistant(终答)，
    不再是 user → tool 的畸形序列。"""
    from anyspark.core import ToolCall

    model = ScriptedModel(
        [
            ModelOutput(
                tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id="call_abc123")]
            ),
            _no_tool("结果是 3"),
        ]
    )
    agent = _make_agent(model)
    agent.store.create("c2")
    turn = agent.run("算一下", "c2")
    assert turn.text == "结果是 3"

    msgs = agent.store.messages("c2")
    roles = [m.role for m in msgs]
    # 合法配对序列：user → assistant(tool_calls 声明) → tool(配对) → assistant(终答)
    assert roles == ["user", "assistant", "tool", "assistant"]
    # assistant 声明带原生 tool_calls
    decl = msgs[1].metadata.get("tool_calls")
    assert decl == [{"name": "add", "arguments": {"a": 1, "b": 2}, "id": "call_abc123"}]
    # tool 结果带配对 id
    assert msgs[2].metadata.get("tool_call_id") == "call_abc123"


def test_tool_result_backfill_preserved() -> None:
    """S23 兼容性：工具结果回填文本保留（模型可读），配对信息仅存 metadata——
    不带 id 的旧链路（DashScope 宽容模式）行为不变。"""
    from anyspark.core import ToolCall

    model = ScriptedModel(
        [
            ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 5, "b": 7})]),
            _no_tool("结果是 12"),
        ]
    )
    agent = _make_agent(model)
    agent.store.create("c3")
    turn = agent.run("算", "c3")
    assert turn.text == "结果是 12"
    msgs = agent.store.messages("c3")
    tool_msg = next(m for m in msgs if m.role == "tool")
    assert "5 + 7 = 12" in tool_msg.content  # 文本回填仍在
    assert tool_msg.metadata.get("tool_call_id") is None  # 无 id 则不配对（旧行为）
