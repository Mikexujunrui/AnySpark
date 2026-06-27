import asyncio
import json
import re

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.agent_loop import AgentConfig, LoopEvent, run_agent_loop
from core.compaction import compact_messages_async, needs_compaction
from core.config import DATA_DIR
from core.event_bus import Event, EventType, bus
from core.extractor import accept_proposal, extract_from_text, extract_stream
from core.graph_store import GraphStore, get_store
from core.question import manager as question_manager
from core.run_state import run_state
from core.task_queue import TaskStatus, task_queue
from core.writer import write_stream
from data.json_store import json_store
from tools.executor import get_executor

router = APIRouter(tags=["chat"])


# ── Autopilot Session Registry ──

_autopilot_sessions_file = DATA_DIR / "autopilot_sessions.json"

def _load_autopilot_sessions() -> dict[str, str]:
    try:
        if _autopilot_sessions_file.exists():
            return json.loads(_autopilot_sessions_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}

def _save_autopilot_sessions(sessions: dict[str, str]):
    try:
        _autopilot_sessions_file.write_text(
            json.dumps(sessions, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass

_active_autopilot_sessions: dict[str, str] = _load_autopilot_sessions()

def register_autopilot_session(session_id: str, task_id: str):
    _active_autopilot_sessions[session_id] = task_id
    _save_autopilot_sessions(_active_autopilot_sessions)

def unregister_autopilot_session(session_id: str):
    if _active_autopilot_sessions.pop(session_id, None) is not None:
        _save_autopilot_sessions(_active_autopilot_sessions)

def get_active_autopilot(session_id: str) -> str | None:
    """Return the active autopilot task_id for this session, or None.
    Automatically cleans up stale registrations."""
    task_id = _active_autopilot_sessions.get(session_id)
    if task_id:
        task = task_queue.get_task(task_id)
        if task and task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.PENDING):
            return task_id
        _active_autopilot_sessions.pop(session_id, None)
    return None


# ── Intervention Patterns ──

INTERVENTION_PATTERNS = [
    (r"暂停|停一下|等一下|pause", "pause"),
    (r"取消|停止|算了|cancel", "cancel"),
    (r"跳过.{0,5}章|跳过当前|skip", "skip_chapter"),
    (r"改.{0,10}(风格|激烈|温柔|节奏|紧凑|舒缓)", "modify_instruction"),
    (r"(第?\d+章).{0,20}(改|调整|修改|重做)", "modify_chapter"),
]

def classify_intervention(msg: str) -> tuple[str, dict]:
    """Classify if a message is an autopilot intervention."""
    for pattern, action in INTERVENTION_PATTERNS:
        if re.search(pattern, msg):
            return action, {}
    return "chat_overlay", {}


class MessageRequest(BaseModel):
    message: str
    book_id: str
    mode: str = "write"
    session_id: str = ""
    auto_mode_enabled: bool = False  # 机器人开关，控制 Autopilot 可见性


class ReplyRequest(BaseModel):
    answers: list[list[str]] = [["确认"]]


class WriteRequest(BaseModel):
    instruction: str = ""
    book_id: str = ""
    mode: str = "strict"




@router.post("/books/{book_id}/questions/{qid}/reply")
async def reply_question(book_id: str, qid: str, data: ReplyRequest):
    from fastapi import HTTPException
    answers = data.answers
    ok = question_manager.reply(qid, answers)
    if not ok:
        raise HTTPException(404, "提问不存在或已回复")
    return {"ok": True}


@router.post("/books/{book_id}/questions/{qid}/reject")
async def reject_question(book_id: str, qid: str):
    from fastapi import HTTPException
    ok = question_manager.reject(qid)
    if not ok:
        raise HTTPException(404, "提问不存在或已回复")
    return {"ok": True}


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    cancelled = await run_state.cancel(session_id)
    return {"ok": cancelled, "message": "已取消" if cancelled else "无活跃任务"}


@router.get("/sessions/{session_id}/status")
async def session_status(session_id: str):
    busy = run_state.is_busy(session_id)
    return {"busy": busy, "session_id": session_id}


@router.post("/chat")
async def chat_with_agent(req: MessageRequest):
    msg = req.message.strip()

    # ── 会话自动命名：首条非斜杠命令消息自动成为会话标题 ──
    if req.session_id and not msg.startswith("/") and not msg.startswith("#"):
        try:
            sessions = json_store.load_sessions(req.book_id)
            session = next((s for s in sessions if s["id"] == req.session_id), None)
            if session:
                title = session.get("title", "")
                # Only rename if title matches default pattern: "会话 N" or "默认会话"
                import re
                if re.match(r"^(会话\s*\d*|默认会话)$", title):
                    new_title = msg[:30] + ("…" if len(msg) > 30 else "")
                    json_store.update_session(req.book_id, req.session_id, {"title": new_title})
        except Exception:
            pass

    # ── Autopilot intervention detection ──
    session_key = req.session_id or req.book_id
    active_task_id = get_active_autopilot(session_key)
    if active_task_id:
        action, _ = classify_intervention(msg)
        if action != "chat_overlay":
            return EventSourceResponse(_handle_intervention(msg, req, active_task_id, action))

    if msg == "/" or msg == "/help":
        return _slash_help(req)

    if msg.startswith("/skills"):
        return _list_skills(req)

    if msg.startswith("/style"):
        return _style_cmd(req, msg)

    if msg.startswith("/s "):
        if req.mode == "plan":
            return {"type": "error", "message": "提取设定需要 Write 模式。"}
        kb = get_store(req.book_id)
        return EventSourceResponse(_extract_shortcut(msg[3:], kb, req.book_id, req.session_id, msg))

    if msg.startswith("/w ") or msg.startswith("/ws "):
        if req.mode == "plan":
            return {"type": "error", "message": "写作需要 Write 模式。"}
        mode = "strict" if msg.startswith("/w ") else "suggest"
        instruction = msg[3:] if msg.startswith("/w ") else msg[4:]
        return EventSourceResponse(_write_shortcut(instruction, mode, req.book_id, req.session_id, msg))

    # ── Flash 快捷路由：仅高确定性的生成类意图 ──
    intent, _ = await _classify_intent(msg)

    if intent == "generate_outline":
        return EventSourceResponse(_tool_shortcut("generate_outline", {}, req, msg))
    elif intent == "generate_detailed_outline":
        return EventSourceResponse(_tool_shortcut("generate_detailed_outline", {}, req, msg))
    elif intent == "generate_worldbuilding":
        return EventSourceResponse(_tool_shortcut("generate_worldbuilding", {}, req, msg))
    elif intent == "generate_timeline":
        return EventSourceResponse(_tool_shortcut("generate_timeline", {}, req, msg))

    return EventSourceResponse(_agent_loop_sse(msg, req))


INTENT_CLASSIFY_SYSTEM = """你是小说写作助手的意图分类器。仅分类以下意图之一：

- generate_outline: 用户想生成全书大纲（如"生成大纲"、"创建大纲"、"大纲"）
- generate_detailed_outline: 用户想生成细纲/剧情骨架（如"细纲"、"剧情骨架"）
- generate_worldbuilding: 用户想生成世界观（如"生成世界观"、"创建世界观"）
- generate_timeline: 用户想生成时间线（如"生成时间线"、"创建时间线"）
- general: 以上都不匹配（包括写作、评审、提取设定、管理评审员等——全部归为 general）

输出格式（严格JSON，别无其他内容）:
{"intent": "类别", "args": {}}

只输出 JSON，不要加 markdown 代码块。"""


async def _classify_intent(msg: str) -> tuple[str, dict]:
    import asyncio
    import json

    from core.llm_client import MODELS, get_client
    from tools.executor import get_executor

    loop = asyncio.get_running_loop()

    def _call():
        client = get_client()
        r = client.chat.completions.create(
            model=MODELS["flash"],
            messages=[
                {"role": "system", "content": INTENT_CLASSIFY_SYSTEM},
                {"role": "user", "content": msg[:400]},
            ],
            temperature=0.0,
            max_tokens=50,
        )
        return r.choices[0].message.content or ""

    raw = await loop.run_in_executor(get_executor(), _call)
    try:
        result = json.loads(raw.strip())
        return result.get("intent", "general"), result.get("args", {})
    except json.JSONDecodeError:
        return "general", {}


async def _tool_shortcut(tool_name: str, extra_args: dict, req, original_msg: str):
    import asyncio

    from tools.executor import execute_tool_streaming

    kb = GraphStore(req.book_id)
    kb.init_schema()
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    async def _run():
        result = await execute_tool_streaming(
            loop, tool_name, extra_args, kb, req.book_id,
            original_msg, req.session_id, queue)
        await queue.put(result)
        await queue.put(None)

    task = asyncio.create_task(_run())

    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, dict) and item.get("_progress"):
            yield {"event": "progress", "data": json.dumps(
                {"stage": item["_progress"]}, ensure_ascii=False)}
        else:
            content = str(item) if item else "完成"
            _persist_turn(req.book_id, req.session_id, original_msg, content[:500], mode=req.mode)
            yield {"event": "done", "data": json.dumps(
                {"message": content}, ensure_ascii=False)}
            return

    await task


