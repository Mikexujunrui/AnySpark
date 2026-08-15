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

    保留正常配对（含被 user 插话隔开的配对——那是"宽松层"允许的，
    协议特有的"严格紧邻"由各适配器转换防御再处理）。
    """
    out: list[Message] = []
    declared: deque[str] = deque()
    for m in messages:
        if m.role == "assistant":
            out.append(m)
            for tid in _declared_ids(m):
                declared.append(tid)
        elif m.role == "tool":
            tid = str(m.metadata.get("tool_call_id") or "")
            if tid:
                if tid in declared:
                    declared.remove(tid)
                    out.append(m)
                # 无对应声明 → 孤儿，丢弃
            elif declared:
                # 缺 id：从相邻未配对声明补配（保持声明→tool 顺序）
                md = dict(m.metadata)
                md["tool_call_id"] = declared.popleft()
                out.append(Message(role=m.role, content=m.content, metadata=md))
            # 队列空且无 id → 孤儿，丢弃
        else:
            out.append(m)
    # 裁剪悬挂声明（声明了但无任何 tool 结果配对）
    if declared:
        dangling = set(declared)
        out = [_strip_dangling(m, dangling) if m.role == "assistant" else m for m in out]
    return out


def requires_tool_call_id(m: Message) -> bool:
    """该 tool 消息是否还缺配对的 tool_call_id（调试/断言辅助）。"""
    return m.role == "tool" and not m.metadata.get("tool_call_id")
