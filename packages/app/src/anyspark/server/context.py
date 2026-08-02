"""
anyspark.server.context — token 预算 + 两阶段压缩（长书刚需）。

设计（DESIGN 模型局限弥补）：
- "上下文窗口有限 → prune/summarize 两阶段压缩"
- "算不了数/算不准 → token 精确计算（tiktoken）"

两阶段：
  阶段 1 prune：超预算时从最早的对话消息开始切出"可压缩段"（system 永远保留，
                最近 K 条消息保底保留——进行中的对话不能砍）。
  阶段 2 summarize：若注入 LLM 摘要器，把切出的历史压成一条"历史摘要"系统消息
                插回（信息密度保留）；无摘要器则纯丢弃（prune-only 降级）。

模型无关：压缩产物为自然语言消息；计数器用 tiktoken cl100k_base 近似
（DeepSeek 自研 tokenizer 无公开编码，预算留安全余量，调用方按 ~1.2 系数）。
"""

from __future__ import annotations

from collections.abc import Callable

import tiktoken

from anyspark.core.types import Message

# 保留最近多少条消息（进行中对话不砍）
KEEP_RECENT = 6
# 预算安全系数：DeepSeek tokenizer 与 cl100k 的偏差余量
SAFETY_FACTOR = 1.2

Summarizer = Callable[[list[Message]], str] | None


class TokenBudget:
    """tiktoken 精确计数 + prune/summarize 两阶段压缩器（core 的 ContextCompressor 实现）。"""

    def __init__(
        self,
        budget: int = 12000,
        encoding: str = "cl100k_base",
        summarize: Summarizer = None,
    ) -> None:
        self._budget = int(budget / SAFETY_FACTOR)
        self._enc = tiktoken.get_encoding(encoding)
        self._summarize = summarize

    # ------------------------------------------------------------------
    # 计数
    # ------------------------------------------------------------------
    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def count_messages(self, messages: list[Message]) -> int:
        return sum(self.count(m.content) for m in messages)

    # ------------------------------------------------------------------
    # 压缩（ContextCompressor 协议入口）
    # ------------------------------------------------------------------
    def compress(self, messages: list[Message]) -> list[Message]:
        """输入完整 prompt 消息，超预算则两阶段压缩，返回压缩后消息。"""
        total = self.count_messages(messages)
        if total <= self._budget:
            return messages

        # 找出可压缩段：messages[0] 可能是 system（保留），从其后开始；
        # 保底保留最近 KEEP_RECENT 条（进行中对话）。
        head_len = 1 if messages and messages[0].role == "system" else 0
        if len(messages) <= head_len + KEEP_RECENT:
            # 消息太少无法压缩，直接截断最近的到预算内
            return self._truncate_tail(messages, head_len)

        cut_end = len(messages) - KEEP_RECENT  # 可压缩段 [head_len, cut_end)
        if cut_end <= head_len:
            return self._truncate_tail(messages, head_len)

        # 阶段 2：LLM 摘要可压缩段（无摘要器则纯 prune）
        history_part = messages[head_len:cut_end]
        if self._summarize is not None:
            try:
                summary = self._summarize(history_part)
                summary_msg = Message(
                    role="system",
                    content=(
                        "【历史对话摘要】（压缩自 "
                        f"{len(history_part)} 条消息，省 token）\n{summary}"
                    ),
                )
                kept = (
                    [messages[0], summary_msg, *messages[cut_end:]]
                    if head_len
                    else [summary_msg, *messages[cut_end:]]
                )
                if self.count_messages(kept) <= total:  # 摘要有效才替换
                    return kept
            except Exception:
                pass  # 摘要失败降级为纯 prune

        # 阶段 1（或降级）：纯 prune——保留 system + 最近消息（丢弃可压缩段）
        return [messages[0], *messages[cut_end:]] if head_len else messages[cut_end:]

    def _truncate_tail(self, messages: list[Message], head_len: int) -> list[Message]:
        """消息太少时的兜底：从尾部逐条保留直到预算内（最近优先）。"""
        kept = list(messages)
        while len(kept) > head_len + 1 and self.count_messages(kept) > self._budget:
            kept.pop(head_len)  # 从最旧的非 system 消息开始丢
        return kept


def make_summarizer(model: object, max_len: int = 800) -> Summarizer:
    """LLM 历史摘要器（真实 DeepSeek，模型无关）。"""

    def _summarize(history: list[Message]) -> str:
        lines = "\n".join(f"{m.role}: {m.content[:200]}" for m in history[-20:])
        prompt = (
            "你是小说写作助手。把下面的对话历史压缩成一段简明摘要（保留：进行到哪、"
            "写过什么、用户偏好/指令、关键事实）。只输出摘要正文，不要其它文字。\n\n"
            f"对话历史（{len(history)} 条）：\n{lines}"
        )
        out = model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return str(out.text)[:max_len]

    return _summarize
