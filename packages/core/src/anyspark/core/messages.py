"""
anyspark.core.messages — 消息序列质量守卫（模型无关，多协议共享）。

核心价值：把"工具调用配对完整"这个不变量做在**消息层（core Message）**，
各协议适配器（openai/anthropic/gemini/responses）转换前统一调用一次，
保证传给任何厂商的序列都不存在"工具结果无声明 / 声明无结果"的残缺配对。

设计（S190 讨论定案，向 pi 对齐）：
- 输入侧不变量：任何路径产生的消息都必须配对完整（写入守卫在存储层 replace），
  转换层只需忠实映射。本函数是转换层的**通用兜底**——覆盖绕开存储直接构造
  消息的路径（内部管道、未来协议、第三方），并给此前完全没有防御的
  OpenAI 兼容适配器补齐同等保障。
- 纯函数、幂等、模型无关：不改输入（返回新列表），无副作用，不查数据库。
  正常配对的干净输入原样返回（零行为变化）。
- 这是"宽松配对"（允许 tool 结果与声明被 user 插话隔开）；各协议特有的
  "严格紧邻"（Anthropic 要求 tool_result 紧跟 tool_use）由适配器各自的
  转换防御保留——本守卫负责"无孤儿/无悬挂"这个通用层面。
"""

from __future__ import annotations

from collections import deque

from .types import Message


def _declared_ids(m: Message) -> list[str]:
    """assistant 消息声明的 tool_call id（空串 / 非法项忽略）。"""
    calls = m.metadata.get("tool_calls")
    if not isinstance(calls, list):
        return []
    ids: list[str] = []
    for tc in calls:
        if isinstance(tc, dict) and tc.get("id"):
            ids.append(str(tc["id"]))
    return ids


def _strip_dangling(m: Message, dangling: set[str]) -> Message:
    """裁剪 assistant 消息中无配对结果的悬挂工具声明（返回新 Message）。"""
    calls = m.metadata.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        return m
    kept = [tc for tc in calls if isinstance(tc, dict) and str(tc.get("id") or "") not in dangling]
    if len(kept) == len(calls):
        return m
    md = dict(m.metadata)
    if kept:
        md["tool_calls"] = kept
    else:
        md.pop("tool_calls", None)
    return Message(role=m.role, content=m.content, metadata=md)


def sanitize_tool_pairing(messages: list[Message]) -> list[Message]:
    """模型无关的通用配对守卫（纯函数、幂等，返回新列表）。

    处理三类残缺配对：
    - **孤儿工具结果**：tool 消息的 tool_call_id 无对应 assistant 声明 → 移除
    - **悬挂工具声明**：assistant 声明的 tool_call_id 无对应 tool 结果 → 从声明裁剪
    - **缺 id 的工具结果**：tool 消息缺 tool_call_id → 用相邻未配对声明补配，
      补不上（队列空）则移除

    S201：额外处理「被 user 插话隔开的配对」——OpenAI 严格模式要求 assistant
    tool_calls 声明后**必须紧跟一整组 tool 消息**（中间不可插 user/system）。
    steer/followup 插话、队列接力若把 user 落在声明与 tool 结果之间，
    原样发给 API 会 400（insufficient tool messages following tool_calls）。
    处理：把插在声明↔tool 结果之间的非 tool 消息**推迟到该组 tool 结果之后**
    （保序、保内容，只调位置）。
    """
    out: list[Message] = []
    declared: deque[str] = deque()
    # S201：声明组待回填的 tool 数（当前未闭合的声明集合大小）——
    # 在这个窗口内出现的非 tool 消息先暂存，等 tool 组闭合后插回。
    pending_defer: list[Message] = []
    open_decls: set[str] = set()
    for m in messages:
        if m.role == "assistant":
            out.append(m)
            for tid in _declared_ids(m):
                declared.append(tid)
                open_decls.add(tid)
        elif m.role == "tool":
            tid = str(m.metadata.get("tool_call_id") or "")
            if tid:
                if tid in declared:
                    declared.remove(tid)
                    open_decls.discard(tid)
                    out.append(m)
                    # 该组闭合：把暂存的其他角色消息插回（保持插话语义）
                    if not open_decls:
                        out.extend(pending_defer)
                        pending_defer.clear()
                # 无对应声明 → 孤儿，丢弃
                elif tid in open_decls:
                    # 声明在但已配对过（多结果同声明异常）——忽略防重
                    pass
            elif declared:
                # 缺 id：从相邻未配对声明补配（保持声明→tool 顺序）
                md = dict(m.metadata)
                mdid = declared.popleft()
                md["tool_call_id"] = mdid
                open_decls.discard(mdid)
                out.append(Message(role=m.role, content=m.content, metadata=md))
                if not open_decls:
                    out.extend(pending_defer)
                    pending_defer.clear()
            # 队列空且无 id → 孤儿，丢弃
        else:
            # S201：声明窗口未闭合时遇到的 user/system → 推迟到该组 tool 之后
            if open_decls:
                pending_defer.append(m)
            else:
                out.append(m)
    # 裁剪悬挂声明（声明了但无任何 tool 结果配对）；暂存未闭合的直接丢弃
    if declared:
        dangling = set(declared)
        out = [_strip_dangling(m, dangling) if m.role == "assistant" else m for m in out]
    return out


def requires_tool_call_id(m: Message) -> bool:
    """该 tool 消息是否还缺配对的 tool_call_id（调试/断言辅助）。"""
    return m.role == "tool" and not m.metadata.get("tool_call_id")