def _slash_help(req: MessageRequest) -> dict:
    from core.scheduler import TASK_TEMPLATES
    from core.skills import manager as skill_manager

    commands = [
        {"cmd": "/s <内容>", "desc": "强制提取设定（从内容中识别实体/关系/伏笔）"},
        {"cmd": "/w <指令>", "desc": "强制写作——严格模式下只使用已有知识库（Write模式）"},
        {"cmd": "/ws <指令>", "desc": "宽松写作——AI可补充细节但标记待确认"},
        {"cmd": "/help", "desc": "显示此帮助"},
        {"cmd": "/skills", "desc": "列出所有可用技能（预定义写作工作流）"},
    ]

    skills = skill_manager.list_skills()
    skill_items = [f"  **/{sk['name']}** — {sk['description']}" for sk in skills]

    templates = list(TASK_TEMPLATES.keys())
    template_items = [f"  - `{t}`" for t in templates]

    lines = [
        "## 可用斜杠命令\n",
        "| 命令 | 说明 |",
        "|------|------|",
    ]
    for c in commands:
        lines.append(f"| `{c['cmd']}` | {c['desc']} |")

    if skill_items:
        lines.append("\n### 技能（可直接用 /技能名 调用）")
        lines.extend(skill_items)

    lines.append("\n### 调度器任务模板（通过API创建定时任务）")
    lines.extend(template_items)

    lines.append("\n---")
    lines.append("💡 也可以直接用自然语言描述需求，Agent 会自动分类并选择合适的处理方式。")

    return {"type": "text", "message": "\n".join(lines)}


