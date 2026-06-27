import asyncio
import logging

from .config import config
from .llm_client import chat, model_for
from .thread_pools import llm_pool
from .token_counter import _get_encoder, count_message_tokens, count_tokens, get_context_limit

logger = logging.getLogger(__name__)

PROTECTED_TAIL_TOKENS = config.compaction.protected_tail_tokens
TAIL_TURNS_TO_KEEP = config.compaction.tail_turns_to_keep
COMPACTION_THRESHOLD_RATIO = config.compaction.threshold_ratio
MAX_TOOL_OUTPUT_TOKENS = config.compaction.max_tool_output_tokens
PRUNED_PLACEHOLDER = "[内容已省略 — 过长的工具输出已被裁剪以节省上下文]"

COMPACTION_SYSTEM = """你是对话历史压缩器。你的任务是将一段对话历史压缩为简洁的摘要。

规则：
1. **区分状态**：每条操作必须标注是 ✅已执行 还是 📋讨论中（未执行）
2. 保留所有关键事实：用户意图、已执行的操作及结果、重要结论
3. 保留实体名称、数字、ID 等精确信息
4. 如工具结果包含计数（如"新增3实体"），必须保留计数
5. 用要点列表格式输出
6. 不超过 500 字
7. 用中文输出"""


def _extract_tool_status(content: str, max_len: int = 120) -> str:
    """Extract the first meaningful line from a tool result as a status indicator."""
    lines = content.strip().split("\n")
    for line in lines[:3]:
        stripped = line.strip()
        if stripped and not stripped.startswith(("```", "{")):
            return stripped[:max_len]
    return content.strip()[:max_len]


def estimate_context_usage(messages: list[dict], model: str = None) -> tuple[int, int]:
    model = model or model_for("general")
    used = count_message_tokens(messages)
    limit = get_context_limit(model)
    return used, limit


def needs_compaction(messages: list[dict], model: str = None) -> bool:
    used, limit = estimate_context_usage(messages, model)
    return used > limit * COMPACTION_THRESHOLD_RATIO


def prune_tool_outputs(messages: list[dict]) -> tuple[list[dict], bool]:
    count_message_tokens(messages)

    tail_token_count = 0
    tail_start_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = count_tokens(messages[i].get("content", "") or "")
        tail_token_count += msg_tokens
        if tail_token_count >= PROTECTED_TAIL_TOKENS:
            tail_start_idx = i + 1
            break

    pruned = False
    result = []
    for i, msg in enumerate(messages):
        if i >= tail_start_idx:
            result.append(msg)
            continue

        if msg.get("role") == "tool":
            content = msg.get("content", "") or ""
            tokens = count_tokens(content)
            if tokens > MAX_TOOL_OUTPUT_TOKENS:
                new_msg = dict(msg)
                # Token-based truncation: encode → slice → decode
                encoder = _get_encoder()
                encoded = encoder.encode(content)
                truncated = encoder.decode(encoded[:MAX_TOOL_OUTPUT_TOKENS])
                new_msg["content"] = truncated + f"\n\n{PRUNED_PLACEHOLDER}"
                result.append(new_msg)
                pruned = True
                continue

        result.append(msg)

    return result, pruned


