"""
anyspark.server.context — token 预算 + 两阶段压缩（长书刚需）。

设计（DESIGN 模型局限弥补）：
- "上下文窗口有限 → prune/summarize 两阶段压缩"
- "算不了数/算不准 → token 精确计算（tiktoken）"

两阶段：
  阶段 1 prune：超预算时从最早的对话消息开始切出"可压缩段"（system 永远保留，
                最近消息按 token 预算保底保留——进行中的对话不能砍）。
  阶段 2 summarize：若注入 LLM 摘要器，把切出的历史压成一条"历史摘要"系统消息
                插回（信息密度保留）；无摘要器则纯丢弃（prune-only 降级）。

S24（对齐 pi 的 compaction 语义，修复 S21c 审计发现）：
- E1 效率：指纹**先查**（内容未变直接返回缓存结果，连计数都不做）；计数两档——
  字符粗算（O(n) 极快，高估安全）滤掉绝大多数"不需要压缩"的轮次，tiktoken 精算
  只在接近预算时发生。
- B1 切割合法性：保留段按 **token 预算**（KEEP_RECENT_TOKENS）往回找，且**永不切在
  tool 结果上**（tool 结果必须跟在 assistant 声明后；孤立 tool 消息会让模型上下文畸形）。
- B2 摘要信息密度：摘要输入**全量序列化**可压缩段（此前只喂最后 20 条×200 字，
  中间关键指令全丢）；支持**增量更新**（识别上一次摘要作为 previous，用 UPDATE 模式
  追加新进展，对齐 pi 的 previousSummary + UPDATE_SUMMARIZATION_PROMPT）。

模型无关：压缩产物为自然语言消息；计数器用 tiktoken cl100k_base 近似
（DeepSeek 自研 tokenizer 无公开编码，预算留安全余量，调用方按 ~1.2 系数）。
"""

from __future__ import annotations

from collections.abc import Callable

import tiktoken

from anyspark.core import Message

# 保留最近消息的最小条数（刚发生的对话不砍，即使很小）
KEEP_RECENT_MIN = 4
# 保留最近消息的 token 预算上限（对齐 pi keepRecentTokens 语义：按 token 而非条数保底）。
# S28：实例化时按预算缩放（min(4000, 预算×40%)）——小窗口下保留段不能超过总预算，
# 否则压缩形同虚设（压力测试暴露：预算 2800 时保留段 4000 > 总预算，消息数持续上涨）。
KEEP_RECENT_TOKENS = 4000
# 保留段占预算的比例上限（防止保留段吞噬整个预算）
KEEP_RECENT_RATIO = 0.4
# 预算安全系数：DeepSeek tokenizer 与 cl100k 的偏差余量
SAFETY_FACTOR = 1.2
# 压缩触发阈值（S21 对齐 pi：接近上限前主动压缩，避免临界突变）
COMPRESS_AT = 0.9

# 摘要器签名（S24）：(可压缩段, 上一次摘要) → 摘要文本；previous 为空则初始摘要
Summarizer = Callable[[list[Message], str | None], str]

_SUMMARY_PREFIX = "【历史对话摘要】"


