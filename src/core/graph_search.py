"""Graph semantic search — LLM-driven question answering over the knowledge graph.

Decomposes user questions into sub-questions, generates Cypher queries,
executes them, and synthesizes results.

This implementation uses:
- LLM for question decomposition → sub-questions
- LLM for Cypher generation (with EXPLAIN pre-validation)
- Neo4j FTS for text search fallback
- LLM for result synthesis
"""

import json
import logging
from dataclasses import dataclass, field

from .graph_store import GraphStore
from .llm_client import chat as llm_chat
from .utils import extract_json_from_response

logger = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = """你是一位Neo4j图数据库查询专家。你正在处理一个小说知识图谱，包含以下节点和关系：

## 节点类型
- Entity:Character — 角色
- Entity:Location — 地点
- Entity:Item — 物品
- Entity:Skill — 技能/功法
- Entity:Organization — 组织
- Entity:Race — 种族
- Entity:Concept — 概念
- Entity:Event — 事件
- Timeline — 时间线事件
- Fore — 伏笔

## 关系类型
- KNOWS, ALLY, ANTAGONIST, FAMILY, ROMANTIC, LOVES, MENTOR_OF, MASTER_OF
- KILLED, SAVED, OWNS, BELONGS_TO, LOCATED_AT
- CAUSES, BEFORE, AFTER, FORESHADOWS, RESOLVES, PARTICIPATES_IN
- INVOLVES (Timeline→Entity), HAS_PHASE (Entity→Snapshot), DEPENDS_ON (Fore→Fore)
- LOCATED_IN (Location→Location, 空间包含), ADJACENT_TO (Location→Location, 相邻)
- OCCURRED_AT (Timeline→Location, 事件发生地点)

## 实体属性
- id, entity_type, name, aliases (列表), data (JSON), project_id

## 任务
根据用户问题，生成一个或多个Cypher查询来回答。输出JSON格式：

```json
{
  "sub_questions": ["分解后的子问题1", "子问题2"],
  "queries": [
    {
      "cypher": "MATCH ... RETURN ...",
      "explanation": "这个查询做什么",
      "sub_question_index": 0
    }
  ],
  "synthesis_hint": "如何综合结果回答"
}
```

## 规则
1. 必须在WHERE子句中使用 project_id 过滤（参数名 $pid）
2. 使用 LIMIT 限制返回数量（最多50条）
3. 对于实体名查询，使用模糊匹配：WHERE e.name CONTAINS $name
4. 对于关系查询，使用 type(r) 获取关系类型
5. 避免使用 * 全图扫描
6. 如果问题涉及多个实体，使用最短路径查询
7. query 和 sub_question 必须一一对应
"""


@dataclass
class SearchResult:
    """A single search result."""
    sub_question: str = ""
    cypher: str = ""
    explanation: str = ""
    rows: list[dict] = field(default_factory=list)
    error: str = ""


@dataclass
class GraphSearchResponse:
    """Complete search response."""
    original_question: str = ""
    sub_questions: list[str] = field(default_factory=list)
    results: list[SearchResult] = field(default_factory=list)
    answer: str = ""
    error: str = ""


def _execute_cypher(store: GraphStore, cypher: str, params: dict) -> tuple[list[dict], str]:
    """Execute a Cypher query with pre-validation and error handling."""
    try:
        # Pre-validate with EXPLAIN
        explain_result = store._run(f"EXPLAIN {cypher}", params)
        if not explain_result and store._driver is not None:
            # EXPLAIN returned empty but driver is alive — query may be valid
            pass
    except Exception as e:
        return [], f"Cypher syntax error: {str(e)[:120]}"

    try:
        rows = store._run(cypher, params)
        # Convert Neo4j records to dicts
        result = []
        for row in rows:
            d = {}
            for key, value in row.items():
                if hasattr(value, '_properties'):
                    # Node or Relationship
                    d[key] = dict(value._properties) if hasattr(value, '_properties') else str(value)
                    d[key]['_labels'] = list(value.labels) if hasattr(value, 'labels') else []
                elif isinstance(value, (list, dict)):
                    d[key] = value
                else:
                    d[key] = str(value) if value is not None else None
            result.append(d)
        return result, ""
    except Exception as e:
        return [], f"Query execution error: {str(e)[:120]}"


