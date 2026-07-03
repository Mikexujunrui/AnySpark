"""Tests for CharacterAgent — lightweight character agent with graph-driven profiles.

Mocks GraphStore and llm_chat for CI compatibility (no Neo4j or LLM required).
"""

import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from core.knowledge import Entity, EntityType
from core.simulation.character_agent import CharacterAgent, CharacterProfile


@pytest.fixture
def mock_graph():
    """Create a mock GraphStore."""
    graph = MagicMock()
    # Default: return a test character entity
    graph.get_entity.return_value = Entity(
        id="char_001",
        type=EntityType.CHARACTER,
        name="张三",
        aliases=["小张"],
        data={
            "description": "一个沉稳的剑客，性格内敛但重情义。",
            "skills": ["剑术", "轻功"],
        },
    )
    # Default: no phase snapshot
    graph._run.return_value = []
    return graph


@pytest.fixture
def agent(mock_graph):
    """Create a CharacterAgent with mocked graph."""
    a = CharacterAgent("test_book")
    a.graph = mock_graph
    return a


def test_build_profile_basic(agent, mock_graph):
    """Test basic profile building from entity data."""
    profile = agent.build_profile("char_001")
    assert profile is not None
    assert profile.character_id == "char_001"
    assert profile.name == "张三"
    assert "沉稳的剑客" in profile.personality
    assert "剑术" in profile.skills
    assert "轻功" in profile.skills


def test_build_profile_with_phase(agent, mock_graph):
    """Test profile building with phase snapshot."""
    mock_graph._run.return_value = [{
        "s": {
            "phase": "第一部·觉醒",
            "label": "觉醒",
            "data": {
                "personality": "经历变故后更加沉稳",
                "motivation": "寻找失散的师妹",
                "appearance": "一身黑衣",
                "growth_note": "从冲动少年成长为沉稳剑客",
            },
            "is_current": True,
            "time_order": 2,
        }
    }]

    profile = agent.build_profile("char_001")
    assert profile is not None
    assert profile.current_phase is not None
    assert profile.current_phase["phase"] == "第一部·觉醒"
    assert "经历变故后更加沉稳" in profile.personality
    assert "寻找失散的师妹" in profile.system_prompt


def test_build_profile_with_relationships(agent, mock_graph):
    """Test profile building with character relationships."""
    # Mock relationship queries
    call_count = [0]

    def mock_run(query, params):
        call_count[0] += 1
        if "HAS_PHASE" in query:
            return []
        elif "outgoing" in query:
            return [{
                "name": "李四",
                "target_id": "char_002",
                "rel_type": "ALLY",
                "direction": "outgoing",
            }]
        elif "incoming" in query:
            return [{
                "name": "王五",
                "target_id": "char_003",
                "rel_type": "ANTAGONIST",
                "direction": "incoming",
            }]
        return []

    mock_graph._run.side_effect = mock_run

    profile = agent.build_profile("char_001")
    assert profile is not None
    assert len(profile.relationships) == 2
    names = [r["target_name"] for r in profile.relationships]
    assert "李四" in names
    assert "王五" in names
    # Check that relationship info is in the system prompt
    assert "李四" in profile.system_prompt
    assert "盟友" in profile.system_prompt


def test_build_profile_entity_not_found(agent, mock_graph):
    """Test profile building when entity doesn't exist."""
    mock_graph.get_entity.return_value = None
    profile = agent.build_profile("nonexistent")
    assert profile is None


def test_system_prompt_contains_constraints(agent):
    """Test that the system prompt contains behavioral constraints."""
    profile = agent.build_profile("char_001")
    assert "你必须执行它" in profile.system_prompt
    assert "张三" in profile.system_prompt
    assert "剑术" in profile.system_prompt


def test_profile_to_dict(agent):
    """Test that profile can be serialized to dict."""
    profile = agent.build_profile("char_001")
    d = profile.to_dict()
    assert d["character_id"] == "char_001"
    assert d["name"] == "张三"
    assert "personality" in d
    assert isinstance(d["skills"], list)


@pytest.mark.asyncio
async def test_respond_returns_structured_data(agent):
    """Test that respond() returns structured character response."""
    mock_response = json.dumps({
        "perception": "我看到前方有一队人马",
        "thoughts": "这是敌是友？",
        "action": "隐蔽在树后观察",
        "dialogue": "",
    })

    with patch("core.simulation.character_agent.llm_chat", return_value=mock_response):
        profile = agent.build_profile("char_001")
        result = await agent.respond(
            profile=profile,
            situation="前方出现一队人马",
            mode="character_pov",
        )

    assert result["perception"] == "我看到前方有一队人马"
    assert result["thoughts"] == "这是敌是友？"
    assert result["action"] == "隐蔽在树后观察"
    assert result["dialogue"] == ""


@pytest.mark.asyncio
async def test_respond_handles_llm_failure(agent):
    """Test that respond() handles LLM errors gracefully."""
    with patch("core.simulation.character_agent.llm_chat", side_effect=Exception("API error")):
        profile = agent.build_profile("char_001")
        result = await agent.respond(
            profile=profile,
            situation="测试情境",
        )

    assert "失败" in result["perception"]
    assert result["action"] == "无"


@pytest.mark.asyncio
async def test_respond_handles_invalid_json(agent):
    """Test that respond() handles invalid JSON responses."""
    with patch("core.simulation.character_agent.llm_chat", return_value="这不是JSON格式的内容"):
        profile = agent.build_profile("char_001")
        result = await agent.respond(
            profile=profile,
            situation="测试情境",
        )

    # Should fall back to using raw text as action
    assert "这不是JSON格式的内容" in result["action"]


def test_build_profiles_batch(agent, mock_graph):
    """Test batch profile building."""
    # Mock get_entity to return different entities for different IDs
    def get_entity(eid):
        if eid == "char_001":
            return Entity(id="char_001", type=EntityType.CHARACTER, name="张三",
                          data={"description": "剑客"})
        elif eid == "char_002":
            return Entity(id="char_002", type=EntityType.CHARACTER, name="李四",
                          data={"description": "书生"})
        return None

    mock_graph.get_entity.side_effect = get_entity
    mock_graph._run.return_value = []

    profiles = agent.build_profiles_batch(["char_001", "char_002", "nonexistent"])
    assert len(profiles) == 2
    assert "char_001" in profiles
    assert "char_002" in profiles
    assert profiles["char_001"].name == "张三"
    assert profiles["char_002"].name == "李四"
