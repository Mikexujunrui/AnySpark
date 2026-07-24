# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tool handlers for the narrative logic engine.

These are thin wrappers that extract parameters, call the
narrative_logic package, and format the result for the agent.
"""

from __future__ import annotations

import json
import logging

from core.llm_client import chat as llm_chat
from core.narrative_logic import (
    ConfidenceScorer,
    ConstraintChecker,
    ConstraintStore,
    ImpactPropagator,
    ImpactSource,
)
from core.thread_pools import llm_pool as _ai_executor
from core.utils import extract_json_from_response

logger = logging.getLogger(__name__)


# ── Constraint definition ──


async def _define_constraint(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Convert a natural-language constraint into a structured rule and store it."""
    description = args.get("description", "").strip()
    if not description:
        return "错误: 需要描述约束规则"

    severity = args.get("severity", "hard")
    if severity not in ("hard", "soft"):
        severity = "hard"

    # Use LLM to classify the constraint and generate a Cypher violation query
    system = """你是小说叙事约束分析专家。将用户的自然语言约束转换为结构化规则。

分析约束类型:
- entity_state: 实体状态约束（如"X归Y所有"、"X在Y地点"）
- relation_lock: 关系锁定约束（如"A和B是盟友"）
- temporal_order: 时序约束（如"事件X在事件Y之前"）
- custom: 自定义约束

生成一个只读Cypher查询（仅MATCH/RETURN，禁止CREATE/DELETE/SET），用于检测违反此约束的情况。
查询中使用 $pid 作为项目ID参数。

输出JSON:
{
  "constraint_type": "entity_state|relation_lock|temporal_order|custom",
  "target_entity": "约束涉及的主要实体名（如无则为空字符串）",
  "condition": {"key": "value"},  // 结构化条件
  "violation_query": "MATCH ... RETURN ..."  // 检测违反的Cypher查询
}
"""

    # Build context: list existing entity names so the LLM can reference them
    entities = kb.list_entities()
    entity_names = [e.name for e in entities[:50]]  # cap at 50 for token budget
    context = f"知识库中的实体（前50个）: {', '.join(entity_names)}\n" if entity_names else ""

    prompt = f"{context}用户约束: {description}"

    try:
        response = await loop.run_in_executor(_ai_executor, llm_chat, prompt, system, 0.1, "extraction")
        parsed = extract_json_from_response(response)
        if not parsed:
            # Fallback: store as custom with no violation query
            parsed = {
                "constraint_type": "custom",
                "target_entity": "",
                "condition": {},
                "violation_query": "",
            }
    except Exception as e:
        logger.warning("LLM constraint parsing failed: %s", e)
        parsed = {
            "constraint_type": "custom",
            "target_entity": "",
            "condition": {},
            "violation_query": "",
        }

    # Store the constraint
    store = ConstraintStore(kb)
    constraint = store.add(
        description=description,
        constraint_type=parsed.get("constraint_type", "custom"),
        target_entity=parsed.get("target_entity", ""),
        condition=parsed.get("condition", {}),
        violation_query=parsed.get("violation_query", ""),
        severity=severity,
    )

    lines = [
        f"已创建叙事约束 #{constraint.id}",
        f"  规则: {description}",
        f"  类型: {constraint.constraint_type}",
        f"  严重度: {severity}",
    ]
    if constraint.violation_query:
        lines.append(f"  检测查询: {constraint.violation_query[:100]}...")
        lines.append("系统将在 check_constraints 时自动执行检测。")
    else:
        lines.append("  (未生成自动检测查询，此约束仅作记录)")
    lines.append(f"\n当前共有 {len(store.list())} 条活跃约束。")

    return "\n".join(lines)


# ── Constraint checking ──


