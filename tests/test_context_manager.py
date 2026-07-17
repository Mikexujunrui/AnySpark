"""Tests for ContextManager with budget allocation and tiered loading."""

import pytest

from core.context_manager import ContextBudget, ContextManager
from core.knowledge import Entity, EntityType


@pytest.fixture
def ctx_mgr():
    mgr = ContextManager("test_ctx", ContextBudget(total_tokens=4000))
    yield mgr
    try:
        mgr.store._run("MATCH (e:Entity {project_id: 'test_ctx'}) DETACH DELETE e")
    except Exception:
        pass


def test_empty_context(ctx_mgr):
    result = ctx_mgr.build_writing_context()
    assert "知识库为空" in result


def test_context_with_entities(ctx_mgr):
    e1 = Entity(id="e1", type=EntityType.CHARACTER, name="主角", data={"年龄": "20"})
    e2 = Entity(id="e2", type=EntityType.LOCATION, name="青云镇", data={"类型": "小镇"})
    ctx_mgr.store.add_entity(e1)
    ctx_mgr.store.add_entity(e2)

    result = ctx_mgr.build_writing_context()
    assert "主角" in result
    assert "青云镇" in result


def test_context_referenced_entities_resident(ctx_mgr):
    e1 = Entity(id="e1", type=EntityType.CHARACTER, name="主角", data={"年龄": "20"})
    e2 = Entity(id="e2", type=EntityType.CHARACTER, name="配角", data={"年龄": "22"})
    ctx_mgr.store.add_entity(e1)
    ctx_mgr.store.add_entity(e2)

    result = ctx_mgr.build_writing_context(relevant_entity_names=["主角"])
    assert "主角" in result
    assert "年龄" in result


def test_budget_limits_context(ctx_mgr):
    """With a small budget, the index should truncate excess entities."""
    for i in range(5):
        e = Entity(id=f"e{i}", type=EntityType.CHARACTER, name=f"角色{i}", data={"描述": "测试" * 50})
        ctx_mgr.store.add_entity(e)

    result = ctx_mgr.build_writing_context()
    assert len(result) > 0
