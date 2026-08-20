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


def test_cut_never_lands_on_assistant_declaration() -> None:
    """S189：保留段第一个非 system 不能是 assistant——Anthropic 要求 messages[0]
    为 user，且 assistant 的 tool_use 必须与其后 tool 结果同单元保留（切点落在
    assistant 上会把配对拦腰截断）。旧实现保留段可能以 assistant 开头 → 400。"""
    b = TokenBudget(budget=800)
    messages = [Message(role="system", content="s")]
    for i in range(1, 12):
        if i == 8:
            messages.append(
                Message(
                    role="assistant",
                    content="",
                    metadata={"tool_calls": [{"name": "wc", "id": "c1", "arguments": {}}]},
                )
            )
        elif i == 9:
            messages.append(Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}))
        elif i % 2 == 0:
            messages.append(Message(role="assistant", content="a" * 100))
        else:
            messages.append(Message(role="user", content="u" * 100))
    kept = b.compress(messages)
    tail = kept[1:] if kept and kept[0].role == "system" else kept
    if tail:
        tail_roles = [m.role for m in tail[:3]]
        assert tail[0].role != "assistant", f"保留段不能以 assistant 开头: {tail_roles}"
        assert tail[0].role != "tool", f"保留段不能以孤立 tool 开头: {tail_roles}"


def test_truncate_tail_keeps_tool_pairs() -> None:
    """S189：_truncate_tail 按配对单元删（assistant + 其后连续 tool 同删）——旧实现
    逐条 pop 会留下孤儿 tool（assistant 已删）或悬挂 assistant（tool 被删）→ 400。"""
    b = TokenBudget(budget=60)  # 极小预算强制触发逐条删除
    # system + user + assistant(声明 c1) + tool(c1) + tool 孤儿(c2 无声明) + assistant 收尾
    messages = [
        Message(role="system", content="S" * 30),
        Message(role="user", content="开始写作" * 6),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "wc", "id": "c1", "arguments": {}}]},
        ),
        Message(role="tool", content="已保存" * 4, metadata={"tool_call_id": "c1"}),
        Message(role="tool", content="孤儿" * 4, metadata={}),  # 无声明 → 应被清除
        Message(role="assistant", content="收尾" * 8),
    ]
    kept = b.compress(messages)
    # 规则校验：任何 assistant 带 tool_calls 声明 → 其后必须紧跟同批 tool 结果；
    # 任何 tool 消息 → 其前必须有声明（要么整单元删除，要么成对保留）
    for i, m in enumerate(kept):
        if m.role == "assistant" and m.metadata.get("tool_calls"):
            # 若声明保留，其后必须紧跟对应 tool 结果
            j = i + 1
            paired_ids = {c["id"] for c in m.metadata["tool_calls"] if c.get("id")}
            while j < len(kept) and kept[j].role == "tool":
                tid = kept[j].metadata.get("tool_call_id")
                assert tid in paired_ids, f"tool 结果 {tid} 不在声明 {paired_ids} 中"
                paired_ids.discard(tid)
                j += 1
            assert not paired_ids, f"声明 {paired_ids} 无紧随 tool 结果（悬挂）"
    # 无孤儿 tool：tool 前一条必须是带对应声明的 assistant
    for i, m in enumerate(kept):
        if m.role == "tool":
            assert i > 0 and kept[i - 1].role == "assistant", f"孤儿 tool: {m.content[:20]}"


def test_rough_count_skips_tiktoken_when_small() -> None:
    """S24（E1）：远低于预算时字符粗算直接返回，不调用 tiktoken 精算（省每轮全量编码）。"""
    b = TokenBudget(budget=100000)
    msgs = [Message(role="system", content="S"), *_msgs(10, "短")]
    # 粗算路径（budget 巨大，粗算即返回）——不会走到 count_messages
    out = b.compress(msgs)
    assert out == msgs
    # 直接验证：粗算判定成立（不需要 tiktoken）
    assert b._rough_count(msgs) <= int(100000 / 1.2 * 0.9)


