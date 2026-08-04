"""anyspark.server.context — token 预算两阶段压缩测试（S24 对齐 pi compaction 语义）。"""

from __future__ import annotations

from anyspark.core.types import Message
from anyspark.server.context import TokenBudget, make_summarizer


def _msgs(n: int, per: str = "消息内容 ") -> list[Message]:
    return [Message(role="user" if i % 2 == 0 else "assistant", content=per * 10) for i in range(n)]


def test_count_approximates_tokens() -> None:
    b = TokenBudget(budget=1000)
    assert b.count("") == 0
    assert b.count("hello world") > 0
    assert b.count("你好") > 0


def test_no_compress_under_budget() -> None:
    b = TokenBudget(budget=100000)
    msgs = [Message(role="system", content="S"), *_msgs(10, "短")]
    out = b.compress(msgs)
    assert out == msgs  # 未超预算原样返回


def test_prune_without_summarizer() -> None:
    """超预算且无摘要器：纯 prune，保留 system + 最近消息。"""
    b = TokenBudget(budget=100)  # 极小预算触发压缩
    msgs = [Message(role="system", content="系统指令" * 20), *_msgs(30, "长消息")]
    out = b.compress(msgs)
    assert out[0].role == "system"  # system 保留
    assert len(out) < len(msgs)  # 有压缩
    assert b.count_messages(out) <= b.count_messages(msgs)  # 不增反减
    assert out[-1].content == msgs[-1].content  # 最近消息保留


def test_summarize_with_llm() -> None:
    """有摘要器：旧历史压成一条历史摘要（系统消息），最近消息保留。"""
    captured: list[list[Message]] = []
    prevs: list[str | None] = []

    def fake_summarize(history: list[Message], previous: str | None) -> str:
        captured.append(history)
        prevs.append(previous)
        return "摘要：早期对话已压缩。"

    b = TokenBudget(budget=100, summarize=fake_summarize)
    msgs = [Message(role="system", content="系统指令" * 20), *_msgs(30, "长消息")]
    out = b.compress(msgs)
    # 摘要器被调用（拿到了可压缩段）
    assert captured and len(captured[0]) < len(msgs)
    assert prevs[0] is None  # 首次摘要无 previous
    # 输出含历史摘要系统消息
    assert any("历史对话摘要" in m.content for m in out)
    # 最近消息保留
    assert out[-1].content == msgs[-1].content
    assert b.count_messages(out) < b.count_messages(msgs)


def test_summarize_failure_falls_back_to_prune() -> None:
    """摘要器抛异常：降级纯 prune，不中断。"""

    def broken(history: list[Message], previous: str | None) -> str:
        raise RuntimeError("LLM 挂了")

    b = TokenBudget(budget=100, summarize=broken)
    msgs = [Message(role="system", content="系统指令" * 20), *_msgs(30, "长消息")]
    out = b.compress(msgs)
    assert out[0].role == "system"
    assert len(out) < len(msgs)


def test_make_summarizer_uses_model() -> None:
    """make_summarizer 包装真实模型调用（fake 模型）。"""

    class FakeModel:
        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="压缩摘要：写了第一章雨夜。")

    s = make_summarizer(FakeModel())
    assert s is not None
    out = s([Message(role="user", content="x")], None)
    assert "雨夜" in out


def test_make_summarizer_incremental_prompt() -> None:
    """S24（B2）：有 previous 时走 UPDATE 模式（增量合并，不是从零重写）。"""
    prompts: list[list[Message]] = []

    class FakeModel:
        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            prompts.append(list(messages))
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="更新摘要")

    s = make_summarizer(FakeModel())
    s([Message(role="user", content="新进展")], "上次摘要：写了第一章")
    assert "上次摘要" in prompts[0][0].content
    assert "previous-summary" in prompts[0][0].content  # UPDATE 模式标记


def test_compress_keeps_read_note() -> None:
    """S21 修失忆-重读循环：prune 后保留已读章节清单，模型不盲目重读。"""
    from anyspark.core.types import Message

    b = TokenBudget(budget=300)  # 小预算强制触发压缩
    messages: list[Message] = [
        Message(role="system", content="你是写作助手。"),
        Message(role="user", content="开始"),
        Message(role="tool", content="《第一章》全文如下：\n" + "雨夜" * 80),
        Message(role="assistant", content="我读了第一章" + "续" * 50),
        Message(role="tool", content="《第二章》全文如下：\n" + "码头" * 80),
        Message(role="assistant", content="我读了第二章" + "续" * 50),
        Message(role="user", content="继续写" + "续" * 60),
        Message(role="assistant", content="好的" + "续" * 60),
        Message(role="user", content="再继续" + "续" * 60),
        Message(role="assistant", content="明白" + "续" * 60),
        Message(role="user", content="继续第三章" + "续" * 60),
    ]
    kept = b.compress(messages)
    combined = "\n".join(m.content for m in kept)
    # 已读清单保留（模型知道读过第一章/第二章）
    assert "已读章节清单" in combined
    assert "第一章" in combined and "第二章" in combined
    # 可压缩段（含超长工具结果）被裁掉：消息数显著减少 + 无"全文如下"
    assert len(kept) < len(messages)
    assert "全文如下" not in combined