def _list_skills(req: MessageRequest) -> dict:
    from core.skills import manager as skill_manager
    skills = skill_manager.list_skills()
    if not skills:
        return {"type": "text", "message": "暂无可用技能。可在 skills/ 目录下添加 YAML 定义。"}
    lines = ["## 可用技能\n"]
    for sk in skills:
        lines.append(f"**/{sk['name']}**")
        lines.append(f"  {sk['description']}")
        steps = sk.get("steps", [])
        if steps:
            step_names = " → ".join(s.get("label", s.get("tool", "")) for s in steps)
            lines.append(f"  步骤: {step_names}")
        lines.append("")
    return {"type": "text", "message": "\n".join(lines)}


def _style_cmd(req: MessageRequest, msg: str) -> dict:
    from core.styles import manager as style_manager
    parts = msg.split(maxsplit=1)
    if len(parts) >= 2:
        name = parts[1].strip()
        style = style_manager.get(name)
        if style:
            from tools.executor import _set_style
            result = _set_style({"name": name})
            return {"type": "text", "message": result}
        else:
            names = ", ".join(s["name"] for s in style_manager.list_styles())
            return {"type": "text", "message": f"未知风格: {name}。可用: {names}"}
    else:
        styles = style_manager.list_styles()
        lines = ["## 可用写作风格\n"]
        for s in styles:
            lines.append(f"**{s['name']}** — {s['description']}")
            lines.append(f"  适用: {', '.join(s['applies_to'])}")
            lines.append("")
        lines.append("输入 `/style 风格名` 切换风格")
        return {"type": "text", "message": "\n".join(lines)}


