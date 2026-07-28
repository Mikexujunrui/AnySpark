import logging
import uuid
from dataclasses import dataclass, field

from .agent_loop import AgentConfig, run_agent_loop
from .config import config

logger = logging.getLogger(__name__)

AGENT_TYPES = {
    "general": {
        "description": "通用助手，处理复杂多步任务",
        "mode": "write",
        "agent_type": "general",
        "task_label": "general",
    },
    "extract": {
        "description": "知识提取专家，从文本中提取结构化知识",
        "mode": "write",
        "agent_type": "extract",
        "temperature": 0.1,
        "task_label": "extraction",
    },
    "plan": {
        "description": "只读分析助手，检索和分析知识库数据",
        "mode": "plan",
        "agent_type": "plan",
        "task_label": "planning",
    },
    "write": {
        "description": "写作助手，执行写作相关操作",
        "mode": "write",
        "agent_type": "write",
        "temperature": 0.3,
        "task_label": "writing",
    },
    "edit": {
        "description": "编辑助手，拆解章节/分析风格/复写章节",
        "mode": "write",
        "agent_type": "edit",
        "temperature": 0.3,
        "task_label": "editing",
    },
    "consistency": {
        "description": "一致性校验助手，检测知识库矛盾",
        "mode": "plan",
        "agent_type": "consistency",
        "temperature": 0.1,
        "task_label": "extraction",
    },
    "reviewer": {
        "description": "评审团评审助手，从多个角色视角评审章节质量",
        "mode": "plan",
        "agent_type": "reviewer",
        "temperature": 0.3,
        "task_label": "review",
    },
    "research": {
        "description": "联网调研助手，搜索外部资料辅助写作",
        "mode": "plan",
        "agent_type": "research",
        "temperature": 0.2,
        "task_label": "research",
    },
}


@dataclass
class SubAgentResult:
    success: bool = True
    output: str = ""
    rounds: int = 0
    error: str = ""
    session_id: str = ""


@dataclass
class SubAgentSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_type: str = "general"
    parent_session_id: str = ""
    messages_history: list[dict] = field(default_factory=list)


_sub_sessions: dict[str, SubAgentSession] = {}


async def spawn_sub_agent(
    prompt: str,
    agent_type: str = "general",
    book_id: str = "",
    parent_session_id: str = "",
    task_id: str | None = None,
) -> SubAgentResult:

    from core.permissions import permission_manager

    # Isolate sub-agent permissions: save parent's approved set, reset for
    # the sub-agent, restore when done. This prevents sub-agents from
    # inheriting parent's sensitive approvals (e.g. delete_entity).
    parent_approved = permission_manager._session_approved.copy()
    permission_manager.reset_session()

    session = None
    try:
        agent_def = AGENT_TYPES.get(agent_type, AGENT_TYPES["general"])

        if task_id and task_id in _sub_sessions:
            session = _sub_sessions[task_id]
        else:
            session = SubAgentSession(
                agent_type=agent_type,
                parent_session_id=parent_session_id,
            )
            _sub_sessions[session.id] = session

        sub_config = AgentConfig(
            agent_type=agent_def["agent_type"],
            mode=agent_def["mode"],
            book_id=book_id,
            session_id=f"sub_{session.id}",
            max_rounds=agent_def.get("max_rounds", config.agent.max_rounds),
            temperature=agent_def.get("temperature", config.agent.default_temperature),
            task_description=prompt[:200],
        )

        collected_text = []
        tool_summary = []  # Track intermediate tool calls for history
        rounds = 0

        async for event in run_agent_loop(prompt, sub_config, session.messages_history):
            if event.type == "text":
                collected_text.append(event.data.get("content", ""))
            elif event.type == "done":
                rounds = event.data.get("rounds", 0)
                msg = event.data.get("message", "")
                if msg and msg not in collected_text:
                    collected_text.append(msg)
            elif event.type == "error":
                return SubAgentResult(
                    success=False,
                    error=event.data.get("message", "sub-agent error"),
                    session_id=session.id,
                )
            elif event.type == "tool-end":
                # Capture tool call info for history preservation
                tool_name = event.data.get("tool", "")
                result_preview = event.data.get("result_preview", "")[:200]
                if tool_name:
                    tool_summary.append(f"[{tool_name}] {result_preview}")

        # Store user prompt + intermediate tool context + assistant output
        session.messages_history.append({"role": "user", "content": prompt})
        if tool_summary:
            session.messages_history.append(
                {
                    "role": "assistant",
                    "content": f"（执行过程摘要：调用了 {len(tool_summary)} 个工具）\n"
                    + "\n".join(tool_summary[:20]),  # limit to 20 entries
                }
            )
        output = "\n".join(collected_text) if collected_text else "子任务完成（无文本输出）"
        session.messages_history.append({"role": "assistant", "content": output})

        return SubAgentResult(
            success=True,
            output=output,
            rounds=rounds,
            session_id=session.id,
        )
    finally:
        # Restore parent permissions regardless of sub-agent outcome
        permission_manager._session_approved = parent_approved
        # Clean up sub-session to prevent memory leak
        cleanup_id = task_id if task_id and task_id in _sub_sessions else (session.id if session else None)
        if cleanup_id:
            cleanup_sub_session(cleanup_id)


def get_available_agents_description() -> str:
    lines = []
    for name, info in AGENT_TYPES.items():
        lines.append(f"- {name}: {info['description']}")
    return "\n".join(lines)


def cleanup_sub_session(session_id: str):
    _sub_sessions.pop(session_id, None)
