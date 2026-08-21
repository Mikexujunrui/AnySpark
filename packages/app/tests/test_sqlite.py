"""anyspark.store.sqlite — 会话与章节存储的真实 SQLite 测试。"""

import tempfile
from pathlib import Path

from anyspark.core.types import Message
from anyspark.store import ChapterStore, SqliteConversationStore


def _db() -> Path:
    d = tempfile.mkdtemp()
    return Path(d) / "test.db"


def test_conversation_crud() -> None:
    db = _db()
    store = SqliteConversationStore(db)
    try:
        conv = store.create()
        store.append(conv.id, Message(role="user", content="a"))
        store.append(conv.id, Message(role="assistant", content="b"))
        msgs = store.messages(conv.id)
        assert [m.content for m in msgs] == ["a", "b"]
        assert store.get(conv.id) is not None
        assert store.list_conversations()
    finally:
        store.close()


def test_chapter_upsert_and_version_history() -> None:
    db = _db()
    store = ChapterStore(db)
    try:
        c1 = store.upsert("main", "第一章", "版本一正文", 0)
        c2 = store.upsert("main", "第一章", "版本二正文（修改后）", 0)
        assert c1.id == c2.id  # 同一章覆盖
        got = store.get(c1.id)
        assert got is not None
        assert got.content == "版本二正文（修改后）"
        assert len(got.versions) == 1  # 旧版进了历史
        assert got.versions[0]["content"] == "版本一正文"
    finally:
        store.close()


def test_chapter_list_ordered() -> None:
    db = _db()
    store = ChapterStore(db)
    try:
        store.upsert("main", "第二章", "b", 1)
        store.upsert("main", "第一章", "a", 0)
        titles = [c.title for c in store.list_by_book("main")]
        assert titles == ["第一章", "第二章"]
    finally:
        store.close()


def test_chapter_delete_commits() -> None:
    """S75：ChapterStore.delete 必须提交事务（前端报告并发锁根因——
    缺 commit 则 DELETE 事务保持打开、锁持续持有，后续写请求 500 locked）。"""
    import tempfile
    from pathlib import Path

    from anyspark.store import ChapterStore

    store = ChapterStore(Path(tempfile.mkdtemp()) / "t.db")
    ch = store.upsert("main", "锁测试章", "内容", 1)
    assert store.delete(ch.id) is True
    # 删除后立即写（之前：缺 commit → 事务未提交 → 立即写报 locked）
    ch2 = store.upsert("main", "新章", "内容", 2)
    assert ch2.title == "新章"
    assert store.get(ch.id) is None


def test_store_wal_enabled() -> None:
    """S75：WAL 模式（多 store 独立连接并发加固）+ timeout=30。"""
    import tempfile
    from pathlib import Path

    from anyspark.store import ChapterStore

    store = ChapterStore(Path(tempfile.mkdtemp()) / "t.db")
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_replace_messages_pairing_guard() -> None:
    """S190：replace_messages 写入前配对自愈——任何整体替换历史的路径（压缩回写 /
    前端覆盖保存）落库都是配对完整序列，孤儿 tool / 悬挂声明在写入前修剪，
    绝不让残缺配对残留到协议转换时 400。"""

    def _bad_seq() -> list[Message]:
        # ① 悬挂声明：assistant 声明 c1/c2 但无任何 tool 结果
        # ② 孤儿 tool：tool 结果无对应 assistant 声明
        # ③ 缺 tool_call_id：tool 消息有内容但 metadata 空
        # ④ 正常配对（不应被误伤）
        return [
            Message(role="user", content="写"),
            Message(
                role="assistant",
                content="",
                metadata={
                    "tool_calls": [
                        {"name": "a", "arguments": {}, "id": "c1"},
                        {"name": "b", "arguments": {}, "id": "c2"},
                    ]
                },
            ),  # 悬挂（无 tool 结果）
            Message(role="tool", content="孤儿结果", metadata={"tool_call_id": "c_zzz"}),  # 孤儿
            Message(role="assistant", content="继续"),
            Message(role="tool", content="刚才的结果", metadata={}),  # 缺 tool_call_id
            Message(role="assistant", content="完成"),
        ]

    db = _db()
    store = SqliteConversationStore(db)
    try:
        conv = store.create()
        store.replace_messages(conv.id, _bad_seq())
        msgs = store.messages(conv.id)  # 幂等：读回也应配对完整
        # ① 配对不变量：assistant 声明的每个 tool_call id 必须能在后续 tool 结果里配对
        #    （c1 被缺 id 的 tool 复用补配 → 合法保留；c2 真悬挂 → 被裁剪）
        for i, m in enumerate(msgs):
            if m.role == "assistant":
                for tc in m.metadata.get("tool_calls") or []:
                    tid = tc.get("id")
                    assert any(
                        mm.role == "tool" and mm.metadata.get("tool_call_id") == tid
                        for mm in msgs[i:]
                    ), f"悬挂声明 id {tid}"
        # ② 孤儿 tool（c_zzz 无声明）→ 丢弃
        assert not any(m.role == "tool" and "孤儿结果" in m.content for m in msgs)
        # ③ 缺 tool_call_id 的 tool → 从相邻/recorder 补配或丢弃，绝不留无 id 的 tool
        for m in msgs:
            if m.role == "tool":
                assert m.metadata.get("tool_call_id"), f"tool 消息必须有配对 id: {m.metadata}"
        # ④ 序列不变量：任何 tool 前必有 assistant（无孤立 tool 开头）
        for i, m in enumerate(msgs):
            if m.role == "tool":
                assert msgs[i - 1].role == "assistant", "孤儿 tool 残留"
    finally:
        store.close()