class TokenBudget:
    """tiktoken 精确计数 + prune/summarize 两阶段压缩器（core 的 ContextCompressor 实现）。"""

    def __init__(
        self,
        budget: int = 12000,
        encoding: str = "cl100k_base",
        summarize: Summarizer | None = None,
    ) -> None:
        self._budget = int(budget / SAFETY_FACTOR)
        # S28：保留段阈值随预算缩放（小窗口不失效）
        self._keep_recent = min(KEEP_RECENT_TOKENS, int(self._budget * KEEP_RECENT_RATIO))
        self._enc = tiktoken.get_encoding(encoding)
        self._summarize = summarize
        # 摘要结果指纹缓存（S21 修续聊卡住）：同上下文不重复调 LLM 摘要
        # （Agent 每轮迭代都 compress，消息未变时命中缓存，省 30-60s/轮）
        self._cache: dict[int, list[Message]] = {}
        self._cache_order: list[int] = []
        self._cache_max = 32

    # ------------------------------------------------------------------
    # 计数
    # ------------------------------------------------------------------
    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def count_messages(self, messages: list[Message]) -> int:
        return sum(self.count(m.content) for m in messages)

    def _rough_count(self, messages: list[Message]) -> int:
        """字符数粗算（S24 E1）：chars ≥ tokens 对中英混合基本成立（BPE 一般压缩字符），
        高估安全——粗算不超阈值则实际一定不超，可省掉 tiktoken 精算。"""
        return sum(len(m.content) for m in messages)

    # ------------------------------------------------------------------
    # 压缩（ContextCompressor 协议入口）
    # ------------------------------------------------------------------
    def compress(self, messages: list[Message]) -> list[Message]:
        """输入完整 prompt 消息，超过触发阈值（90% 预算，S21 提前触发）则压缩。

        S24 效率链：指纹先查（缓存命中直接返回，连计数都不做）→ 字符粗算（高估安全，
        绝大多数轮次在此被滤掉）→ tiktoken 精算（仅接近预算时）→ 压缩。
        """
        # E1：指纹先查——Agent 每轮迭代调用，上下文未变则直接命中缓存结果
        fingerprint = hash(tuple(m.content for m in messages))
        cached = self._cache.get(fingerprint)
        if cached is not None:
            return cached

        threshold = int(self._budget * COMPRESS_AT)
        # 粗算滤掉绝大多数"不需要压缩"的轮次（无需 tiktoken 编码全量历史）
        if self._rough_count(messages) <= threshold:
            return messages
        total = self.count_messages(messages)
        if total <= threshold:
            return messages

        kept = self._compress_uncached(messages, total)
        self._cache[fingerprint] = kept
        self._cache_order.append(fingerprint)
        if len(self._cache_order) > self._cache_max:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)
        return kept

    def _compress_uncached(self, messages: list[Message], total: int) -> list[Message]:
        """压缩主逻辑（被 compress 缓存包裹）。"""

        # 找出可压缩段：messages[0] 可能是 system（保留），从其后开始
        head_len = 1 if messages and messages[0].role == "system" else 0
        if len(messages) <= head_len + KEEP_RECENT_MIN:
            # 消息太少无法压缩，直接截断最近的到预算内
            return self._truncate_tail(messages, head_len)

        # B1：保留段按 token 预算往回找 + 切割合法性（不切在 tool 结果上）
        cut_end = self._find_cut_point(messages, head_len)
        if cut_end <= head_len:
            return self._truncate_tail(messages, head_len)

        # 已读清单（S21 修失忆-重读循环）：prune 前扫描被裁剪段里的 read 成功记录，
        # 生成"已读章节"提示——模型知道读过什么，压缩后不会盲目重读
        read_note = _collect_read_note(messages[head_len:cut_end])

        # 阶段 2：LLM 摘要可压缩段（无摘要器则纯 prune）
        history_part = messages[head_len:cut_end]
        if self._summarize is not None:
            try:
                # B2 增量更新：识别上一次摘要作为 previous，UPDATE 模式追加新进展
                previous = _extract_previous_summary(history_part)
                summary = self._summarize(history_part, previous)
                head = f"{_SUMMARY_PREFIX}（压缩自 {len(history_part)} 条，省 token）"
                summary_msg = Message(
                    role="system",
                    content=f"{head}\n{summary}",
                )
                kept = (
                    [messages[0], summary_msg, *messages[cut_end:]]
                    if head_len
                    else [summary_msg, *messages[cut_end:]]
                )
                if self.count_messages(kept) <= total:  # 摘要有效才替换
                    if read_note:
                        kept.insert(head_len + 1, read_note)
                    return kept
            except Exception:
                pass  # 摘要失败降级为纯 prune

        # 阶段 1（或降级）：纯 prune——保留 system + 最近消息（丢弃可压缩段）
        kept = [messages[0], *messages[cut_end:]] if head_len else messages[cut_end:]
        if read_note:
            kept.insert(head_len, read_note)
        return kept

    def _find_cut_point(self, messages: list[Message], head_len: int) -> int:
        """B1：返回保留段的起始下标（可压缩段 = [head_len, cut_end)）。

        - 从后往前累计字符粗算 token，达到 KEEP_RECENT_TOKENS 即停（至少保底 KEEP_RECENT_MIN 条）
        - 切割点**永不落在 tool 消息上**：保留段第一条若是 tool，说明它的 assistant
          声明在可压缩段内（已被切掉）——把孤立的 tool 结果一起切掉，避免畸形上下文。
        """
        n = len(messages)
        cut = n
        acc = 0
        for i in range(n - 1, head_len - 1, -1):
            acc += len(messages[i].content)
            if acc >= self._keep_recent and n - i >= KEEP_RECENT_MIN:
                cut = i
                break
        # 保底：至少保留最近 KEEP_RECENT_MIN 条
        if n - cut < KEEP_RECENT_MIN:
            cut = max(head_len, n - KEEP_RECENT_MIN)
        # 切割合法性：保留段第一条不能是 tool（孤立 tool 结果无声明）
        while cut < n and messages[cut].role == "tool":
            cut += 1
        return cut

    def _truncate_tail(self, messages: list[Message], head_len: int) -> list[Message]:
        """消息太少时的兜底：从尾部逐条保留直到预算内（最近优先）。"""
        kept = list(messages)
        while len(kept) > head_len + 1 and self.count_messages(kept) > self._budget:
            kept.pop(head_len)  # 从最旧的非 system 消息开始丢
        return kept


