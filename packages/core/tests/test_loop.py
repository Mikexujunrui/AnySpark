"""anyspark.core.loop 测试 — 验证最小循环走通（读提示→调工具→回填→输出）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anyspark.core import (
    Agent,
    Message,
    Model,
    ModelOutput,
    ToolRegistry,
    ToolResult,
    ToolSpec,
)
from anyspark.core.events import Event
from anyspark.core.tools import register_builtins


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


def test_loop_default_no_hard_limit_but_repeat_detection() -> None:
    """S108：默认无硬上限（对齐 pi）；同参数重复调用被智能停止拦截（非硬限）。"""
    from anyspark.core import ToolCall

    # 同参数反复调用（真死循环模式）——重复检测应在 ~6 轮拦截
    same = ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})])
    agent = _make_agent(ScriptedModel([same] * 100))
    assert agent.max_tool_iterations is None  # 默认无硬上限
    turn = agent.run("死循环测试")
    assert "重复的工具调用" in turn.text
    assert turn.error is not None

    # 递进式任务（参数变化）不受限——20 轮后正常终答
    from anyspark.core import ToolCall

    outputs: list[ModelOutput] = [
        ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": i, "b": i})])
        for i in range(20)
    ]
    outputs.append(_no_tool("完成"))
    agent2 = _make_agent(ScriptedModel(outputs))
    turn2 = agent2.run("递进任务")
    assert turn2.error is None
    assert turn2.text == "完成"
    assert len(agent2._call_signatures) == 20  # 20 轮都记录了但未触发重复检测


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


def test_steer_injects_between_turns() -> None:
    """S25 steering：运行中插话——消息在当前轮工具结果后、下一轮 LLM 前注入。"""
    from anyspark.core import ToolCall

    model = ScriptedModel(
        [
            ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2})]),
            _no_tool("收到插话后的回答"),
        ]
    )
    agent = _make_agent(model)
    agent.store.create("s1")
    # 启动循环前预置插话（模拟 API 层在 agent 运行中途入队）
    agent.steer("别写太血腥")
    turn = agent.run("写一章", "s1")
    assert turn.text == "收到插话后的回答"
    # 注入时机与 pi 一致：每轮 LLM 前检查 steering 队列——插话先于本轮模型调用生效
    roles = [m.role for m in agent.store.messages("s1")]
    assert roles == ["user", "user", "assistant", "tool", "assistant"]
    assert "别写太血腥" in agent.store.messages("s1")[1].content


def test_followup_runs_after_stop() -> None:
    """S25 followUp：agent 即将停止（无工具调用）时注入追问续跑，而不是结束。"""
    model = ScriptedModel(
        [
            _no_tool("第一段回答"),
            _no_tool("追问后的回答"),
        ]
    )
    agent = _make_agent(model)
    agent.store.create("s2")
    agent.follow_up("继续说说细节")
    turn = agent.run("问个问题", "s2")
    assert turn.text == "追问后的回答"
    roles = [m.role for m in agent.store.messages("s2")]
    # user → assistant(第一段) → user(追问) → assistant(追问后)
    assert roles == ["user", "assistant", "user", "assistant"]
    assert "继续说说细节" in agent.store.messages("s2")[2].content


def test_sequential_tool_runs_serially() -> None:
    """S25 sequential 模式：批内含 sequential 工具时整批串行执行（保逻辑顺序）。"""
    from anyspark.core import ToolCall

    order: list[str] = []

    def do_read(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        order.append("read")
        return ToolResult(call=ToolCall(name="slow_read", arguments={}), ok=True, content="读完了")

    def do_write(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        order.append("write")
        return ToolResult(
            call=ToolCall(name="critical_write", arguments={}), ok=True, content="写完了"
        )

    registry = ToolRegistry()
    registry.register(ToolSpec(name="slow_read", params=[]), do_read)
    registry.register(
        ToolSpec(name="critical_write", params=[], execution_mode="sequential"), do_write
    )
    model = ScriptedModel(
        [
            ModelOutput(
                tool_calls=[
                    ToolCall(name="slow_read", arguments={}, id="c1"),
                    ToolCall(name="critical_write", arguments={}, id="c2"),
                ]
            ),
            _no_tool("完成"),
        ]
    )
    agent = Agent(model=model, registry=registry)
    turn = agent.run("测试")
    assert turn.text == "完成"
    assert order == ["read", "write"]  # 串行保序


def test_tool_execution_events_emitted() -> None:
    """S25 工具执行事件：执行前 tool_execution_start、执行后 tool_execution_end（带 ok/耗时）。"""
    from anyspark.core import ToolCall

    events: list[str] = []
    agent = _make_agent(
        ScriptedModel(
            [
                ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id="c9")]),
                _no_tool("ok"),
            ]
        )
    )
    agent.events.on("tool_execution_start", lambda e: events.append(e.type))
    agent.events.on("tool_execution_end", lambda e: events.append(e.type))
    agent.run("算")
    assert events == ["tool_execution_start", "tool_execution_end"]


def test_before_tool_call_can_block() -> None:
    """S27 before_tool_call 钩子：返回拦截原因 → 工具不执行，回填错误。"""
    from anyspark.core import ToolCall

    executed = {"n": 0}

    def do_add(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        executed["n"] += 1
        return ToolResult(call=ToolCall(name="add", arguments=arguments), ok=True, content="算好了")

    registry = ToolRegistry()
    registry.register(ToolSpec(name="add", params=[]), do_add)
    model = ScriptedModel(
        [
            ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id="b1")]),
            _no_tool("拦截后继续"),
        ]
    )
    agent = Agent(model=model, registry=registry)
    agent.before_tool_call = lambda call: "危险操作" if call.name == "add" else None
    turn = agent.run("算")
    assert turn.text == "拦截后继续"
    assert executed["n"] == 0  # add 从未执行
    assert turn.tool_results[0].ok is False
    assert "被拦截" in turn.tool_results[0].content


def test_after_tool_call_rewrites_result() -> None:
    """S27 after_tool_call 钩子：可改写结果（安全统一/信号采集挂点）。"""
    from anyspark.core import ToolCall

    model = ScriptedModel(
        [
            ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id="a2")]),
            _no_tool("完成"),
        ]
    )
    agent = _make_agent(model)
    agent.after_tool_call = lambda call, result: ToolResult(
        call=result.call, ok=False, content="被钩子改写为失败", terminate=result.terminate
    )
    turn = agent.run("算")
    assert turn.text == "完成"
    assert turn.tool_results[0].ok is False
    assert "钩子改写" in turn.tool_results[0].content


def test_terminate_stops_loop() -> None:
    """S27 terminate：批内全部工具 terminate=True → 循环立即结束（不再死磕迭代上限）。"""
    from anyspark.core import ToolCall

    def do_done(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            call=ToolCall(name="finish", arguments={}),
            ok=True,
            content="任务完成",
            terminate=True,
        )

    registry = ToolRegistry()
    registry.register(ToolSpec(name="finish", params=[]), do_done)
    # 模型永远要调 finish——没有 terminate 会撞迭代上限；有 terminate 应提前结束
    model = ScriptedModel(
        [ModelOutput(tool_calls=[ToolCall(name="finish", arguments={}, id="t1")])] * 100
    )
    agent = Agent(model=model, registry=registry, max_tool_iterations=50)
    turn = agent.run("结束吧")
    assert "任务完成" in turn.text or "停止" in turn.text
    assert turn.error is None  # 不是迭代上限错误
    assert len(turn.tool_calls) == 1  # 只跑了一轮


def test_workflow_status_polling_not_deadloop() -> None:
    """S158c：workflow_status 轮询合法（等异步任务，幂等只读）——不触发 S108 死循环拦截。

    连续 N 轮只调 workflow_status（签名相同）不应被当作死循环终止；
    之后正常终答。
    """
    from anyspark.core import ToolCall

    polls = [
        ModelOutput(tool_calls=[ToolCall(name="workflow_status", arguments={"task_id": "task-x"})])
        for _ in range(15)
    ]
    polls.append(_no_tool("任务还在跑，我先结束，后台继续。"))
    agent = _make_agent(ScriptedModel(polls))
    turn = agent.run("查任务进度")
    assert turn.error is None
    assert "重复的工具调用" not in turn.text
    assert turn.text.startswith("任务还在跑")


def _dangling_decl_ids(msgs: list[Message]) -> set[str]:
    """提取悬挂声明：assistant 声明的 tool_call id 减去已配对 tool 的 id。"""
    decl: set[str] = set()
    for m in msgs:
        if m.role == "assistant" and m.metadata.get("tool_calls"):
            for tc in m.metadata["tool_calls"]:
                if isinstance(tc, dict) and tc.get("id"):
                    decl.add(str(tc["id"]))
        elif m.role == "tool":
            decl.discard(str(m.metadata.get("tool_call_id") or ""))
    return decl


def test_cancel_any_time_leaves_no_dangling_declaration() -> None:
    """S169：运行中取消（任意时机）不得留下无配对的 assistant 声明——
    声明已落 store 后取消（执行前窗口）会触发 OpenAI 协议 400
    （insufficient tool messages following tool_calls）；补 ToolResult 回填防悬挂。"""
    import threading
    import time

    from anyspark.core import CancellationToken, ToolCall

    for i in range(20):
        model = ScriptedModel(
            [
                ModelOutput(
                    tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id=f"call_{i}")]
                ),
                _no_tool("done"),
            ]
        )
        agent = _make_agent(model)
        token = CancellationToken()
        # 子线程随机延迟取消（模拟 API 层 cancel 端点，覆盖不同执行时机）
        delay = (i % 7) * 0.0005

        def _cancel_later(d: float, tk: CancellationToken) -> None:
            time.sleep(d)
            tk.cancel()

        threading.Thread(target=lambda d=delay, tk=token: _cancel_later(d, tk)).start()
        agent.run("问题", token=token)
        msgs = agent.store.messages(agent.store.list_conversations()[0].id)
        dangling = _dangling_decl_ids(msgs)
        assert not dangling, f"迭代{i} 存在悬挂声明: {dangling}"


def test_before_tool_call_hook_exception_keeps_pairs() -> None:
    """S169：before_tool_call 钩子抛异常不冒泡——冒泡会让已落 store 的
    assistant 声明悬挂无配对（400）；转拦截错误回填保持配对完整。"""

    from anyspark.core import ToolCall

    def bad_hook(call: ToolCall) -> str:
        raise RuntimeError("钩子炸了")

    model = ScriptedModel(
        [
            ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 1, "b": 2}, id="call_h")]),
            _no_tool("恢复"),
        ]
    )
    reg = ToolRegistry()
    register_builtins(reg)
    agent = Agent(model=model, registry=reg, before_tool_call=bad_hook)
    turn = agent.run("问题")
    assert turn.text == "恢复"  # 异常未冒泡，循环继续到终答
    msgs = agent.store.messages(agent.store.list_conversations()[0].id)
    assert not _dangling_decl_ids(msgs)
    # 配对序列完整：user → assistant(声明) → tool(拦截结果) → assistant(终答)
    assert [m.role for m in msgs] == ["user", "assistant", "tool", "assistant"]
    tool = next(m for m in msgs if m.role == "tool")
    assert tool.metadata.get("tool_call_id") == "call_h"
    assert "钩子异常" in tool.content
