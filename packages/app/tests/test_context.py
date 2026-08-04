"""anyspark.server.context — token 预算两阶段压缩测试。"""

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

    def fake_summarize(history: list[Message]) -> str:
        captured.append(history)
        return "摘要：早期对话已压缩。"

    b = TokenBudget(budget=100, summarize=fake_summarize)
    msgs = [Message(role="system", content="系统指令" * 20), *_msgs(30, "长消息")]
    out = b.compress(msgs)
    # 摘要器被调用（拿到了可压缩段）
    assert captured and len(captured[0]) < len(msgs)
    # 输出含历史摘要系统消息
    assert any("历史对话摘要" in m.content for m in out)
    # 最近消息保留
    assert out[-1].content == msgs[-1].content
    assert b.count_messages(out) < b.count_messages(msgs)


def test_summarize_failure_falls_back_to_prune() -> None:
    """摘要器抛异常：降级纯 prune，不中断。"""

    def broken(history: list[Message]) -> str:
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
    out = s([Message(role="user", content="x")])
    assert "雨夜" in out


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

    def fake_summarize(msgs: list[Message]) -> str:
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