def test_read_note_empty_when_no_reads() -> None:
    """无已读记录时不生成清单（不污染提示）。"""
    from anyspark.core.types import Message

    b = TokenBudget(budget=100)
    messages = [
        Message(role="system", content="s"),
        Message(role="user", content="u" * 80),
        Message(role="assistant", content="a" * 80),
    ]
    kept = b.compress(messages)
    assert "已读章节清单" not in "\n".join(m.content for m in kept)


def test_compress_cache_hits_same_context() -> None:
    """S21 修续聊卡住：同上下文二次压缩命中指纹缓存（不重复 LLM 摘要）。"""
    calls: list[int] = []

    def fake_summarize(msgs: list[Message], previous: str | None) -> str:
        calls.append(len(msgs))
        return "摘要内容" + "续" * 100

    from anyspark.core.types import Message

    b = TokenBudget(budget=200, summarize=fake_summarize)
    messages = [
        Message(role="system", content="s"),
        Message(role="user", content="u" * 80),
        Message(role="assistant", content="a" * 80),
        Message(role="tool", content="《第一章》全文如下：\n" + "x" * 100),
        Message(role="user", content="继续" + "续" * 80),
        Message(role="assistant", content="好" + "续" * 80),
        Message(role="user", content="再继续" + "续" * 80),
        Message(role="assistant", content="明白" + "续" * 80),
    ]
    r1 = b.compress(messages)
    r2 = b.compress(messages)  # 同上下文
    assert len(calls) == 1  # 摘要只跑一次
    assert r1 == r2


def test_cut_never_lands_on_tool_result() -> None:
    """S24（B1）：切割点**永不落在 tool 结果上**——保留段第一条不能是孤立 tool
    （其 assistant 声明已在可压缩段内被切掉，会造成畸形上下文）。"""
    b = TokenBudget(budget=800)  # 触发压缩且保留段保底恰好撞上 tool 消息
    # 12 条：index 7 assistant(声明) / 8 tool(结果) —— 保底 4 条时保留段 [8:] 第一条是 tool
    messages = [Message(role="system", content="s")]
    for i in range(1, 12):
        if i == 3 or i == 8:
            messages.append(Message(role="tool", content="《第X章》全文如下：\n" + "x" * 100))
        elif i % 2 == 0:
            messages.append(Message(role="assistant", content="a" * 100))
        else:
            messages.append(Message(role="user", content="u" * 100))
    kept = b.compress(messages)
    # 压缩后的保留段（摘要消息之后）第一条绝不能是 tool——孤立 tool 结果不允许残留
    tail = kept[1:] if kept and kept[0].role == "system" else kept
    if tail:
        assert tail[0].role != "tool"


def test_rough_count_skips_tiktoken_when_small() -> None:
    """S24（E1）：远低于预算时字符粗算直接返回，不调用 tiktoken 精算（省每轮全量编码）。"""
    b = TokenBudget(budget=100000)
    msgs = [Message(role="system", content="S"), *_msgs(10, "短")]
    # 粗算路径（budget 巨大，粗算即返回）——不会走到 count_messages
    out = b.compress(msgs)
    assert out == msgs
    # 直接验证：粗算判定成立（不需要 tiktoken）
    assert b._rough_count(msgs) <= int(100000 / 1.2 * 0.9)


def test_incremental_summary_uses_previous() -> None:
    """S24（B2）：第二次压缩时识别到上一次摘要（【历史对话摘要】消息）→ previous 非空。"""
    prevs: list[str | None] = []

    def fake_summarize(msgs: list[Message], previous: str | None) -> str:
        prevs.append(previous)
        return "摘要更新" + "续" * 50

    b = TokenBudget(budget=300, summarize=fake_summarize)
    messages = [
        Message(role="system", content="s"),
        # 上一次压缩产物（模拟）
        Message(role="system", content="【历史对话摘要】（压缩自 5 条消息，省 token）\n上次摘要"),
        Message(role="user", content="u" * 150),
        Message(role="assistant", content="a" * 150),
        Message(role="user", content="继续" + "续" * 100),
        Message(role="assistant", content="好" + "续" * 100),
        Message(role="user", content="再继续" + "续" * 100),
    ]
    b.compress(messages)
    assert prevs and prevs[0] is not None
    assert "上次摘要" in prevs[0]