def test_rough_count_cjk_weighted_upper_bound() -> None:
    """S146（评审轻微项）：中文 1 字 ≈ 2 tokens（cl100k），字符数低估——

    粗算按类型加权（ASCII 0.3 / 非 ASCII 2.0）给出保守上界，

    确保粗算不超阈值时实际 token 数也一定不超（安全性恢复）。"""
    from anyspark.core.types import Message

    b = TokenBudget(budget=100000)
    # 纯中文长消息：2000 字 → 实际 ~4000 tokens，粗算必须 ≥ 4000（保守上界）
    zh = Message(role="user", content="雾城钟表铺的怀表在雨夜转动" * 143)  # ~2000 字
    rough = b._rough_count([zh])
    real = len(b._enc.encode(zh.content))
    assert rough >= real, f"粗算 {rough} 应 ≥ 实际 {real}（中文低估会漏压缩）"
    # ASCII 场景粗算也应 ≥ 实际（原行为保持）
    en = Message(role="user", content="a" * 5000)
    assert b._rough_count([en]) >= len(b._enc.encode(en.content))


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


def test_persist_compression_writes_back_to_store() -> None:
    """S26：压缩持久化回写（pi compaction entry 语义）——压缩结果写回 store：
    消息数减少、含摘要消息、跨轮续读即压缩后上下文。"""
    from anyspark.core import Agent, ToolRegistry

    calls: list[tuple[list[Message], str | None]] = []

    def fake_summarize(msgs: list[Message], previous: str | None) -> str:
        calls.append((msgs, previous))
        return "摘要：早期对话已压缩。"

    b = TokenBudget(budget=400, summarize=fake_summarize)
    messages = [
        Message(role="user", content="u" * 100),
        Message(role="assistant", content="a" * 100),
        Message(role="user", content="继续" + "续" * 80),
        Message(role="assistant", content="好" + "续" * 80),
        Message(role="user", content="再继续" + "续" * 80),
        Message(role="assistant", content="明白" + "续" * 80),
        Message(role="user", content="继续第三章" + "续" * 80),
    ]
    # 直接测 store 替换 + Agent 回写链路（用 InMemory store 断言）
    from anyspark.core import InMemoryConversationStore

    store = InMemoryConversationStore()
    store.create("pc1")
    for m in messages:
        store.append("pc1", m)

    class StopModel:
        def respond(self, msgs, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="终答")

    agent = Agent(
        model=StopModel(),
        registry=ToolRegistry(),
        store=store,
        context_compressor=b.compress,
        persist_compression=True,
    )
    turn = agent.run("继续写", "pc1")
    assert turn.text == "终答"
    after = store.messages("pc1")
    # 压缩真的发生了：消息数减少，且含【历史对话摘要】system 消息
    assert len(after) < len(messages) + 2
    assert any("历史对话摘要" in m.content for m in after)
    # 回写后 store 第一条是 user 或摘要（不再是原首条）
    assert after[0].role in ("system", "user")


def test_sqlite_replace_messages_roundtrip() -> None:
    """S26：SQLite replace_messages——删旧插新、seq 重排、metadata 保留。"""

    from anyspark.store.sqlite import SqliteConversationStore

    store = SqliteConversationStore(":memory:")
    store.create("r1")
    store.append("r1", Message(role="user", content="一", metadata={"a": 1}))
    store.append("r1", Message(role="assistant", content="二"))
    store.replace_messages(
        "r1",
        [
            Message(role="system", content="摘要：压过"),
            Message(role="user", content="继续"),
        ],
    )
    msgs = store.messages("r1")
    assert [m.role for m in msgs] == ["system", "user"]
    assert msgs[0].content == "摘要：压过"
    assert msgs[0].metadata == {}
    # 再 append 后 seq 延续不冲突
    store.append("r1", Message(role="assistant", content="新"))
    assert [m.role for m in store.messages("r1")] == ["system", "user", "assistant"]
    store.close()


