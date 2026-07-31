"""Engine-signal flows: autopilot_plan / task_list.

These coordinate background engines (Autopilot startup confirmation,
task-list tracking).
"""


from core.loop_event import LoopEvent
from core.question import _await_answer
from core.question import manager as question_manager


async def flow_autopilot_plan(result: dict, book_id: str):
    """Autopilot 启动确认：弹窗 → 用户确认 → 启动/取消后台任务。"""
    task_id = result.get("task_id", "")
    plan_summary = result.get("plan_summary", "")
    chapters = result.get("chapters", [])
    audit_mode = result.get("audit_mode", "soft")
    ch_list = "、".join(f"第{c['index']}章{c.get('title', '')}" for c in chapters[:5])
    confirm_msg = (
        f"是否启动 Autopilot 自主写作？\n\n"
        f"计划: {plan_summary}\n"
        f"章节: {ch_list}{'...' if len(chapters) > 5 else ''}\n"
        f"模式: {audit_mode}\n\n"
        f"启动后将在后台逐章执行，您可随时暂停/取消。"
    )
    q_req = question_manager.create_question(
        [
            {
                "question": confirm_msg,
                "header": "启动 Autopilot",
                "options": [
                    {"label": "确认启动", "description": "开始执行写作计划"},
                    {"label": "取消", "description": "不启动 Autopilot"},
                ],
                "custom": False,
            }
        ],
        book_id,
    )
    events = [LoopEvent(type="question", data={"id": q_req.id, "questions": q_req.questions})]
    confirmed = await _await_answer(q_req.id)
    if confirmed == "confirmed":
        from core.autopilot_runner import autopilot as ap

        ok = await ap.confirm_start(task_id)
        if ok:
            result_str = (
                f"Autopilot 已启动！\n\n"
                f"任务ID: {task_id}\n"
                f"计划: {plan_summary}\n"
                f"模式: {audit_mode}\n\n"
                f"后台执行中，可在右侧面板监控进度。完成后会自动通知。"
            )
        else:
            result_str = "Autopilot 启动失败，请重试。"
    else:
        if confirmed == "timeout":
            result_str = "Autopilot 启动确认超时（5分钟未收到回复），未启动。如需启动请重新发起。"
        else:
            result_str = "用户取消了 Autopilot 启动。如需调整参数，请重新发起。"
        from core.task_queue import task_queue as tq

        tq.cancel_task(task_id)
    return events, result_str, False, None


async def flow_task_list(result: dict, book_id: str):
    """任务列表：向前端发 task_list 事件；active_task_list_id 由调用方记录（依赖 state）。"""
    events = [LoopEvent(type="task_list", data={"items": result.get("items", [])})]
    return events, result.get("text", ""), False, None
