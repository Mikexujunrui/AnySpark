"""Tests for _await_answer — the permission-confirmation waiter.

Regression: the old implementation polled in 10s chunks; the first chunk
timeout cancelled ``wait_for_answer`` which pops its future in ``finally``,
so the second iteration found no pending future and instantly returned
``[["已取消"]]``. Anyone who answered the preceding ask_user but didn't
click the permission dialog within ~10s was mis-reported as having
cancelled their own write. These tests pin the new single-wait behaviour:
only a genuine timeout or an explicit cancel reports as non-confirmed.
"""

import asyncio

from core.agent_loop import _await_answer
from core.loop_state import LoopState
from core.question import manager as question_manager


def _make_question():
    return question_manager.create_question(
        [
            {
                "question": "确认执行该操作？",
                "options": [{"label": "确认执行"}, {"label": "取消"}],
            }
        ],
        book_id="test",
    )


async def test_await_answer_confirmed():
    req = _make_question()
    asyncio.get_running_loop().call_later(
        0.05, lambda: question_manager.reply(req.id, [["确认执行"]])
    )
    result = await _await_answer(req.id, timeout=1)
    assert result == "confirmed"


async def test_await_answer_cancelled():
    req = _make_question()
    asyncio.get_running_loop().call_later(
        0.05, lambda: question_manager.reply(req.id, [["取消"]])
    )
    result = await _await_answer(req.id, timeout=1)
    assert result == "cancelled"


async def test_await_answer_timeout_reports_timeout_not_cancel():
    req = _make_question()
    result = await _await_answer(req.id, timeout=0.2)
    assert result == "timeout"


async def test_await_answer_late_reply_still_confirms():
    # Regression: with the old 10s-chunk polling, a reply arriving after the
    # first chunk timeout was silently dropped (future already popped) and
    # the waiter reported "cancelled". With the single-wait fix a reply
    # arriving before the full window must still confirm.
    req = _make_question()
    asyncio.get_running_loop().call_later(
        0.15, lambda: question_manager.reply(req.id, [["确认执行"]])
    )
    result = await _await_answer(req.id, timeout=1)
    assert result == "confirmed"


def test_loop_state_has_confirm_cancel_fuse():
    s = LoopState()
    assert s.consecutive_confirm_cancels == 0