def _format_results_for_llm(results: list[SearchResult]) -> str:
    """Format search results as compact text for LLM synthesis."""
    parts = []
    for i, r in enumerate(results):
        parts.append(f"\n### 子问题{i+1}: {r.sub_question}")
        if r.error:
            parts.append(f"查询失败: {r.error}")
        elif r.rows:
            parts.append(f"Cypher: {r.cypher}")
            parts.append(f"结果 ({len(r.rows)}条):")
            for j, row in enumerate(r.rows[:10]):
                # Compact row representation
                flat = {}
                for k, v in row.items():
                    if isinstance(v, dict):
                        flat[k] = v.get('name', v.get('id', str(v)[:50]))
                    else:
                        flat[k] = str(v)[:50] if v else ''
                parts.append(f"  {j+1}. {json.dumps(flat, ensure_ascii=False)}")
            if len(r.rows) > 10:
                parts.append(f"  ... 还有 {len(r.rows) - 10} 条结果")
        else:
            parts.append("未找到匹配结果")
    return "\n".join(parts)


def graph_search(
    store: GraphStore,
    question: str,
    max_results: int = 50,
) -> GraphSearchResponse:
    """Search the knowledge graph using natural language.

    Args:
        store: The GraphStore instance for the book.
        question: User's natural language question.
        max_results: Maximum number of results per sub-query.

    Returns:
        GraphSearchResponse with sub-questions, raw results, and synthesized answer.
    """
    response = GraphSearchResponse(original_question=question)

    # Step 1: Decompose question and generate Cypher
    prompt = f"## 用户问题\n{question}\n\n请分析问题，生成子问题和Cypher查询。输出JSON:"
    try:
        llm_response = llm_chat(prompt, system=SEARCH_SYSTEM_PROMPT, temperature=0.1, task="extraction")
        if not llm_response:
            response.error = "LLM returned empty response"
            return response
        j = extract_json_from_response(llm_response)
        plan = json.loads(j.strip())
    except (json.JSONDecodeError, ValueError) as e:
        response.error = f"Failed to parse LLM search plan: {e}"
        return response
    except Exception as e:
        response.error = f"LLM search plan generation failed: {e}"
        return response

    response.sub_questions = plan.get("sub_questions", [])
    queries = plan.get("queries", [])

    # Step 2: Execute each query
    params = {"pid": store.project_id, "name": question, "limit": max_results}
    for q in queries:
        sr = SearchResult(
            cypher=q.get("cypher", ""),
            explanation=q.get("explanation", ""),
            sub_question="",
        )
        sub_idx = q.get("sub_question_index", 0)
        if sub_idx < len(response.sub_questions):
            sr.sub_question = response.sub_questions[sub_idx]

        if sr.cypher:
            rows, err = _execute_cypher(store, sr.cypher, params)
            sr.rows = rows
            sr.error = err
        else:
            sr.error = "No Cypher query generated"

        response.results.append(sr)

    # Step 3: Synthesize answer
    if response.results and not response.error:
        synthesis_prompt = f"""## 用户问题\n{question}\n\n## 图谱查询结果\n{_format_results_for_llm(response.results)}\n\n请用中文简洁回答用户问题。如果查询结果不足以回答问题，请说明原因。"""
        try:
            answer = llm_chat(
                synthesis_prompt,
                system="你是小说知识图谱助手。根据图谱查询结果回答用户问题。如果信息不足，诚实说明。用中文回答，简洁明了。",
                temperature=0.2,
                task="extraction",
            )
            response.answer = answer or "（无法生成回答）"
        except Exception as e:
            response.answer = f"回答生成失败: {e}"
            response.error = str(e)

    return response


def quick_graph_search(store: GraphStore, question: str) -> str:
    """Simplified: search and return answer directly."""
    result = graph_search(store, question)
    if result.error and not result.answer:
        return f"搜索失败: {result.error}"
    return result.answer or "未找到相关信息"