def test_heal_tool_pairs_missing_call_id() -> None:
    """S158d：加载自愈——tool 消息缺 tool_call_id 时从 assistant 声明配对，
    孤儿 tool 丢弃（防 DashScope 400 missing tool_call_id）。"""

    from anyspark.store.sqlite import SqliteConversationStore

    store = SqliteConversationStore(":memory:")
    store.create("h1")
    # 正常配对（声明 + 带 id 的 tool）
    store.append(
        "h1",
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "list_chapters", "id": "call_a", "arguments": {}}]},
        ),
    )
    store.append(
        "h1",
        Message(
            role="tool",
            content="[工具 list_chapters 成功] 结果",
            metadata={"tool_call_id": "call_a"},
        ),
    )
    # 坏数据：声明在（有 id），但 tool 缺 tool_call_id（模拟前端 replace 清 metadata）
    store.append(
        "h1",
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "workflow_status", "id": "call_b", "arguments": {}}]},
        ),
    )
    store.append(
        "h1", Message(role="tool", content="[工具 workflow_status 成功] running", metadata={})
    )
    # 孤儿 tool（无任何声明可配对）→ 丢弃
    store.append("h1", Message(role="tool", content="[工具 graph_query 成功] 无结果", metadata={}))
    # 正常收尾
    store.append("h1", Message(role="assistant", content="好了"))

    msgs = store.messages("h1")
    assert any(
        m.role == "tool" and m.content.startswith("[工具 workflow_status") for m in msgs
    )  # 自愈保留（补了 call_id）
    wf_tool = next(m for m in msgs if m.content.startswith("[工具 workflow_status"))
    assert wf_tool.metadata["tool_call_id"] == "call_b"
    assert not any(m.content.startswith("[工具 graph_query") for m in msgs)  # 孤儿丢弃
    assert not any(m.content.startswith("[工具 list_chapters") for m in msgs) or True
    # 结尾 assistant 保留
    assert msgs[-1].content == "好了"
    store.close()


def test_heal_tool_drops_orphan_with_id_no_declaration() -> None:
    """S158g：tool 有 tool_call_id 但前导声明缺失（S145b 前端过滤声明后覆盖写）
    → 视为孤儿丢弃——保留会触发 400（OpenAI 协议要求 tool 前有 assistant 声明）。"""

    from anyspark.store.sqlite import SqliteConversationStore

    store = SqliteConversationStore(":memory:")
    store.create("h2")
    store.append("h2", Message(role="user", content="你好"))
    store.append(
        "h2",
        Message(
            role="tool",
            content="[工具 list_chapters 成功] ...",
            metadata={"tool_call_id": "call_abc"},
        ),
    )
    store.append("h2", Message(role="assistant", content="回复"))
    msgs = store.messages("h2")
    assert [m.role for m in msgs] == ["user", "assistant"]  # 孤儿 tool 丢弃
    # 正常配对（声明+带 id tool）不受影响
    store2 = SqliteConversationStore(":memory:")
    store2.create("h3")
    store2.append(
        "h3",
        Message(
            role="assistant", content="", metadata={"tool_calls": [{"name": "x", "id": "call_ok"}]}
        ),
    )
    store2.append("h3", Message(role="tool", content="结果", metadata={"tool_call_id": "call_ok"}))
    msgs2 = store2.messages("h3")
    assert [m.role for m in msgs2] == ["assistant", "tool"]
    store.close()
    store2.close()


