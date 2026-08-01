"""User-interaction flows: plot_cards (剧情方向选择) and question (ask_user).

Both block on ``question_manager`` for the user's answer, then turn the
answer into a readable tool message the LLM sees.
"""

import asyncio

from core.loop_event import LoopEvent
from core.question import manager as question_manager


async def flow_plot_cards(result: dict, book_id: str):
    """剧情卡片：前端渲染可选方向，用户选择后回填给 LLM。"""
    events = await flow_plot_cards_emit(result, book_id)
    if events is None:
        return [], "无可选方向", False, None
    try:
        answers = await asyncio.wait_for(question_manager.wait_for_answer(events[0].data["id"]), timeout=300)
        selected_text = answers[0][0] if answers and answers[0] else "用户未选择"
    except TimeoutError:
        selected_text = "用户超时未选择"
    except (ValueError, IndexError, KeyError):
        selected_text = "用户拒绝了所有选项，请重新构思方向"
    result_str = f"用户的剧情方向选择: {selected_text}\n\n请根据用户选择继续。"
    return events, result_str, False, None


async def flow_plot_cards_emit(result: dict, book_id: str):
    """Stage 1: register the question and produce the plot_cards event — does NOT block."""
    cards = result.get("cards", [])
    if not cards:
        return None
    q_req = question_manager.create_question(
        [
            {
                "question": "选择一个剧情方向",
                "header": "剧情走向",
                "options": [{"label": c.get("title", ""), "description": c.get("description", "")} for c in cards],
                "card_type": "plot_cards",
                "cards": cards,
                "context_summary": result.get("context_summary", ""),
                "custom": True,
            }
        ],
        book_id,
    )
    return [
        LoopEvent(
            type="plot_cards",
            data={
                "id": q_req.id,
                "context_summary": result.get("context_summary", ""),
                "cards": cards,
                "instruction": result.get("instruction", ""),
            },
        )
    ]


async def flow_ask_user(result: dict, book_id: str):
    """ask_user 工具：前端弹问题，用户回答，格式化回填给 LLM。"""
    events = await flow_ask_user_emit(result, book_id)
    if events is None:
        return [], "无问题", False, None
    try:
        answers = await asyncio.wait_for(question_manager.wait_for_answer(events[0].data["id"]), timeout=300)
    except TimeoutError:
        answers = [["用户超时未回复"]]
    except Exception:
        answers = [["用户拒绝了提问"]]
    result_str = await flow_ask_user_wait(result, book_id, answers)
    return events, result_str, False, None


async def flow_ask_user_emit(result: dict, book_id: str):
    """Stage 1: register the question and produce the SSE event — does NOT block.

    Returns None when there is nothing to ask (caller should treat as no-op).
    Normalizes ``options`` (string list → {label, description}) so the frontend
    QuestionCard always has ``label`` to render.
    """
    qs = result.get("questions", [])
    if not qs:
        return None
    normalized = []
    for q in qs:
        entry = dict(q)
        opts = entry.get("options")
        if isinstance(opts, list):
            entry["options"] = [
                o if isinstance(o, dict) else {"label": str(o), "description": ""} for o in opts
            ]
        normalized.append(entry)
    q_req = question_manager.create_question(normalized, book_id)
    return [LoopEvent(type="question", data={"id": q_req.id, "questions": q_req.questions})]


async def flow_ask_user_wait(result: dict, book_id: str, answers: list[list[str]] | None = None):
    """Stage 2: assemble the tool-message text from the user's answers."""
    qs = result.get("questions", [])
    if answers is None:
        answers = [["用户未回复"]]
    answer_parts = []
    for i, q in enumerate(qs):
        q_text = q.get("question", f"问题{i + 1}")
        ans = answers[i] if i < len(answers) else ["未回复"]
        answer_parts.append(f"Q: {q_text}\nA: {', '.join(ans)}")
    return "用户回答:\n" + "\n\n".join(answer_parts)
