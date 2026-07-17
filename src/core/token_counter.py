import tiktoken

_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        try:
            # DeepSeek has no official tiktoken encoder. Using gpt-4o's
            # cl100k_base as a best-effort approximation. Token counts may
            # differ by ~10-15% from DeepSeek's actual tokenizer. This is
            # acceptable for context budget management (compaction decisions)
            # but not for exact billing.
            _encoder = tiktoken.encoding_for_model("gpt-4o")
        except (KeyError, ValueError):
            _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_encoder().encode(text))


def count_message_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        total += 4
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""))
        # Tool calls: name + arguments both cost tokens.
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += count_tokens(tc.get("function", {}).get("name", ""))
                total += count_tokens(tc.get("function", {}).get("arguments", ""))
        # Reasoning content (DeepSeek reasoner). When present it occupies
        # context budget even though we don't replay it into later turns —
        # counting it here gives accurate usage for the *current* turn.
        reasoning = msg.get("reasoning")
        if reasoning:
            total += count_tokens(reasoning)
    total += 2
    return total


MODEL_CONTEXT_LIMITS = {
    "deepseek-v4-pro": 1000000,
    "deepseek-v4-flash": 1000000,
    "deepseek-chat": 1000000,
    "deepseek-reasoner": 64000,
}


def get_context_limit(model: str) -> int:
    return MODEL_CONTEXT_LIMITS.get(model, 128000)
