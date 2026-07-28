"""Tests for NarratorAgent — dual-mode推演 orchestrator with SSE.

Tests the SSE event generation flow and graph-driven option generation
with mocked CharacterAgent and GraphStore.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.simulation.character_agent import CharacterProfile
from core.simulation.narrator_agent import NarratorAgent
from core.simulation.simulation_store import SimulationStore


@pytest.fixture
def mock_store(tmp_path, monkeypatch):
    """Create a SimulationStore with JSON fallback."""
    monkeypatch.setattr("core.simulation.simulation_store.DATA_DIR", tmp_path)
    s = SimulationStore("test_book")
    s._neo4j_ok = False
    s._json_dir = tmp_path / "simulations"
    s._json_dir.mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture
def mock_profile():
    """Create a test CharacterProfile."""
    return CharacterProfile(
        character_id="char_001",
        name="张三",
        personality="沉稳的剑客",
        skills=["剑术"],
        system_prompt="你是张三。",
    )


@pytest.fixture
def narrator(mock_store, mock_profile):
    """Create a NarratorAgent with mocked dependencies."""
    n = NarratorAgent("test_book")
    n.store = mock_store
    # Mock graph
    n.graph = MagicMock()
    n.graph.get_graph_insights.return_value = {
        "forgotten_characters": [{"name": "王五"}],
        "unresolved_foreshadows": [{"text": "神秘信物的来历"}],
    }
    n.graph._run.return_value = []
    # Mock character agent
    n.char_agent = MagicMock()
    n.char_agent.build_profile.return_value = mock_profile
    n.char_agent.build_profiles_batch.return_value = {"char_001": mock_profile}
    return n


def test_generate_graph_insight_options(narrator):
    """Test graph-driven option generation."""
    options = narrator._generate_graph_insight_options("sim_test", "测试上下文")
    assert len(options) > 0
    assert len(options) <= 4

    # Check that forgotten character option exists
    forgotten_opts = [o for o in options if "王五" in o.get("text", "")]
    assert len(forgotten_opts) > 0

    # Check that foreshadow option exists
    foreshadow_opts = [o for o in options if "伏笔" in o.get("text", "")]
    assert len(foreshadow_opts) > 0


def test_generate_graph_insight_options_fallback(narrator):
    """Test fallback options when graph has no insights."""
    narrator.graph.get_graph_insights.return_value = {}
    options = narrator._generate_graph_insight_options("sim_test", "测试")
    # Should have at least 2 fallback options
    assert len(options) >= 2
    texts = [o.get("text", "") for o in options]
    assert any("继续" in t for t in texts)


def test_build_synthesis_prompt_character_pov(narrator, mock_profile):
    """Test synthesis context building for character POV mode."""
    char_responses = [
        {
            "character_name": "张三",
            "perception": "看到前方有人",
            "thoughts": "是敌是友？",
            "action": "拔剑警戒",
            "dialogue": "来者何人？",
        }
    ]
    context = narrator._build_synthesis_prompt(
        mode="character_pov",
        sim_id="test_sim",
        char_responses=char_responses,
        history=[],
        setting="城门口",
        pov_profile=mock_profile,
    )
    assert "张三" in context
    assert "拔剑警戒" in context
    assert "来者何人？" in context
    assert "角色主视角" in context


def test_build_synthesis_prompt_narrator_pov(narrator):
    """Test synthesis context building for narrator POV mode."""
    char_responses = [
        {"character_name": "张三", "action": "拔剑", "dialogue": "来者何人？"},
        {"character_name": "李四", "action": "后退", "dialogue": "且慢！"},
    ]
    context = narrator._build_synthesis_prompt(
        mode="narrator_pov",
        sim_id="test_sim",
        char_responses=char_responses,
        history=[],
        setting="城门口",
    )
    assert "张三" in context
    assert "李四" in context
    assert "叙事者全知视角" in context


@pytest.mark.asyncio
async def test_character_pov_turn_sse_events(narrator, mock_store, mock_profile):
    """Test that character POV turn generates correct SSE event sequence."""
    # Setup session
    session = mock_store.create_session(
        mode="character_pov",
        setting="城门口",
        pov_character_id="char_001",
    )

    # Mock character agent respond
    narrator.char_agent.respond = AsyncMock(
        return_value={
            "perception": "看到旧友",
            "thoughts": "多年未见",
            "action": "上前打招呼",
            "dialogue": "好久不见！",
        }
    )

    # Mock LLM streaming — plain text narrative (not JSON)
    mock_narrative = "张三走上前去，认出了多年未见的老友。两人相视而笑，千言万语尽在不言中。"

    async def mock_stream(*args, **kwargs):
        for chunk in [mock_narrative[i : i + 20] for i in range(0, len(mock_narrative), 20)]:
            yield chunk

    # Mock options generation (separate non-streaming call)
    mock_options = [
        {"text": "询问近况", "description": "关心老友"},
        {"text": "切磋武艺", "description": "以武会友"},
    ]

    async def mock_gen_options(*args, **kwargs):
        return mock_options, "张三面临选择，你决定："

    with (
        patch.object(narrator, "_stream_llm", side_effect=mock_stream),
        patch.object(narrator, "_generate_options", side_effect=mock_gen_options),
    ):
        events = []
        async for event in narrator.process_turn(
            sim_id=session["id"],
            choice_text="走向城门",
        ):
            events.append(event)

    # Verify SSE event sequence
    event_types = [e["type"] for e in events]
    assert "character_thinking" in event_types
    assert "character_response" in event_types
    assert "narrator_synthesizing" in event_types
    assert "narrative_chunk" in event_types
    assert "choices_ready" in event_types
    assert "done" in event_types

    # Verify character response event
    char_resp_event = next(e for e in events if e["type"] == "character_response")
    assert char_resp_event["character"] == "张三"
    assert char_resp_event["data"]["action"] == "上前打招呼"

    # Verify choices were stored
    choices_event = next(e for e in events if e["type"] == "choices_ready")
    assert len(choices_event["choices"]) == 2


@pytest.mark.asyncio
async def test_narrator_pov_turn_parallel_characters(narrator, mock_store):
    """Test narrator POV mode with multiple characters responding in parallel."""
    profile_a = CharacterProfile(character_id="char_a", name="张三", system_prompt="你是张三")
    profile_b = CharacterProfile(character_id="char_b", name="李四", system_prompt="你是李四")

    narrator.char_agent.build_profiles_batch.return_value = {
        "char_a": profile_a,
        "char_b": profile_b,
    }

    # Mock parallel responses
    async def mock_respond(profile, situation, history=None, mode="narrator_pov"):
        if profile.name == "张三":
            return {
                "perception": "感知到威胁",
                "thoughts": "必须保护家人",
                "action": "拔剑戒备",
                "dialogue": "谁敢来犯！",
            }
        else:
            return {
                "perception": "看到张三紧张",
                "thoughts": "出了什么事",
                "action": "询问情况",
                "dialogue": "张兄，怎么了？",
            }

    narrator.char_agent.respond = mock_respond

    # Setup session
    session = mock_store.create_session(
        mode="narrator_pov",
        condition="敌军来袭",
        involved_character_ids=["char_a", "char_b"],
    )

    # Mock LLM streaming — plain text narrative (not JSON)
    mock_narrative = "张三拔剑戒备，李四疑惑询问。空气中弥漫着紧张的气氛。"

    async def mock_stream(*args, **kwargs):
        yield mock_narrative

    # Mock options generation
    mock_options = [
        {"text": "敌军发起进攻", "description": "战斗开始"},
    ]

    async def mock_gen_options(*args, **kwargs):
        return mock_options, "局势紧张，接下来会发生什么？"

    with (
        patch.object(narrator, "_stream_llm", side_effect=mock_stream),
        patch.object(narrator, "_generate_options", side_effect=mock_gen_options),
    ):
        events = []
        async for event in narrator.process_turn(
            sim_id=session["id"],
            choice_text="敌军来袭",
        ):
            events.append(event)

    [e["type"] for e in events]

    # Should have two character_thinking events (one per character)
    thinking_events = [e for e in events if e["type"] == "character_thinking"]
    assert len(thinking_events) == 2

    # Should have two character_response events
    response_events = [e for e in events if e["type"] == "character_response"]
    assert len(response_events) == 2

    # Verify both characters responded
    char_names = [e["character"] for e in response_events]
    assert "张三" in char_names
    assert "李四" in char_names

    # Choices should be "condition" type
    choices_event = next(e for e in events if e["type"] == "choices_ready")
    assert choices_event["choices"][0]["choice_type"] == "condition"


def test_get_open_foreshadows(narrator):
    """Test fetching open foreshadows."""
    narrator.graph._run.return_value = [
        {"f": {"id": "fore_1", "text": "神秘信物", "resolved": False}},
        {"f": {"id": "fore_2", "text": "失踪的师妹", "resolved": False}},
    ]
    foreshadows = narrator._get_open_foreshadows()
    assert len(foreshadows) == 2
    assert foreshadows[0]["text"] == "神秘信物"
