"""单元层任务组：长书记忆保持（T15）+ SSE 帧协议（T16）。"""

from __future__ import annotations

import yaml

from benchmarks.unit.core import ApiClient, GOLD_DIR, normalize

ASSETS = GOLD_DIR.parent.parent / "assets"


def _chapter_text(n: int) -> str:
    return (ASSETS / f"ch{n}.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# T15 长书记忆保持率（先灌章节，末尾提问核对）
# ---------------------------------------------------------------------------
def t15_memory_retention(api: ApiClient) -> tuple[bool, dict, str]:
    points = yaml.safe_load((GOLD_DIR / "memory_points.yaml").read_text(encoding="utf-8"))["points"]
    summaries = yaml.safe_load((GOLD_DIR / "chapter_summaries.yaml").read_text(encoding="utf-8"))
    conv = api.post("/api/chat", {"message": "我们开始共同创作一个故事。以下是我收集的背景资料。"})["conversation_id"]
    # 第 1 章喂全文；第 2/3 章喂摘要（控制输入规模避免超时，保持跨章测试意图）
    feeds = [
        ("第1章", _chapter_text(1)),
        ("第2章摘要", summaries["ch2_summary"]),
        ("第3章摘要", summaries["ch3_summary"]),
    ]
    for label, chunk in feeds:
        api.post(
            "/api/chat",
            {"message": f"【背景资料·{label}】\n{chunk}", "conversation_id": conv, "skip_inject": ["manual", "graph", "bias", "mood"], "extract_graph": False},
        )
    # 抽查 3 个关键事实（每章一个，跨距覆盖）
    sample = [p for p in points if p["id"] in ("m1", "m5", "m7")]
    n_hit = 0
    details: list[str] = []
    for p in sample:
        resp = api.post(
            "/api/chat",
            {"message": p["question"], "conversation_id": conv, "skip_inject": ["manual", "graph", "bias", "mood"], "extract_graph": False},
        )
        answer = str(resp.get("text", ""))
        hit = normalize(p["key"]) in normalize(answer)
        n_hit += 1 if hit else 0
        details.append(f"{p['id']}:{'✓' if hit else '✗'}")
    rate = n_hit / len(sample)
    return (
        rate >= 0.66,
        {"hit": n_hit, "total": len(sample), "hit_rate": round(rate, 3)},
        " ".join(details),
    )


# ---------------------------------------------------------------------------
# T16 SSE 帧协议（事件序列合法 + 文本非空）
# ---------------------------------------------------------------------------
def t16_sse_frames(api: ApiClient) -> tuple[bool, dict, str]:
    frames = api.post_stream("/api/chat/stream", {"message": "用两句话描述雾城的清晨。", "skip_inject": ["manual", "graph", "bias", "mood"]})
    types = [t for t, _ in frames]
    text = "".join(p.get("content", "") for t, p in frames if t == "text_delta")
    ok_done = "done" in types
    ok_delta = any(t == "text_delta" for t in types)
    ok_no_error = "error" not in types
    # 帧序：text_delta 必须全部出现在 done 之前
    if "done" in types:
        delta_positions = [i for i, t in enumerate(types) if t == "text_delta"]
        done_pos = types.index("done")
        ok_order = all(p < done_pos for p in delta_positions)
    else:
        ok_order = False
    passed = ok_done and ok_delta and ok_no_error and ok_order and len(text) > 0
    return (
        passed,
        {"frames": len(frames), "delta_frames": types.count("text_delta"), "text_chars": len(text), "types": sorted(set(types))},
        f"顺序: {' → '.join(types[:8])}...",
    )
