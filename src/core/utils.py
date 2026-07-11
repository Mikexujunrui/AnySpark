import json


def extract_json_from_response(text: str) -> str:
    s = text.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def safe_json_parse(text: str, default=None):
    try:
        cleaned = extract_json_from_response(text)
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return default


def estimate_tokens(text: str) -> int:
    """Better Chinese+English token estimation. CJK chars ≈1.5 tokens, English ≈0.25 per char."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - cjk
    return int(cjk * 1.5 + other * 0.25)
