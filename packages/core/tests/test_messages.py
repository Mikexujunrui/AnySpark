"""anyspark.core.messages 测试 — 通用配对守卫 sanitize_tool_pairing。"""

from __future__ import annotations

from anyspark.core import Message
from anyspark.core.messages import sanitize_tool_pairing


def _user(c: str = "写") -> Message:
    return Message(role="user", content=c)


def _assistant_decl(*ids: str) -> Message:
    return Message(
        role="assistant",
        content="",
        metadata={"tool_calls": [{"name": f"t{i}", "arguments": {}, "id": i} for i in ids]},
    )


def _tool(tid: str = "c1", content: str = "结果") -> Message:
    return Message(role="tool", content=content, metadata={"tool_call_id": tid})


def test_clean_pairing_unchanged() -> None:
    """正常配对序列原样返回（零行为变化）。"""
    msgs = [_user(), _assistant_decl("c1"), _tool("c1"), Message(role="assistant", content="完成")]
    out = sanitize_tool_pairing(msgs)
    assert out == msgs


def test_orphan_tool_removed() -> None:
    """孤儿 tool 结果（无对应声明）→ 移除。"""
    msgs = [_user(), _assistant_decl("c1"), _tool("c1"), _tool("c_orphan"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    assert all(m.role != "tool" or m.metadata.get("tool_call_id") == "c1" for m in out)
    assert not any(m.role == "tool" and m.metadata.get("tool_call_id") == "c_orphan" for m in out)


def _assistant_never(c: str = "完成") -> Message:
    return Message(role="assistant", content=c)


def test_dangling_declaration_stripped() -> None:
    """悬挂声明（无任何 tool 结果配对）→ 从 assistant tool_calls 裁剪。"""
    msgs = [_user(), _assistant_decl("c1", "c2"), _tool("c1"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    asst = next(m for m in out if m.role == "assistant" and m.metadata.get("tool_calls"))
    ids = [tc["id"] for tc in asst.metadata["tool_calls"]]
    assert ids == ["c1"], f"悬挂的 c2 应裁剪: {ids}"


def test_missing_id_from_neighbor_decl() -> None:
    """缺 id 的 tool 结果 → 用相邻未配对声明补配（保持声明→tool 顺序）。"""
    msgs = [_user(), _assistant_decl("c1"), _tool("", "补配这个"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    t = next(m for m in out if m.role == "tool")
    assert t.metadata.get("tool_call_id") == "c1"
    # 且声明保留（c1 有配对）
    asst = next(m for m in out if m.role == "assistant" and m.metadata.get("tool_calls"))
    assert [tc["id"] for tc in asst.metadata["tool_calls"]] == ["c1"]


def test_missing_id_orphan_removed() -> None:
    """缺 id 且无可用声明 → 孤儿移除。"""
    msgs = [_user(), _tool("", "无主结果"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    assert not any(m.role == "tool" for m in out)


def test_separated_pair_kept_relaxed() -> None:
    """宽松层：tool 结果被 user 插话隔开仍保留（声明有结果、结果有声明）。\n
    协议特有的“严格紧邻”由各适配器转换防御处理，不在此层。"""
    msgs = [_user(), _assistant_decl("c1"), _user("插话"), _tool("c1"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    assert any(m.role == "tool" and m.metadata.get("tool_call_id") == "c1" for m in out)
    # 声明保留
    assert any(m.role == "assistant" and m.metadata.get("tool_calls") for m in out)


def test_multi_id_partial_pairing() -> None:
    """同批多声明部分配对：有结果的保留、无结果的裁剪（宽松层）。"""
    msgs = [_user(), _assistant_decl("c1", "c2"), _tool("c1"), _tool("c2"), _assistant_never()]
    out = sanitize_tool_pairing(msgs)
    asst = next(m for m in out if m.role == "assistant" and m.metadata.get("tool_calls"))
    assert [tc["id"] for tc in asst.metadata["tool_calls"]] == ["c1", "c2"]
