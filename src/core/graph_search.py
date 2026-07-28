"""Graph semantic search — LLM-driven question answering over the knowledge graph.

Decomposes user questions into sub-questions, generates SQL queries,
executes them, and synthesizes results.

This implementation uses:
- LLM for question decomposition -> sub-questions
- LLM for SQL generation
- SQLite FTS for text search fallback
- LLM for result synthesis
"""

import json
import logging
from dataclasses import dataclass, field

from .llm_client import chat as llm_chat
from .utils import extract_json_from_response

logger = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = """你是一位SQLite数据库查询专家。你正在处理一个小说知识图谱，使用关系型表存储：

## 表结构

### entities (实体/节点)
- id TEXT PRIMARY KEY — 唯一ID
- entity_type TEXT — 类型: character|location|item|skill|organization|race|concept|event
- name TEXT — 名称
- aliases TEXT — JSON数组, 如 '["别名1","别名2"]'
- data TEXT — JSON字典, 存放额外属性
- project_id TEXT — 项目ID (查询时一定要用此过滤)

### relations (关系/边)
- id TEXT PRIMARY KEY
- from_entity TEXT — 起点实体ID (关联entities.id)
- to_entity TEXT — 终点实体ID (关联entities.id)
- type TEXT — 关系类型: KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|LOVES|MENTOR_OF|MASTER_OF|KILLED|SAVED|OWNS|BELONGS_TO|LOCATED_AT|LOCATED_IN|ADJACENT_TO|CAUSES|BEFORE|AFTER|FORESHADOWS|RESOLVES|PARTICIPATES_IN|PARENT_OF|CHILD_OF|SPOUSE_OF|SIBLING_OF|FRIEND
- data TEXT — JSON字典
- project_id TEXT

### foreshadows (伏笔)
- id, text, hint, expected_resolution, resolved(0/1), status, confidence, project_id

### timeline_events (时间线事件)
- id, label, time_order, description, chapter_ref, track_id, location_ref, project_id

## 常用查询模式
1. 查角色: SELECT * FROM entities WHERE entity_type='character' AND project_id=?
2. 查关系: SELECT r.type, e2.name FROM relations r JOIN entities e1 ON r.from_entity=e1.id JOIN entities e2 ON r.to_entity=e2.id WHERE e1.name=? AND r.project_id=?
3. 模糊搜名: SELECT * FROM entities WHERE name LIKE ? AND project_id=?
4. 查角色关系网络: SELECT r.type, e.name AS related_entity FROM relations r JOIN entities e ON r.to_entity=e.id WHERE r.from_entity IN (SELECT id FROM entities WHERE name=? AND project_id=?) AND r.project_id=?

## 任务
根据用户问题，生成一个或多个SQL查询来回答。输出JSON格式：

```json
{
  "sub_questions": ["分解后的子问题1", "子问题2"],
  "queries": [
    {
      "sql": "SELECT ... WHERE project_id=? LIMIT 50",
      "explanation": "这个查询做什么",
      "sub_question_index": 0
    }
  ],
  "synthesis_hint": "如何综合结果回答"
}
```

## 规则
1. 必须使用 project_id=? 过滤
2. 使用 LIMIT 50 限制返回数量
3. 对于实体名查询，使用 LIKE '%关键词%'
4. JSON字段用 json_extract() 或程序解析
5. 子查询比JOIN更清晰时优先使用子查询
6. query 和 sub_question 必须一一对应
"""


@dataclass
class SearchResult:
    """A single search result."""

    sub_question: str = ""
    sql: str = ""
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


def _execute_query(store, sql: str, params: dict) -> tuple[list[dict], str]:
    """Execute a SQL query with error handling.

    Works with both SQLiteStore (tuple params) and legacy Neo4j GraphStore (dict params).
    """
    try:
        # SQLiteStore._run expects tuple; legacy GraphStore._run expects dict
        # Try tuple first (SQLite), fall back to dict (Neo4j)
        if hasattr(store, "_conn") and hasattr(store._conn, "execute"):
            # It's an SQLiteStore — convert params dict to tuple
            # Extract known params like project_id, limit, name
            pid = params.get("pid", store.project_id)
            limit = params.get("limit", 50)
            name = params.get("name", "")

            # Try to execute with positional params
            import sqlite3

            try:
                cursor = store._conn.execute(sql, (pid, limit, name))
                rows = cursor.fetchall()
            except sqlite3.Error:
                # Fall back to named params
                cursor = store._conn.execute(sql, params)
                rows = cursor.fetchall()

            # Convert to plain dicts
            result = [dict(r) for r in rows]
        else:
            # Legacy Neo4j path
            rows = store._run(sql, params)
            result = []
            for row in rows:
                d = {}
                for key, value in row.items():
                    if hasattr(value, "_properties"):
                        d[key] = dict(value._properties)
                        d[key]["_labels"] = list(value.labels) if hasattr(value, "labels") else []
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
        parts.append(f"\n### 子问题{i + 1}: {r.sub_question}")
        if r.error:
            parts.append(f"查询失败: {r.error}")
        elif r.rows:
            parts.append(f"SQL: {r.sql}")
            parts.append(f"结果 ({len(r.rows)}条):")
            for j, row in enumerate(r.rows[:10]):
                flat = {}
                for k, v in row.items():
                    if isinstance(v, dict):
                        flat[k] = v.get("name", v.get("id", str(v)[:50]))
                    else:
                        flat[k] = str(v)[:50] if v else ""
                parts.append(f"  {j + 1}. {json.dumps(flat, ensure_ascii=False)}")
            if len(r.rows) > 10:
                parts.append(f"  ... 还有 {len(r.rows) - 10} 条结果")
        else:
            parts.append("未找到匹配结果")
    return "\n".join(parts)


def graph_search(
    store,
    question: str,
    max_results: int = 50,
) -> GraphSearchResponse:
    """Search the knowledge graph using natural language.

    Args:
        store: The SQLiteStore (or legacy GraphStore) instance.
        question: User's natural language question.
        max_results: Maximum number of results per sub-query.

    Returns:
        GraphSearchResponse with sub-questions, raw results, and synthesized answer.
    """
    response = GraphSearchResponse(original_question=question)

    # Step 1: Decompose question and generate SQL
    prompt = f"## 用户问题\n{question}\n\n请分析问题，生成子问题和SQL查询。输出JSON:"
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
            sql=q.get("sql", ""),
            explanation=q.get("explanation", ""),
            sub_question="",
        )
        sub_idx = q.get("sub_question_index", 0)
        if sub_idx < len(response.sub_questions):
            sr.sub_question = response.sub_questions[sub_idx]

        if sr.sql:
            rows, err = _execute_query(store, sr.sql, params)
            sr.rows = rows
            sr.error = err
        else:
            sr.error = "No SQL query generated"

        response.results.append(sr)

    # Step 3: Synthesize answer
    if response.results and not response.error:
        synthesis_prompt = (
            f"## 用户问题\n{question}\n\n"
            f"## 图谱查询结果\n{_format_results_for_llm(response.results)}\n\n"
            "请用中文简洁回答用户问题。如果查询结果不足以回答问题，请说明原因。"
        )
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


def quick_graph_search(store, question: str) -> str:
    """Simplified: search and return answer directly."""
    result = graph_search(store, question)
    if result.error and not result.answer:
        return f"搜索失败: {result.error}"
    return result.answer or "未找到相关信息"