async def _agent_loop_sse(msg: str, req: MessageRequest):
    history_msgs = _load_history_as_llm_messages(req.session_id) if req.session_id else []

    if history_msgs and needs_compaction([{"role": "system", "content": ""}] + history_msgs):
        compacted = await compact_messages_async([{"role": "system", "content": ""}] + history_msgs)
        history_msgs = [m for m in compacted if m.get("role") != "system"]

    extra_context = ""
    if len(msg) > 2000:
        loop = asyncio.get_running_loop()
        extra_context = await loop.run_in_executor(None, _classify_long_content, msg)

    agent_config = AgentConfig(
        agent_type="write" if req.mode == "write" else "plan",
        mode=req.mode,
        book_id=req.book_id,
        session_id=req.session_id or req.book_id,
        extra_context=extra_context,
        auto_mode_enabled=req.auto_mode_enabled,
    )

    final_text = ""
    turn_parts = None
    did_yield_done = False

    async for event in run_agent_loop(msg, agent_config, history_msgs):
        sse_event = _map_loop_event_to_sse(event)
        if sse_event:
            yield sse_event
            if sse_event.get("event") == "done":
                did_yield_done = True

        if event.type == "done":
            final_text = event.data.get("message", "")
            # Parts collected by the loop (full tool-call/result/chapter-diff/
            # reasoning history) — persisted so the session can be replayed.
            turn_parts = event.data.get("parts")
        elif event.type == "text" and not final_text:
            final_text = event.data.get("content", "")
        elif event.type == "error":
            final_text = event.data.get("message", "处理出错")

    # Fallback: if loop ended without a done event, send one now so the
    # frontend never silently hangs. This can happen if the LLM provider
    # hangs or the loop exits abnormally.
    if not did_yield_done:
        fallback_msg = final_text or "Agent 循环异常终止，但未收到最终的完成信号。请检查后端日志获取详细信息，或尝试重新发送消息。"
        yield {"event": "done", "data": json.dumps(
            {"message": fallback_msg}, ensure_ascii=False)}

    if final_text:
        _persist_turn(req.book_id, req.session_id, msg, final_text,
                      mode=req.mode, parts=turn_parts)