def make_summarizer(model: object, max_len: int = 800) -> Summarizer:
    """LLM 历史摘要器（真实 DeepSeek，模型无关）。

    S24（B2）：摘要输入**全量序列化**可压缩段（不再截断 20 条×200 字）；若识别到
    上一次摘要（previous 非空）则用 UPDATE 模式增量合并——对齐 pi 的
    SUMMARIZATION_PROMPT / UPDATE_SUMMARIZATION_PROMPT 结构化格式。
    """

    def _summarize(history: list[Message], previous: str | None = None) -> str:
        lines = "\n".join(f"{m.role}: {m.content}" for m in history)
        if previous:
            prompt = (
                "你是小说写作助手。以下是**新增加的**对话消息，要并入已有的历史摘要"
                "（<previous-summary> 标签内）。规则：\n"
                "- 保留已有摘要的全部信息\n"
                "- 追加新进展/新指令/新事实/关键决策\n"
                "- 已完成的事项从 In Progress 移到 Done\n"
                "- 保持简洁，保留章节标题、设定、角色名等关键事实\n\n"
                f"<previous-summary>\n{previous}\n</previous-summary>\n\n"
                f"新增对话消息（{len(history)} 条）：\n{lines}"
            )
        else:
            prompt = (
                "你是小说写作助手。把下面的对话历史压缩成一段简明摘要，必须保留：\n"
                "- 进行到哪（当前章节/写作进度）\n"
                "- 写过什么（章节标题、正文要点）\n"
                "- 用户的偏好/指令（含说明书、要求）\n"
                "- 关键事实/设定（角色、地点、事件）\n"
                "- 下一步计划\n"
                "只输出摘要正文，不要其它文字。\n\n"
                f"对话历史（{len(history)} 条）：\n{lines}"
            )
        out = model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return str(out.text)[:max_len]

    return _summarize


def _extract_previous_summary(messages: list[Message]) -> str | None:
    """从可压缩段里识别上一次压缩的摘要（最近一条【历史对话摘要】system 消息）。"""
    for m in reversed(messages):
        if m.role == "system" and m.content.startswith(_SUMMARY_PREFIX):
            return m.content
    return None


def _collect_read_note(messages: list[Message]) -> Message | None:
    """从被裁剪的消息里收集已读章节，生成"已读清单"提示（S21 修失忆-重读循环）。

    扫描 role=tool 且内容是 read_chapter 成功回填（含"全文如下"）的消息，
    提取章节标题；有已读则生成一条 system 提示：压缩后模型知道读过什么，
    不会盲目重复 read_chapter。
    """
    import re as _re

    titles: list[str] = []
    for m in messages:
        if m.role != "tool" or "全文如下" not in m.content:
            continue
        mch = _re.search(r"《(.+?)》全文如下", m.content)
        if mch:
            t = mch.group(1).strip()
            if t and t not in titles:
                titles.append(t)
    if not titles:
        return None
    listing = "、".join(f"《{t}》" for t in titles)
    return Message(
        role="system",
        content=(
            f"【已读章节清单】对话历史中已读取过：{listing}。"
            "如需引用其中内容，直接基于已读记忆/摘要，不要重复调用 read_chapter。"
        ),
    )
