"""单元层任务组：知识图谱（T1-T5）。

黑盒：只走 /api/graph/* + /api/chat + /api/check。
前置：独立后端实例（--db 隔离库），T5 需要真模型抽取短文。
"""

from __future__ import annotations

import yaml

from benchmarks.unit.core import (
    ApiClient,
    GOLD_DIR,
    entity_hit,
    normalize,
    precision_recall_f1,
)

# 提取前 3 章文本（assets 不入库）
ASSETS = GOLD_DIR.parent.parent / "assets"


def _chapter_text(n: int) -> str:
    return (ASSETS / f"ch{n}.txt").read_text(encoding="utf-8")


def _load_gold(ch: int) -> dict:
    return yaml.safe_load((GOLD_DIR / f"ch{ch}.yaml").read_text(encoding="utf-8"))


def _entities_list(api: ApiClient) -> list[dict]:
    resp = api.get("/api/graph/entities")
    return resp if isinstance(resp, list) else []


def _entity_names(api: ApiClient) -> list[str]:
    return [e.get("name", "") for e in _entities_list(api)]


# ---------------------------------------------------------------------------
# T1 图谱抽取准确率（F1 vs gold）
# ---------------------------------------------------------------------------
def t1_extract_f1(api: ApiClient) -> tuple[bool, dict, str]:
    gold = _load_gold(1)
    gold_entities = gold["entities"]
    text = _chapter_text(1)
    # 抽取并入库存真实库（黑盒：extract 端点一次性完成）；真模型波动时重试一次
    counts: dict = {}
    for attempt in range(2):
        counts = api.post("/api/graph/extract", {"chapter_ref": "第一章", "text": text})
        extracted = _entities_list(api)
        if extracted:
            break
    extracted = _entities_list(api)
    n_pred = len(extracted)
    if n_pred == 0:
        return False, {"f1": 0.0, "detail": "抽取 0 实体"}, "无实体被抽取（两次尝试）"
    # 精确率：每个抽取实体是否命中任一 gold
    tp_pred = sum(
        1 for e in extracted if any(entity_hit(g, e.get("name", "")) for g in gold_entities)
    )
    # 召回率：每个 gold 实体是否被任一抽取命中
    tp_gold = sum(
        1 for g in gold_entities if any(entity_hit(g, e.get("name", "")) for e in extracted)
    )
    prf = precision_recall_f1(tp_gold, n_pred, len(gold_entities))
    names = ", ".join(e.get("name", "") for e in extracted[:12])
    return (
        prf["f1"] >= 0.4,
        {
            "f1": prf["f1"],
            "precision": prf["precision"],
            "recall": prf["recall"],
            "n_pred": n_pred,
            "n_gold": len(gold_entities),
            "extract_api": counts,
        },
        f"抽取实体: {names}",
    )


# ---------------------------------------------------------------------------
# T2 幂等落库（重复抽取不产生重复实体名）
# ---------------------------------------------------------------------------
def t2_idempotent(api: ApiClient) -> tuple[bool, dict, str]:
    # 存储层幂等（确定性）：按名合并，重复 ingest 不产生重复名
    api.post("/api/graph/extract", {"chapter_ref": "第一章", "text": _chapter_text(1)})
    entities = _entities_list(api)
    names = [e.get("name", "") for e in entities]
    unique = len({normalize(n) for n in names if n})
    dup = len(names) - unique
    return (
        dup == 0,
        {"total": len(names), "duplicate_names": dup},
        f"实体名重复数（应为 0；LLM 抽取不确定性不计入，见说明）",
    )


# ---------------------------------------------------------------------------
# T3 注入块包含已知事实（检索→注入链路的黑盒代理）
# ---------------------------------------------------------------------------
def t3_context_block(api: ApiClient) -> tuple[bool, dict, str]:
    # 自包含：先入库第 1 章，保证图谱有事实可注入
    api.post("/api/graph/extract", {"chapter_ref": "第一章", "text": _chapter_text(1)})
    block = api.get("/api/graph/context").get("block", "")
    if not block:
        return False, {"block_len": 0}, "注入块为空"
    # gold ch1 里应出现的关键实体/关系/事件（名字在注入块中）
    checks = ["哈利·波特", "邓布利多", "伏地魔"]
    hit = sum(1 for c in checks if c in block)
    # 事件/关系块头
    has_rel = "实体关系" in block or "最近事件" in block
    return (
        hit >= 2 and has_rel,
        {"hit": hit, "has_rel": has_rel, "block_len": len(block)},
        f"注入块: {block[:200]}",
    )


# ---------------------------------------------------------------------------
# T5 时序校验（时空倒置检测）
# ---------------------------------------------------------------------------
def t5_temporal(api: ApiClient) -> tuple[bool, dict, str]:
    # 准备章节序号：写 3 个占位章（不开图谱抽取，省 token）
    for title in ("第一章", "第二章", "第三章"):
        api.post(
            "/api/chat",
            {
                "message": f"请用 write_chapter 写《{title}》，内容为一行占位文字。",
                "extract_graph": False,
            },
        )
    # 第 1 章实体入库（order=0）
    api.post("/api/graph/extract", {"chapter_ref": "第一章", "text": _chapter_text(1)})
    # 未来实体（分院帽/尼可勒梅/魔法石）入库，chapter_ref 映射到第三章（order=2）
    future_text = (
        "霍格沃茨魔法学校的大厅里，分院帽高声宣布新生分院。"
        "麦格教授站在讲台旁看着学生们。邓布利多提到他的老朋友尼可勒梅正在研究魔法石。"
    )
    api.post("/api/graph/extract", {"chapter_ref": "第三章", "text": future_text})

    temporal_yaml = yaml.safe_load((GOLD_DIR / "temporal.yaml").read_text(encoding="utf-8"))
    anomaly_text = temporal_yaml["ch1_text_with_anomaly"]
    expected = [a["entity"] for a in temporal_yaml["anomalies"]]

    # 当前时空点=第1章（order=0）：应报告"分院帽"等异常
    resp_early = api.post("/api/check", {"text": anomaly_text, "chapter_order": 0})
    warnings_early = " ".join(resp_early.get("temporal_warnings", []))
    detected = [e for e in expected if e in warnings_early]

    # 对照：时空点=第三章（order=2）：不应再报"分院帽"（它已登场）
    resp_late = api.post("/api/check", {"text": anomaly_text, "chapter_order": 2})
    warnings_late = " ".join(resp_late.get("temporal_warnings", []))
    false_positive = [e for e in expected if e in warnings_late]

    passed = len(detected) >= 1 and len(false_positive) == 0
    return (
        passed,
        {"detected": detected, "false_positive": false_positive, "expected": expected},
        f"early={warnings_early[:150]} | late={warnings_late[:150]}",
    )