def _map_loop_event_to_sse(event: LoopEvent) -> dict | None:
    t = event.type
    d = event.data

    if t == "start":
        return {"event": "progress", "data": json.dumps(
            {"stage": "Agent 启动", "detail": f"{d.get('agent')} 模式, {d.get('tools_count')} 个工具"},
            ensure_ascii=False)}

    elif t == "thinking":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"思考中... (轮次 {d.get('round', '?')})"},
            ensure_ascii=False)}

    elif t == "compaction":
        return {"event": "progress", "data": json.dumps(
            {"stage": d.get("stage", "压缩中")},
            ensure_ascii=False)}

    elif t == "retry":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"重试中 ({d.get('attempt')}/{3})", "detail": d.get("error", "")[:80]},
            ensure_ascii=False)}

    elif t == "tool-start":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"调用: {d.get('tool')}", "detail": d.get("args", "")[:80]},
            ensure_ascii=False)}

    elif t == "tool-end":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"{d.get('tool')} 完成", "detail": d.get("result_preview", "")[:100]},
            ensure_ascii=False)}

    elif t == "tool-error":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"工具错误: {d.get('tool')}", "detail": d.get("error", "")[:100]},
            ensure_ascii=False)}

    elif t == "doom-loop":
        return {"event": "progress", "data": json.dumps(
            {"stage": "检测到重复调用", "detail": d.get("message", "")[:100]},
            ensure_ascii=False)}

    elif t == "chunk":
        return {"event": "chunk", "data": d.get("text", "")}

    elif t == "text":
        # Text events contain hallucination corrections or final responses
        # when no streaming chunks were sent. Show them as chunks so the
        # frontend can display them. Note: this won't cause double-streaming
        # because "text" events are only yielded when no chunks were streamed.
        text_content = d.get("content", "")
        if text_content:
            return {"event": "chunk", "data": text_content}
        return None

    elif t == "text-correction":
        # Hallucination correction messages should also be visible
        text_content = d.get("content", "")
        if text_content:
            return {"event": "chunk", "data": text_content}
        return None

    elif t == "question":
        return {"event": "question", "data": json.dumps(
            {"id": d.get("id", ""), "questions": d.get("questions", [])},
            ensure_ascii=False)}

    elif t == "plot_cards":
        return {"event": "plot_cards", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "permission-denied":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"权限拒绝: {d.get('tool')}"},
            ensure_ascii=False)}

    elif t == "permission-granted":
        return {"event": "progress", "data": json.dumps(
            {"stage": f"权限已确认: {d.get('tool')}"},
            ensure_ascii=False)}

    elif t == "done":
        return {"event": "done", "data": json.dumps(
            {"message": d.get("message", "完成")},
            ensure_ascii=False)}

    elif t == "error":
        return {"event": "done", "data": json.dumps(
            {"message": d.get("message", "处理出错")},
            ensure_ascii=False)}

    elif t == "cancelled":
        return {"event": "done", "data": json.dumps(
            {"message": "操作已取消"},
            ensure_ascii=False)}

    elif t == "writing":
        return {"event": "writing", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "task_list":
        return {"event": "task_list", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "writing_end":
        return {"event": "writing_end", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "workflow":
        return {"event": "workflow", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "patch_result":
        return {"event": "patch_result", "data": json.dumps(d, ensure_ascii=False)}

    elif t == "chapter_updated":
        return {"event": "chapter_updated", "data": json.dumps(d, ensure_ascii=False)}

    return None


def _classify_long_content(msg: str) -> str:
    from core.agent import classify_content
    try:
        classification = classify_content(msg)
    except Exception:
        return ""

    content_type = classification.get("type", "instruction")
    hints = {
        "setting_document": "用户提交了设定文档，应使用 extract_knowledge 提取。",
        "novel_chapter": "用户提交了章节正文，应 store_chapter 存储。",
        "story_fragment": "用户提交了故事片段，可 store_inspiration 保存。",
        "inspiration_note": "用户提交了灵感笔记，用 store_inspiration 保存。",
    }
    return hints.get(content_type, "")


def _load_history_as_llm_messages(session_id: str, max_turns: int = 20) -> list[dict]:
    """Load conversation history as flat OpenAI-format messages.

    History is persisted as structured ``Turn`` records (with parts). We
    reconstruct the flat message list from those parts. Legacy messages
    (no ``parts`` field) fall back to ``{role, text}``.

    Reasoning parts are deliberately excluded from the replayed messages —
    for a writing assistant the model's explicit output matters more than its
    internal chain-of-thought, and omitting it saves tokens.
    """
    from core.parts import turns_from_history, turns_to_llm_messages

    history = json_store.load_messages(session_id)
    if not history:
        return []
    turns = turns_from_history(history[-(max_turns * 2):])
    return turns_to_llm_messages(turns)


def _persist_turn(book_id: str, session_id: str, user_text: str, agent_text: str,
                  mode: str = "", parts: list | None = None):
    if not session_id:
        return
    from datetime import datetime

    from core.book_locks import book_lock
    ts = datetime.now().strftime("%H:%M")
    with book_lock(session_id):
        history = json_store.load_messages(session_id)
        history.append({"role": "user", "text": user_text, "ts": ts, "mode": mode})
        agent_record = {"role": "agent", "text": agent_text, "ts": ts, "mode": mode}
        if parts is not None:
            agent_record["parts"] = parts
            agent_record["user_text"] = user_text
            agent_record["final_text"] = agent_text
        history.append(agent_record)
        json_store.save_messages(book_id, session_id, history)


async def _extract_shortcut(text: str, kb, book_id: str, session_id: str = "", original_msg: str = ""):
    executor = get_executor()
    yield {"event": "progress", "data": json.dumps({"stage": "准备中...", "detail": "加载知识库"}, ensure_ascii=False)}
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run():
        try:
            for e in extract_stream(text, existing_knowledge=kb.get_knowledge_summary(), book_id=book_id):
                q.put_nowait(e)
        finally:
            q.put_nowait(None)

    loop.run_in_executor(executor, run)

    while True:
        evt = await q.get()
        if evt is None:
            break
        yield {"event": evt["event"], "data": json.dumps(evt["data"], ensure_ascii=False)}
        if evt["event"] == "result":
            yield {"event": "progress", "data": json.dumps({"stage": "正在保存...", "detail": "入库图数据库"}, ensure_ascii=False)}
            proposal = await loop.run_in_executor(executor, extract_from_text, text, "", book_id)
            result = await loop.run_in_executor(executor, accept_proposal, proposal, book_id)
            entities = kb.list_entities()
            json_store.update_book_stats(book_id, entity_count=len(entities))
            done_msg = f"{result}\n实体: {len(proposal.entities)} | 关系: {len(proposal.relations)} | 伏笔: {len(proposal.foreshadows)}"
            _persist_turn(book_id, session_id, original_msg, done_msg, mode="write")
            yield {"event": "done", "data": json.dumps({
                "message": result,
                "totalEntities": len(proposal.entities),
                "totalRelations": len(proposal.relations),
                "totalForeshadows": len(proposal.foreshadows)
            }, ensure_ascii=False)}
            break


async def _write_shortcut(instruction: str, mode: str, book_id: str, session_id: str = "", original_msg: str = ""):
    executor = get_executor()
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()
    full_text = []

    def run():
        try:
            for chunk in write_stream(instruction, mode=mode, project_id=book_id):
                q.put_nowait(chunk)
        finally:
            q.put_nowait(None)

    loop.run_in_executor(executor, run)
    while True:
        chunk = await q.get()
        if chunk is None:
            break
        full_text.append(chunk)
        yield {"event": "chunk", "data": chunk}

    _persist_turn(book_id, session_id, original_msg, "".join(full_text), mode="write")


@router.post("/write")
def write_text(data: WriteRequest):
    instruction = data.instruction
    book_id = data.book_id
    mode = data.mode

    async def event_generator():
        executor = get_executor()
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def run():
            try:
                for chunk in write_stream(instruction, mode=mode, project_id=book_id):
                    q.put_nowait(chunk)
            finally:
                q.put_nowait(None)

        loop.run_in_executor(executor, run)
        while True:
            chunk = await q.get()
            if chunk is None:
                break
            yield {"event": "chunk", "data": chunk}

    return EventSourceResponse(event_generator())


# ── Autopilot Intervention Handler ──

async def _handle_intervention(msg: str, req: MessageRequest, task_id: str, action: str):
    """Handle an autopilot intervention message without creating a new agent_loop."""
    from core.autopilot_runner import autopilot

    async def event_generator():
        if action == "pause":
            ok = await autopilot.pause(task_id)
            yield {"event": "done", "data": json.dumps(
                {"message": "⏸ Autopilot 已暂停" if ok else "暂停失败"}, ensure_ascii=False)}
        elif action == "cancel":
            ok = await autopilot.cancel(task_id)
            unregister_autopilot_session(req.session_id or req.book_id)
            yield {"event": "done", "data": json.dumps(
                {"message": "🚫 Autopilot 已取消" if ok else "取消失败"}, ensure_ascii=False)}
        elif action == "skip_chapter":
            from core.headless_loop import get_task_runner
            runner = get_task_runner()
            if runner:
                ok = await runner.request_skip(task_id)
            else:
                ok = False
            yield {"event": "done", "data": json.dumps(
                {"message": "⏭ 已跳过当前步骤" if ok else "跳过失败：任务未运行"}, ensure_ascii=False)}
        elif action in ("modify_instruction", "modify_chapter"):
            # Inject as context overlay for the next step
            from core.headless_loop import get_task_runner
            runner = get_task_runner()
            if runner:
                acc = runner._accumulators.get(task_id)
                if acc:
                    # Use a special record to inject the intervention
                    acc._intervention_queue = getattr(acc, '_intervention_queue', [])
                    acc._intervention_queue.append(msg)
            yield {"event": "done", "data": json.dumps(
                {"message": f"📨 干预指令已注入，将在下一步生效：{msg[:50]}..." if len(msg) > 50 else f"📨 干预指令已注入：{msg}"}, ensure_ascii=False)}
        else:
            yield {"event": "done", "data": json.dumps(
                {"message": "已收到消息，将在 autopilot 下一步中处理"}, ensure_ascii=False)}

        # Persist the intervention turn
        if req.session_id:
            _persist_turn(req.book_id, req.session_id, msg,
                          f"[autopilot 干预] {action}", mode=req.mode)

    return EventSourceResponse(event_generator())


# ── Autopilot Bridge SSE ──

async def _autopilot_bridge_sse(task_id: str, book_id: str, session_id: str):
    """Bridge autopilot event_bus events into chat-compatible SSE stream."""
    event_queue = asyncio.Queue()

    async def _listener(event: Event):
        if event.data.get("task_id") == task_id:
            await event_queue.put(event)

    bus.on(EventType.TASK_STEP_COMPLETED, _listener)
    bus.on(EventType.TASK_STEP_FAILED, _listener)
    bus.on(EventType.TASK_COMPLETED, _listener)
    bus.on(EventType.TASK_FAILED, _listener)
    bus.on(EventType.TASK_NOTIFICATION, _listener)
    bus.on(EventType.HEADLESS_LOOP_PROGRESS, _listener)

    try:
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=30)
            except TimeoutError:
                yield {"event": "heartbeat", "data": json.dumps({"task_id": task_id}, ensure_ascii=False)}
                continue

            sse = _map_autopilot_event(event)
            if sse:
                yield sse

            if event.type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED):
                # Persist completion message
                if session_id:
                    msg_text = ""
                    if event.type == EventType.TASK_COMPLETED:
                        progress = event.data.get("progress", {})
                        msg_text = f"🎉 Autopilot 完成！共 {progress.get('completed', '?')} 个步骤"
                    else:
                        msg_text = f"❌ Autopilot 失败: {event.data.get('error', '未知错误')[:200]}"
                    if msg_text:
                        _persist_turn(book_id, session_id, "[autopilot]", msg_text, mode="write")
                # Clean up registration
                unregister_autopilot_session(session_id)
                return
    finally:
        bus.off(EventType.TASK_STEP_COMPLETED, _listener)
        bus.off(EventType.TASK_STEP_FAILED, _listener)
        bus.off(EventType.TASK_COMPLETED, _listener)
        bus.off(EventType.TASK_FAILED, _listener)
        bus.off(EventType.TASK_NOTIFICATION, _listener)
        bus.off(EventType.HEADLESS_LOOP_PROGRESS, _listener)


def _map_autopilot_event(event: Event) -> dict | None:
    """Map an autopilot event_bus event to chat-compatible SSE format."""
    data = event.data

    if event.type == EventType.TASK_STEP_COMPLETED:
        return {
            "event": "autopilot_step",
            "data": json.dumps({
                "step_id": data.get("step_id"),
                "step_label": data.get("step_label"),
                "result_summary": str(data.get("result", {}))[:200],
                "progress": data.get("progress"),
            }, ensure_ascii=False),
        }
    elif event.type == EventType.TASK_STEP_FAILED:
        return {
            "event": "autopilot_error",
            "data": json.dumps({
                "step_id": data.get("step_id"),
                "step_label": data.get("step_label"),
                "error": data.get("error", ""),
            }, ensure_ascii=False),
        }
    elif event.type == EventType.TASK_COMPLETED:
        return {
            "event": "autopilot_done",
            "data": json.dumps({
                "summary": f"共 {data.get('progress', {}).get('completed', '?')} 个步骤完成",
                "progress": data.get("progress", {}),
            }, ensure_ascii=False),
        }
    elif event.type == EventType.TASK_FAILED:
        return {
            "event": "autopilot_failed",
            "data": json.dumps({"error": data.get("error", "未知错误")}, ensure_ascii=False),
        }
    elif event.type == EventType.TASK_NOTIFICATION:
        return {
            "event": "autopilot_notify",
            "data": json.dumps({
                "message": data.get("message", ""),
                "action_required": data.get("action_required", False),
            }, ensure_ascii=False),
        }
    elif event.type == EventType.HEADLESS_LOOP_PROGRESS:
        stage = data.get("stage", "")
        event_type = data.get("event_type", "")
        if event_type == "chunk":
            return {"event": "chunk", "data": data.get("text", "")}
        elif event_type in ("tool-start", "tool-end", "progress"):
            return {
                "event": "autopilot_progress",
                "data": json.dumps({
                    "stage": stage or event_type,
                    "detail": str(data.get("tool", data.get("text", "")))[:100],
                }, ensure_ascii=False),
            }

    return None
