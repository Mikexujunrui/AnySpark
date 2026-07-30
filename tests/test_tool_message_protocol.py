"""Regression tests for OpenAI-compatible tool message ordering."""

from core.agent_loop import _sanitize_tool_messages


def _assistant(*call_ids: str) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "extract_chapter", "arguments": "{}"},
            }
            for call_id in call_ids
        ],
    }


def test_sanitizer_moves_interleaved_tool_results_next_to_assistant():
    messages = [
        {"role": "user", "content": "提取两章"},
        _assistant("call_1", "call_2"),
        {"role": "tool", "tool_call_id": "call_1", "content": "第一章完成"},
        {"role": "user", "content": "[系统提示] 请汇报"},
        {"role": "tool", "tool_call_id": "call_2", "content": "第二章完成"},
        {"role": "assistant", "content": "完成"},
    ]

    _sanitize_tool_messages(messages)

    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "user",
        "assistant",
    ]
    assert [messages[2]["tool_call_id"], messages[3]["tool_call_id"]] == ["call_1", "call_2"]


def test_sanitizer_backfills_missing_result_and_drops_orphan():
    messages = [
        _assistant("call_1", "call_2"),
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "tool", "tool_call_id": "orphan", "content": "must disappear"},
    ]

    _sanitize_tool_messages(messages)

    assert [message["role"] for message in messages] == ["assistant", "tool", "tool"]
    assert messages[2]["tool_call_id"] == "call_2"
    assert "占位" in messages[2]["content"]
    assert all(message.get("tool_call_id") != "orphan" for message in messages)


def test_sanitizer_repairs_missing_and_duplicate_call_ids():
    messages = [
        _assistant("", "same"),
        {"role": "tool", "tool_call_id": "same", "content": "first"},
        _assistant("same"),
        {"role": "tool", "tool_call_id": "same", "content": "second"},
    ]

    _sanitize_tool_messages(messages)

    first_ids = [call["id"] for call in messages[0]["tool_calls"]]
    second_assistant = next(
        message for message in messages[1:] if message.get("role") == "assistant" and message.get("tool_calls")
    )
    second_id = second_assistant["tool_calls"][0]["id"]
    assert all(first_ids)
    assert len({*first_ids, second_id}) == 3