def compact_messages(messages: list[dict]) -> list[dict]:
    if not needs_compaction(messages):
        return messages

    messages, was_pruned = prune_tool_outputs(messages)
    if was_pruned and not needs_compaction(messages):
        return messages

    system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
    conversation = messages[1:] if system_msg else messages

    if len(conversation) <= TAIL_TURNS_TO_KEEP * 2:
        return messages

    cut_point = len(conversation) - (TAIL_TURNS_TO_KEEP * 2)
    cut_point = max(1, min(cut_point, len(conversation) - 1))

    # Walk backward to a safe cut that never splits an assistant-with-tool_calls
    # from its tool responses or from interleaved user hints / other messages.
    # Two rules:
    #   R1: to_keep must not start with a tool message (it would be orphan).
    #   R2: to_compact must not end with an assistant that has tool_calls
    #       (its tool responses live in to_keep and would become orphan).
    while cut_point > 0:
        if conversation[cut_point].get("role") == "tool":
            cut_point -= 1
            continue
        if (conversation[cut_point - 1].get("role") == "assistant"
                and conversation[cut_point - 1].get("tool_calls")):
            cut_point -= 1
            continue
        break

    if cut_point <= 0:
        logger.warning("Compaction: no safe cut point found, trying midpoint fallback")
        # Fallback: force-split at the midpoint as a last resort
        mid = max(1, len(conversation) // 2)
        # Ensure mid doesn't split assistant+tool pairs
        while mid > 0 and mid < len(conversation):
            if conversation[mid].get("role") == "tool":
                mid -= 1
                continue
            if (mid > 0 and conversation[mid - 1].get("role") == "assistant"
                    and conversation[mid - 1].get("tool_calls")):
                mid -= 1
                continue
            break
        if mid <= 0:
            return messages  # truly impossible, give up
        to_compact = conversation[:mid]
        to_keep = conversation[mid:]
        compact_text = _summarize_conversation(to_compact)
        result = []
        if system_msg:
            result.append(system_msg)
        result.append({
            "role": "system",
            "content": f"[对话历史摘要]\n{compact_text}\n[摘要结束 — 以下为最近对话]"
        })
        result.extend(to_keep)
        return result

    to_compact = conversation[:cut_point]
    to_keep = conversation[cut_point:]

    compact_text = _summarize_conversation(to_compact)

    result = []
    if system_msg:
        result.append(system_msg)
    result.append({
        "role": "system",
        "content": f"[对话历史摘要]\n{compact_text}\n[摘要结束 — 以下为最近对话]"
    })
    result.extend(to_keep)

    logger.info(f"Compaction: {count_message_tokens(messages)} → {count_message_tokens(result)} tokens")
    return result


def _summarize_conversation(messages: list[dict]) -> str:
    conversation_text = ""
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if role == "tool":
            tool_id = m.get("tool_call_id", "")
            status = _extract_tool_status(content)
            conversation_text += f"[工具结果 {tool_id[:8]}] ✅ {status}\n"
        elif role == "assistant":
            tool_calls = m.get("tool_calls", [])
            if tool_calls:
                tools_used = ", ".join(
                    tc.get("function", {}).get("name", tc.get("name", "?"))
                    if isinstance(tc, dict) else tc.name
                    for tc in tool_calls
                )
                conversation_text += f"[助手调用]: {tools_used}\n"
            if content:
                conversation_text += f"[助手]: {content[:200]}\n"
        elif role == "user":
            conversation_text += f"[用户]: {content[:200]}\n"

    if count_tokens(conversation_text) < 300:
        return conversation_text

    summary = chat(
        f"请压缩以下对话历史，每条操作标注 ✅已执行 或 📋仅讨论：\n\n{conversation_text[:8000]}",
        system=COMPACTION_SYSTEM,
        temperature=0.1,
        task="extraction"
    )
    return summary[:1500]


async def compact_messages_async(messages: list[dict]) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(llm_pool, compact_messages, messages)


async def handle_context_overflow(messages: list[dict]) -> tuple[list[dict], bool]:
    messages, pruned = prune_tool_outputs(messages)
    if not needs_compaction(messages):
        return messages, True

    result = await compact_messages_async(messages)
    if needs_compaction(result):
        # Overflow recovery: if compaction didn't
        # free enough, try a more aggressive prune that keeps only the
        # system message + summary + the very last user message + its
        # response. This is the "last resort" before telling the user to
        # start a new conversation.
        result = _aggressive_compact(result)
        if needs_compaction(result):
            return result, False
    return result, True


def _aggressive_compact(messages: list[dict]) -> list[dict]:
    """Last-resort compaction: keep only system + summary + last turn.

    Drops everything except the system message, the most recent compaction
    summary (if any), and the last user + assistant pair. This ensures the
    agent can at least respond to the current user message even if the
    full context history is too large to retain.
    """
    if not messages:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    [m for m in messages if m.get("role") == "tool"]

    # Find the last user message
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        # No user message — just keep system + first 3 messages
        return (system_msgs + messages[:3])[:5]

    # Keep: system + summary + last user message + everything after it
    # (which should be tool results / assistant response for the current turn)
    tail = messages[last_user_idx:]
    # If tail is still too large, keep only the user message
    from .token_counter import count_message_tokens
    if count_message_tokens(tail) > 4000:
        tail = [messages[last_user_idx]]

    # Sanitize: ensure no orphan tool messages in the tail
    result = (system_msgs[-1:] if system_msgs else []) + tail
    # Remove any tool messages that lost their assistant_tool_calls parent
    has_tc = any(
        m.get("role") == "assistant" and m.get("tool_calls")
        for m in result
    )
    if not has_tc:
        result = [m for m in result if m.get("role") != "tool"]

    return result