async def _check_constraints(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Check all active constraints and report violations."""
    checker = ConstraintChecker(kb)
    store = ConstraintStore(kb)
    constraints = store.list(active_only=True)

    if not constraints:
        return "当前没有活跃的叙事约束。使用 define_constraint 创建约束。"

    violations = checker.check_all()

    lines = [f"检查了 {len(constraints)} 条叙事约束:"]

    if not violations:
        lines.append("所有约束全部通过。")
    else:
        lines.append(f"发现 {len(violations)} 条约束被违反:\n")
        for v in violations:
            sev_icon = {"hard": "🔴", "soft": "🟡"}.get(v.severity, "⚪")
            lines.append(f"{sev_icon} 约束#{v.constraint_id}: {v.description}")
            for detail in v.violations[:5]:
                lines.append(f"   - {json.dumps(detail, ensure_ascii=False)}")
            if len(v.violations) > 5:
                lines.append(f"   ... 还有 {len(v.violations) - 5} 条违反")

    return "\n".join(lines)


# ── Impact analysis ──


async def _analyze_impact(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Analyze the blast radius of modifying a graph element."""
    source_type = args.get("source_type", "entity")
    source_id = args.get("source_id", "").strip()
    change_desc = args.get("change_description", "")

    if not source_id:
        return "错误: 需要 source_id 参数"

    if source_type not in ("entity", "timeline_event", "foreshadow"):
        return f"错误: source_type 必须是 entity / timeline_event / foreshadow，当前为 {source_type}"

    propagator = ImpactPropagator(kb)
    source = ImpactSource(
        source_type=source_type,
        source_id=source_id,
        description=change_desc,
    )
    report = propagator.propagate(source)

    sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(report.max_severity, "⚪")

    lines = [
        f"影响传播分析 {sev_icon} (爆炸半径: {report.blast_radius} 个节点, 严重度: {report.max_severity})",
    ]
    if change_desc:
        lines.append(f"  改动: {change_desc}")

    if report.directly_affected:
        lines.append(f"\n🔴 直接影响 ({len(report.directly_affected)} 个):")
        for item in report.directly_affected[:10]:
            lines.append(f"   - {item['name']} ({item['type']}, 权重={item['weight']})")

    if report.indirectly_affected:
        lines.append(f"\n🟡 间接影响 ({len(report.indirectly_affected)} 个):")
        for item in report.indirectly_affected[:10]:
            lines.append(
                f"   - {item['name']} ({item['type']}, 权重={item['weight']}, {item.get('path_length', '?')}跳)"
            )

    if report.affected_chapters:
        lines.append(f"\n📖 受影响时间线事件 ({len(report.affected_chapters)} 个):")
        for ch in report.affected_chapters[:5]:
            lines.append(f"   - {ch.get('label', '?')} (章节: {ch.get('chapter_ref', '?')})")

    if report.affected_foreshadows:
        lines.append(f"\n🔮 受影响伏笔 ({len(report.affected_foreshadows)} 个):")
        for fs in report.affected_foreshadows[:5]:
            status = "已回收" if fs.get("resolved") else "未回收"
            lines.append(f"   - {fs.get('text', '?')[:30]}... ({status})")

    if report.blast_radius == 0:
        lines.append("\n未找到关联节点，此改动影响范围极小。")

    return "\n".join(lines)


# ── Confidence scoring ──


async def _score_confidence(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Score the confidence/health of knowledge entities."""
    entity_id = args.get("entity_id", "").strip()
    scorer = ConfidenceScorer(kb)

    if entity_id:
        score = scorer.score_one(entity_id)
        scores = [score]
    else:
        scores = scorer.score_all()

    if not scores:
        return "知识库为空，没有可评分的实体。"

    lines = [f"设定可信度评分 ({len(scores)} 个实体):\n"]

    for s in scores[:30]:
        stars = "★" * s.stars + "☆" * (5 - s.stars)
        lines.append(
            f"{stars} {s.entity_name} ({s.entity_type}) "
            f"[{s.confidence}] - {s.chapter_mentions}次引用, "
            f"{s.relation_count}条关系, {s.contradiction_count}个矛盾"
        )
        if s.recommendation != "设定充足":
            lines.append(f"   → {s.recommendation}")

    if len(scores) > 30:
        lines.append(f"\n... 还有 {len(scores) - 30} 个实体未显示")

    # Summary
    avg = sum(s.confidence for s in scores) / len(scores)
    low_count = sum(1 for s in scores if s.confidence < 0.3)
    high_count = sum(1 for s in scores if s.confidence >= 0.5)
    lines.append(f"\n平均可信度: {avg:.3f} | 高分(>=0.5): {high_count} | 低分(<0.3): {low_count}")

    return "\n".join(lines)


# ── Delete constraint (bonus utility) ──


async def _delete_constraint(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Delete a narrative constraint by ID."""
    cid = args.get("constraint_id", "").strip()
    if not cid:
        return "错误: 需要 constraint_id 参数"

    store = ConstraintStore(kb)
    existing = store.get(cid)
    if not existing:
        return f"错误: 约束 {cid} 不存在"

    store.delete(cid)
    remaining = store.list(active_only=True)
    return f"已删除约束 #{cid} ({existing.description})\n剩余活跃约束: {len(remaining)} 条"


# ── Graph search (GraphRAG) ──


async def _search_graph(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Natural language search over the knowledge graph using GraphRAG."""
    from core.graph_search import graph_search

    question = args.get("question", "").strip()
    if not question:
        return "错误: 需要 question 参数"

    try:
        result = await loop.run_in_executor(_ai_executor, graph_search, kb, question)
    except Exception as e:
        return f"图谱搜索失败: {e}"

    if result.error and not result.answer:
        return f"图谱搜索失败: {result.error}"

    lines = [f"问答: {question}"]
    if result.answer:
        lines.append(f"\n{result.answer}")
    if result.sub_questions:
        lines.append(f"\n分解子问题: {', '.join(result.sub_questions)}")
    if result.results:
        found = sum(len(r.rows) for r in result.results if not r.error)
        lines.append(f"查询到 {found} 条结果")
    return "\n".join(lines)


# ── Graph insights ──


async def _get_graph_insights(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Get actionable insights from graph analysis for writing decisions."""
    try:
        insights = await loop.run_in_executor(_ai_executor, kb.get_graph_insights)
    except Exception as e:
        return f"图谱洞察获取失败: {e}"

    lines = ["## 图谱洞察"]

    forgotten = insights.get("forgotten_characters", [])
    if forgotten:
        lines.append(f"\n### 遗忘角色 ({len(forgotten)}个)")
        for c in forgotten[:5]:
            lines.append(f"  - {c.get('name', '?')}: {c.get('reason', '')}")

    unresolved = insights.get("unresolved_foreshadows", [])
    if unresolved:
        lines.append(f"\n### 未回收伏笔 ({len(unresolved)}个)")
        for f in unresolved[:5]:
            lines.append(f"  - {f.get('text', '?')[:50]}")

    disconnected = insights.get("disconnected_pairs", [])
    if disconnected:
        lines.append(f"\n### 断连角色对 ({len(disconnected)}对)")
        for d in disconnected[:3]:
            lines.append(f"  - {d}")

    bridges = insights.get("bridge_characters", [])
    if bridges:
        lines.append(f"\n### 桥接角色 ({len(bridges)}个)")
        for b in bridges[:3]:
            cnt = b.get("connection_count", "?")
            lines.append(f"  - {b.get('entity_name', '?')}: 连接 {cnt} 条关系链")

    underutilized = insights.get("underutilized_locations", [])
    if underutilized:
        lines.append(f"\n### 未使用地点 ({len(underutilized)}个)")
        for loc in underutilized[:3]:
            lines.append(f"  - {loc}")

    scores = insights.get("confidence_scores", [])
    if scores:
        weak = [s for s in scores if s.get("confidence", 1) < 0.3]
        if weak:
            lines.append(f"\n### 设定薄弱 ({len(weak)}个)")
            for s in weak[:5]:
                lines.append(
                    f"  - {s.get('entity_name', '?')} ({s.get('entity_type', '')}): {s.get('recommendation', '')}"
                )

    violations = insights.get("constraint_violations", [])
    if violations:
        lines.append(f"\n### 约束违反 ({len(violations)}条)")
        for v in violations[:3]:
            lines.append(f"  - [{v.get('severity', '')}] {v.get('description', '')}")

    suggestions = insights.get("suggestions", [])
    if suggestions:
        lines.append("\n### 写作建议")
        for s in suggestions[:5]:
            lines.append(f"  - [{s.get('priority', '')}] {s.get('message', '')}")

    if len(lines) == 1:
        lines.append("暂无洞察。知识库可能为空或图谱未初始化。")
    return "\n".join(lines)


# ── Chapter verification (post-write quality gate) ──


async def _verify_chapter(loop, args: dict, kb, book_id: str, msg: str = "") -> str:
    """Post-write verification: entity drift, outline compliance, constraints, foreshadows, confidence.

    Supports two modes:
    - Pre-storage: pass `text` + `chapter_num` to verify raw text before storing
    - Post-storage: pass `chapter_id` to read text from storage
    """
    from data.json_store import json_store

    # 1. Get text to verify — either from args (pre-storage) or from storage
    text = args.get("text", "").strip()
    chapter_num = args.get("chapter_num")
    chapter_id = args.get("chapter_id", "").strip()

    if text:
        # Pre-storage mode: text provided directly
        title = args.get("title", "\u672a\u5b58\u50a8\u7ae0\u8282")
    elif chapter_id:
        # Post-storage mode: read from storage
        chapters = json_store.load_chapters(book_id)
        chapter = json_store._find_chapter(chapters, chapter_id)
        if not chapter:
            return f"\u9519\u8bef: \u7ae0\u8282\u4e0d\u5b58\u5728: {chapter_id}"
        view = json_store._chapter_view(chapter)
        text = view.get("content", "")
        title = view.get("title", chapter_id)
        # Extract chapter_num from chapter_id if not provided
        if chapter_num is None:
            import re

            ch_match = re.search(r"#?(\d+)", chapter_id)
            if ch_match:
                chapter_num = int(ch_match.group(1))
    else:
        return "\u9519\u8bef: \u9700\u8981 chapter_id \u6216 text \u53c2\u6570"

    if not text or len(text.strip()) < 50:
        return f"\u7ae0\u8282\u5185\u5bb9\u8fc7\u77ed\uff08{len(text)}\u5b57\uff09\uff0c\u65e0\u6cd5\u9a8c\u8bc1\u3002"

    # Get scope entity names for drift detection
    scope_entities_str = args.get("scope_entities", "")
    all_entities = kb.list_entities()
    all_entity_names = {e.name for e in all_entities}
    for e in all_entities:
        all_entity_names.update(e.aliases)

    if scope_entities_str:
        scope_names = {n.strip() for n in scope_entities_str.split(",") if n.strip()}
    else:
        scope_names = all_entity_names

    lines = [f"## 章节验证报告: {title} ({len(text)}字)"]
    has_issues = False

    # 2. Entity drift detection (LLM-based)
    try:
        entity_system = '你是文本分析专家。从给定的小说文本中提取所有出现的人名、地名、物品名、组织名、功法名。只输出JSON数组，如 ["叶凡", "青云宗", "古魔洞"]。不要输出其他文字。'
        entity_prompt = (
            f"请从以下文本中提取所有实体名（人名/地名/物品名/组织名/功法名）:\n\n{text[:3000]}\n\n输出JSON数组:"
        )
        raw = await loop.run_in_executor(_ai_executor, llm_chat, entity_prompt, entity_system, 0.1, "extraction")
        import re

        json_match = re.search(r"\[.*?\]", raw, re.DOTALL)
        text_entities = set()
        if json_match:
            try:
                text_entities = set(json.loads(json_match.group()))
            except json.JSONDecodeError:
                pass

        hallucinated = text_entities - all_entity_names
        out_of_scope = text_entities - scope_names - hallucinated

        lines.append("\n### 实体漂移检测")
        lines.append(f"- 知识库实体: {len(all_entity_names)}个 | 文本中提取: {len(text_entities)}个")
        if hallucinated:
            has_issues = True
            lines.append(f"- 幻觉实体（文本中有但知识库没有）: {', '.join(list(hallucinated)[:10])}")
            lines.append("  建议: patch_chapter 替换或 extract_knowledge 补充")
        else:
            lines.append("- 无幻觉实体")
        if out_of_scope:
            lines.append(f"- scope外实体（知识库有但不在本章范围）: {', '.join(list(out_of_scope)[:5])}")
    except Exception as e:
        lines.append(f"\n### 实体漂移检测 (失败: {str(e)[:50]})")

    # 3. Constraint check
    try:
        checker = ConstraintChecker(kb)
        store = ConstraintStore(kb)
        constraints = store.list(active_only=True)
        if constraints:
            violations = checker.check_all()
            lines.append("\n### 约束检查")
            lines.append(f"- 活跃约束 {len(constraints)} 条")
            if violations:
                has_issues = True
                for v in violations[:5]:
                    sev = "🔴" if v.severity == "hard" else "🟡"
                    lines.append(f"  {sev} [{v.severity}] {v.description}")
                    for detail in v.violations[:2]:
                        lines.append(f"     - {detail}")
            else:
                lines.append("- 全部通过")
    except Exception as e:
        logger.debug("constraint check in verify failed: %s", e)

    # 4. Outline compliance check (LLM-based)
    try:
        if chapter_num:
            detailed = json_store.get_detailed_outline(book_id).get("chapters", [])
            if chapter_num - 1 < len(detailed) and detailed[chapter_num - 1]:
                ch_detail = detailed[chapter_num - 1]
                plot_chain = ch_detail.get("plot_chain", [])
                if plot_chain:
                    compliance_system = '你是文本分析专家。判断给定的剧情事件是否在章节文本中被覆盖。只输出JSON: {"covered": [true/false, ...], "missing": ["遗漏的事件描述", ...]}'
                    compliance_prompt = (
                        f"章节文本（前2000字）:\n{text[:2000]}\n\n剧情事件链:\n"
                        + "\n".join(f"{i + 1}. {ev}" for i, ev in enumerate(plot_chain))
                        + "\n\n请判断每个事件是否被覆盖，输出JSON:"
                    )
                    raw2 = await loop.run_in_executor(
                        _ai_executor, llm_chat, compliance_prompt, compliance_system, 0.1, "extraction"
                    )
                    j = extract_json_from_response(raw2)
                    if j:
                        result = json.loads(j.strip())
                        missing = result.get("missing", [])
                        covered_count = sum(1 for c in result.get("covered", []) if c)
                        lines.append("\n### 大纲合规")
                        lines.append(f"- 细纲事件 {len(plot_chain)} 个，覆盖 {covered_count} 个")
                        if missing:
                            has_issues = True
                            lines.append(f"- 遗漏 {len(missing)} 个事件:")
                            for m in missing[:5]:
                                lines.append(f"  - {m}")
                            lines.append("  建议: patch_chapter 补充遗漏内容")
                        else:
                            lines.append("- 全部覆盖")
    except Exception as e:
        logger.debug("outline compliance check failed: %s", e)

    # 5. Foreshadow status check
    try:
        fores = kb.list_foreshadows(resolved=False)
        if fores:
            lines.append("\n### 伏笔状态")
            lines.append(f"- 未回收伏笔 {len(fores)} 个")
            # Check if any foreshadow text appears resolved in chapter
            resolved_in_chapter = []
            for f in fores:
                if f.text[:20] in text:
                    resolved_in_chapter.append(f.text[:30])
            if resolved_in_chapter:
                lines.append("- 可能在本章中回收了伏笔（请确认）:")
                for r in resolved_in_chapter[:3]:
                    lines.append(f"  - {r}")
    except Exception as e:
        logger.debug("foreshadow check failed: %s", e)

    # 6. Confidence scoring (only for entities mentioned in text)
    try:
        scorer = ConfidenceScorer(kb)
        all_scores = scorer.score_all()
        mentioned_scores = [
            s for s in all_scores if s.entity_name in (text_entities if "text_entities" in dir() else set())
        ]
        if not mentioned_scores:
            mentioned_scores = all_scores[:10]
        if mentioned_scores:
            weak = [s for s in mentioned_scores if s.confidence < 0.3]
            lines.append("\n### 可信度")
            if weak:
                lines.append(f"- 设定薄弱的实体 ({len(weak)}个):")
                for s in weak[:5]:
                    lines.append(f"  - {s.entity_name} ({s.entity_type}): {s.recommendation}")
            else:
                avg = sum(s.confidence for s in mentioned_scores) / len(mentioned_scores)
                lines.append(f"- 平均可信度: {avg:.3f} | 全部充足")
    except Exception as e:
        logger.debug("confidence scoring in verify failed: %s", e)

    if has_issues:
        lines.append("\n⚠️ 验证发现问题，建议修正后重新验证。")
    else:
        lines.append("\n✅ 验证通过，未发现明显问题。")

    return "\n".join(lines)