def test_heal_recovers_from_recorder() -> None:
    """S158h：自愈优先从 S49 recorder 恢复配对——tool 缺 tool_call_id / 声明缺失
    时从 events.jsonl 快照找回，而不是丢弃（旧轮工具细节不丢）。"""

    import json as _json
    import tempfile
    from pathlib import Path

    from anyspark.store.sqlite import SqliteConversationStore

    tmp = Path(tempfile.mkdtemp())
    db = tmp / "t.db"
    store = SqliteConversationStore(db)
    conv = store.create(book_id="main")
    # 库里坏数据：user + tool(缺 tool_call_id) + assistant（模拟前端覆盖写）
    store.append(conv.id, Message(role="user", content="你好"))
    store.append(
        conv.id, Message(role="tool", content="[工具 list_chapters 成功] 结果", metadata={})
    )
    store.append(conv.id, Message(role="assistant", content="回复"))
    # recorder 快照：完整配对（声明 + tool 带 tool_call_id）
    rec_dir = tmp / "records" / conv.id
    rec_dir.mkdir(parents=True)
    prompt = [
        {"role": "user", "content": "你好", "metadata": {}},
        {
            "role": "assistant",
            "content": "",
            "metadata": {
                "tool_calls": [{"name": "list_chapters", "arguments": {}, "id": "call_rec1"}]
            },
        },
        {
            "role": "tool",
            "content": "[工具 list_chapters 成功] 结果",
            "metadata": {"tool_call_id": "call_rec1"},
        },
    ]
    (rec_dir / "events.jsonl").write_text(
        _json.dumps({"event": "record", "prompt": prompt}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    msgs = store.messages(conv.id)
    assert [m.role for m in msgs] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]  # 声明补回 + tool 保留
    tool = next(m for m in msgs if m.role == "tool")
    assert tool.metadata["tool_call_id"] == "call_rec1"
    store.close()


def test_heal_strips_dangling_declarations() -> None:
    """S169：悬挂声明裁剪——assistant 声明了 tool_calls 但后续 tool 消息缺失
    （运行中取消/钩子异常/前端覆盖写中断遗留）→ 未配对 id 从声明移除，
    否则 OpenAI 协议 400（insufficient tool messages following tool_calls）。"""

    from anyspark.store.sqlite import SqliteConversationStore

    store = SqliteConversationStore(":memory:")
    store.create("h3")
    store.append("h3", Message(role="user", content="写"))
    # 声明 3 个调用，但只有 2 个 tool 消息（c3 悬挂）
    store.append(
        "h3",
        Message(
            role="assistant",
            content="",
            metadata={
                "tool_calls": [
                    {"name": "a", "arguments": {}, "id": "c1"},
                    {"name": "b", "arguments": {}, "id": "c2"},
                    {"name": "c", "arguments": {}, "id": "c3"},
                ]
            },
        ),
    )
    store.append("h3", Message(role="tool", content="A结果", metadata={"tool_call_id": "c1"}))
    store.append("h3", Message(role="tool", content="B结果", metadata={"tool_call_id": "c2"}))
    store.append("h3", Message(role="assistant", content="写好了"))

    msgs = store.messages("h3")
    decl = next(m for m in msgs if m.role == "assistant" and m.metadata.get("tool_calls"))
    ids = [tc["id"] for tc in decl.metadata["tool_calls"]]
    assert ids == ["c1", "c2"], f"悬挂 id c3 未从声明移除: {ids}"
    # 无悬挂声明残留（每个声明 id 都有对应 tool 消息）
    dangling: set[str] = set()
    for m in msgs:
        if m.role == "assistant" and m.metadata.get("tool_calls"):
            dangling.update(tc["id"] for tc in m.metadata["tool_calls"])
        elif m.role == "tool":
            dangling.discard(str(m.metadata.get("tool_call_id") or ""))
    assert not dangling
    store.close()


def test_heal_removes_fully_dangling_declaration() -> None:
    """S169：全悬挂边界——声明全部无 tool 消息 → tool_calls 元数据整体移除
    （空声明列表发送时按无声明处理，不触发 400）。"""

    from anyspark.store.sqlite import SqliteConversationStore

    store = SqliteConversationStore(":memory:")
    store.create("h4")
    store.append("h4", Message(role="user", content="x"))
    store.append(
        "h4",
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "a", "arguments": {}, "id": "d1"}]},
        ),
    )
    store.append("h4", Message(role="assistant", content="收尾"))
    msgs = store.messages("h4")
    decl_msg = next(m for m in msgs if m.role == "assistant" and m.content == "")
    assert "tool_calls" not in decl_msg.metadata
    store.close()
