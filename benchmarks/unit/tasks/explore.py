"""单元层任务组：探索引擎（T10-T12）。"""

from __future__ import annotations

from benchmarks.unit.core import ApiClient

SEED = "一个侦探在雨夜里收到一封写着自己死亡时间的信"


# ---------------------------------------------------------------------------
# T10 意图确认（概念卡 + 关键歧义点）
# ---------------------------------------------------------------------------
def t10_explore_intent(api: ApiClient) -> tuple[bool, dict, str]:
    intent = api.post("/api/explore/intent", {"seed": SEED})
    # 概念卡字段（画面/基调/类型/种子位置）+ 关键歧义点
    card_ok = any(k in intent for k in ("concept", "画面", "card", "vision", "mood", "基调"))
    questions = (
        intent.get("questions") or intent.get("key_questions") or intent.get("ambiguities") or []
    )
    q_ok = isinstance(questions, list) and len(questions) >= 1
    passed = card_ok and q_ok
    return (
        passed,
        {
            "questions": len(questions) if isinstance(questions, list) else -1,
            "keys": sorted(intent.keys()),
        },
        str(intent)[:200],
    )


# ---------------------------------------------------------------------------
# T11 方向卡多样性（三来源混合 + 术语标注）
# ---------------------------------------------------------------------------
def t11_explore_diversity(api: ApiClient) -> tuple[bool, dict, str]:
    intent = api.post("/api/explore/intent", {"seed": SEED})
    cards = api.post("/api/explore/cards", {"seed": SEED, "intent_confirmed": intent})
    if not isinstance(cards, list) or len(cards) < 3:
        return False, {"n_cards": len(cards) if isinstance(cards, list) else 0}, "方向卡不足"
    sources = {c.get("source", "") for c in cards}
    terms = [c.get("term", "") for c in cards]
    # 三来源混合（template/grow/user 至少两种）+ 术语标注非空
    source_ok = len(sources) >= 2
    term_ok = sum(1 for t in terms if t) >= 2
    titles = "; ".join(c.get("title", "")[:30] for c in cards)
    return (
        source_ok and term_ok,
        {"n_cards": len(cards), "sources": sorted(sources), "terms": terms},
        titles,
    )


# ---------------------------------------------------------------------------
# T12 方向固化（选中方向落盘可查）
# ---------------------------------------------------------------------------
def t12_explore_archive(api: ApiClient) -> tuple[bool, dict, str]:
    intent = api.post("/api/explore/intent", {"seed": SEED})
    cards = api.post("/api/explore/cards", {"seed": SEED, "intent_confirmed": intent})
    if not isinstance(cards, list) or not cards:
        return False, {}, "无方向卡可固化"
    picked = cards[0]
    archived = api.post("/api/explore/archive", {"card": picked})
    ok = archived.get("archived") is True or archived.get("id") or archived.get("ok") is True
    # 落盘可查
    listed = api.get("/api/explore/archive")
    visible = (
        any(c.get("title") == picked.get("title") for c in listed)
        if isinstance(listed, list)
        else False
    )
    return (
        ok and visible,
        {
            "archived": ok,
            "visible": visible,
            "n_archived": len(listed) if isinstance(listed, list) else -1,
        },
        f"picked={picked.get('title', '')[:40]}",
    )
