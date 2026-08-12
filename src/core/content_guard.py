# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Conservative guards for model output that must never become manuscript.

Provider APIs do not consistently signal moderation/refusal as an exception.
Some return a normal 200 response whose text is an apology or safety notice.
Saving that response as a protected chapter makes the next writing attempt
look like an overwrite, so refusal detection must happen before persistence.
"""

import re

_HIGH_CONFIDENCE_PATTERNS = (
    re.compile(r"(?:内容|安全|敏感词).{0,18}(?:过滤|审查|拦截|拒绝|限制)"),
    re.compile(r"(?:content|safety).{0,18}(?:filter|moderation|policy|refus)", re.I),
    re.compile(r"(?:请求|内容).{0,18}(?:违反|不符合).{0,18}(?:政策|规定|准则)"),
)

_SHORT_REFUSAL_PREFIXES = (
    "抱歉，我无法",
    "抱歉，无法",
    "很抱歉，我无法",
    "我无法协助",
    "我不能协助",
    "我无法继续生成",
    "我不能继续生成",
    "作为ai，我无法",
    "作为 ai，我无法",
    "该请求无法完成",
    "此请求无法完成",
)


def detect_model_refusal(text: object) -> str:
    """Return a short reason when *text* is clearly a model refusal.

    The check deliberately inspects the beginning of the response and applies
    broad apology patterns only to short outputs.  This avoids treating normal
    fictional dialogue such as “我不能走” as a provider refusal.
    """

    if not isinstance(text, str):
        return "模型没有返回文本"
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return "模型返回空文本"

    head = normalized[:320]
    for pattern in _HIGH_CONFIDENCE_PATTERNS:
        match = pattern.search(head)
        if match:
            return f"疑似安全过滤/拒答：{match.group(0)[:80]}"

    lowered_head = head.lower()
    if len(normalized) <= 1000:
        for prefix in _SHORT_REFUSAL_PREFIXES:
            if prefix in lowered_head[:180]:
                return f"模型拒答：{head[:100]}"

    return ""