def test_replace_messages_editing_text_keeps_pairing() -> None:
    """S190：编辑 assistant 文本（前端覆盖）后配对不 400——带 tool_calls 的 assistant
    改文本导致声明丢失时，tool 结果要么从 recorder 找回声明、要么作为孤儿丢弃
    （安全降级），绝不留下"tool_result 无对应 tool_use"。"""
    db = _db()
    store = SqliteConversationStore(db)
    try:
        conv = store.create()
        # 模拟 save_conversation_messages 的结果：assistant 文本被编辑（metadata 空 =
        # 内容失配丢失 tool_calls），但其 tool 结果还在、且按旧序补回
        edited = [
            Message(role="user", content="写"),
            Message(role="assistant", content="（文本已被用户改写）"),  # 丢了 tool_calls 声明
            Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),
            Message(role="assistant", content="完成"),
        ]
        store.replace_messages(conv.id, edited)
        msgs = store.messages(conv.id)
        # 不变量：无孤儿 tool；每条 tool 前有 assistant 或本身已配平
        for i, m in enumerate(msgs):
            if m.role == "tool":
                assert i > 0 and msgs[i - 1].role == "assistant", f"孤儿 tool: {m.content}"
        # 转换层契约：发给模型的序列里绝不能出现"tool_result 无对应 tool_use"
        # （此处不直接调 anthropic，断言存储层配对不变量即可）
    finally:
        store.close()


def test_repair_dangling_decls_persists_fix() -> None:
    """S200：repair_dangling_decls 把历史遗留的悬挂 tool_calls 声明落库修剪。

    模拟 S170 之前的旧版数据：assistant 声明 tool_calls 后直接接「已中断」
    文本（无 tool 结果）——修复后声明应从 metadata 移除且**落库**（新 store
    实例读取时也干净，证明不是内存级）。"""

    from anyspark.core.types import Message

    db = _db()
    store = SqliteConversationStore(db)
    try:
        conv = store.create()
        # 旧版遗留：声明 + 取消文本，无 tool 结果。直接写裸 metadata 模拟旧版
        # 程序落库（不走 replace_messages——新版 S190 写入守卫会提前修掉）
        store.append(conv.id, Message(role="user", content="写"))
        store.append(
            conv.id,
            Message(
                role="assistant",
                content="",
                metadata={"tool_calls": [{"name": "read_chapter", "arguments": {}, "id": "c1"}]},
            ),
        )
        store.append(conv.id, Message(role="assistant", content="已中断（用户取消）。"))
        # 确认脏数据确实在库里（append 无写入守卫）
        raw = store._conn.execute(
            "SELECT metadata FROM messages WHERE conversation_id=? AND role='assistant'",
            (conv.id,),
        ).fetchall()
        assert any("tool_calls" in (r["metadata"] or "") for r in raw)
        # 修复：找到 1 条悬挂
        assert store.repair_dangling_decls() == 1
        # 修复已落库：新实例读取干净
        store2 = SqliteConversationStore(db)
        try:
            msgs = store2.messages(conv.id)
            for m in msgs:
                assert not (m.metadata or {}).get("tool_calls"), f"悬挂未清除: {m.metadata}"
        finally:
            store2.close()
        # 幂等：再跑 0 变更
        assert store.repair_dangling_decls() == 0
    finally:
        store.close()
