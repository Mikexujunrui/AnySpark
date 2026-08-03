"""单元层任务组：检测网 + 规则编译器（T6-T7）。"""

from __future__ import annotations

import yaml

from benchmarks.unit.core import ApiClient, GOLD_DIR


# ---------------------------------------------------------------------------
# T6 检测网冲突发现率（预埋 N 个隐藏设定冲突）
# ---------------------------------------------------------------------------
def t6_conflict_detection(api: ApiClient) -> tuple[bool, dict, str]:
    data = yaml.safe_load((GOLD_DIR / "conflicts.yaml").read_text(encoding="utf-8"))
    n_planted = len(data["conflicts"])
    resp = api.post("/api/check", {"text": data["text"], "target": "哈利波特·魔法石·续写片段"})
    findings = resp.get("findings", [])
    hard = [f for f in findings if f.get("severity") == "hard"]
    n_detected = len(hard)
    rate = n_detected / n_planted
    # 宽松阈值：≥3/7 命中即通过（真模型动态检测存在召回不确定），记录数值供趋势观察
    passed = n_detected >= 3
    messages = "; ".join(f.get("message", "")[:60] for f in hard[:5])
    return (
        passed,
        {"planted": n_planted, "detected_hard": n_detected, "hit_rate": round(rate, 3), "total_findings": len(findings)},
        messages,
    )


# ---------------------------------------------------------------------------
# T7 轻量规则编译器（自然语言规则 → 命中）
# ---------------------------------------------------------------------------
def t7_rule_compiler(api: ApiClient) -> tuple[bool, dict, str]:
    # 禁用词规则：含"破折号"（防 AI 味滥用）——规则："禁用破折号"
    resp_pos = api.post("/api/check/rule", {"rule": "禁用破折号", "text": "他推开门——然后愣住了。"})
    resp_neg = api.post("/api/check/rule", {"rule": "禁用破折号", "text": "他推开门，然后愣住了。"})

    ok_pos = resp_pos.get("ok") is True and len(resp_pos.get("hits", [])) >= 1
    ok_neg = resp_neg.get("ok") is True and len(resp_neg.get("hits", [])) == 0
    return (
        ok_pos and ok_neg,
        {"positive_hit": len(resp_pos.get("hits", [])), "negative_hit": len(resp_neg.get("hits", [])), "desc": resp_pos.get("description", "")},
        f"pos={resp_pos.get('hits')} neg={resp_neg.get('hits')}",
    )
