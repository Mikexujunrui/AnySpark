# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for foreshadow network and prophecy parser."""

from core.foreshadow_network import (
    FORESHADOW_REL_TYPES,
    EdgeType,
    ForeshadowEdge,
    ForeshadowNetwork,
    ForeshadowNode,
    ForeshadowType,
    PayoffNode,
    find_unresolved_foreshadows,
    get_outgoing_payoff_pairs,
)
from core.prophecy_parser import (
    build_foreshadow_from_prophecy,
    extract_prophecies_from_text,
)


class TestForeshadowType:
    def test_all_types_defined(self):
        """All foreshadow types should be accessible."""
        assert ForeshadowType.PROPHECY_POEM.value == "prophecy_poem"
        assert ForeshadowType.DIALOGUE_HINT.value == "dialogue_hint"
        assert ForeshadowType.BEHAVIOR_SYMBOL.value == "behavior_symbol"
        assert ForeshadowType.DREAM_OMEN.value == "dream_omen"
        assert ForeshadowType.NAMED_OMEN.value == "named_omen"
        assert len(list(ForeshadowType)) >= 6

    def test_edge_types(self):
        assert EdgeType.HINTS_AT.value == "HINTS_AT"
        assert EdgeType.PAID_OFF_BY.value == "PAID_OFF_BY"
        assert EdgeType.AMPLIFIES.value == "AMPLIFIES"
        assert EdgeType.RESOLVES_IN.value == "RESOLVES_IN"


class TestForeshadowNode:
    def test_basic_creation(self):
        node = ForeshadowNode(
            id="fs_001",
            type=ForeshadowType.PROPHECY_POEM,
            description="玉带林中挂，金簪雪里埋",
            source_chapter=5,
            linked_entities=["女主角", "女配角"],
            hints_at_outcomes=["女主泪尽", "女主守寡"],
        )
        assert node.id == "fs_001"
        assert node.type == ForeshadowType.PROPHECY_POEM
        assert len(node.linked_entities) == 2

    def test_to_neo4j_dict(self):
        node = ForeshadowNode(
            id="fs_001", type=ForeshadowType.DIALOGUE_HINT,
            description="你放心", source_chapter=34,
            linked_entities=["女主角"], hints_at_outcomes=["女主之死"],
        )
        nd = node.to_neo4j_dict()
        assert nd["entity_type"] == "foreshadow"
        assert nd["id"] == "fs_001"
        assert nd["data"]["confidence"] == 1.0


class TestPayoffNode:
    def test_basic_creation(self):
        payoff = PayoffNode(
            id="po_001", chapter=97,
            description="黛玉焚稿断痴情",
            related_foreshadows=["fs_001", "fs_005"],
        )
        assert payoff.chapter == 97
        assert len(payoff.related_foreshadows) == 2

    def test_to_neo4j_dict(self):
        payoff = PayoffNode(
            id="po_001", chapter=98,
            description="苦绛珠魂归离恨天",
            related_foreshadows=["fs_001"],
        )
        nd = payoff.to_neo4j_dict()
        assert nd["entity_type"] == "payoff"
        assert "魂归离恨天" in nd["name"]


class TestForeshadowEdge:
    def test_basic_creation(self):
        edge = ForeshadowEdge(
            foreshadow_id="fs_001",
            target_id="po_001",
            edge_type=EdgeType.PAID_OFF_BY,
            strength=0.85,
            evidence="批注：观此方知后文",
        )
        assert edge.foreshadow_id == "fs_001"
        assert edge.strength == 0.85


class TestFindUnresolved:
    def test_all_resolved(self):
        foreshadows = [
            ForeshadowNode(id="f1", type=ForeshadowType.EVENT_FORESHADOW,
                           description="v1", source_chapter=1,
                           linked_entities=[], hints_at_outcomes=[]),
        ]
        payoffs = [
            PayoffNode(id="p1", chapter=10, description="r",
                       related_foreshadows=["f1"]),
        ]
        edges = [
            ForeshadowEdge(foreshadow_id="f1", target_id="p1",
                           edge_type=EdgeType.PAID_OFF_BY),
        ]
        unresolved = find_unresolved_foreshadows(foreshadows, payoffs, edges)
        assert len(unresolved) == 0

    def test_some_unresolved(self):
        foreshadows = [
            ForeshadowNode(id="f1", type=ForeshadowType.EVENT_FORESHADOW,
                           description="v1", source_chapter=1,
                           linked_entities=[], hints_at_outcomes=[]),
            ForeshadowNode(id="f2", type=ForeshadowType.EVENT_FORESHADOW,
                           description="v2", source_chapter=2,
                           linked_entities=[], hints_at_outcomes=[]),
        ]
        payoffs = [
            PayoffNode(id="p1", chapter=10, description="r",
                       related_foreshadows=["f1"]),
        ]
        edges = [
            ForeshadowEdge(foreshadow_id="f1", target_id="p1",
                           edge_type=EdgeType.PAID_OFF_BY),
        ]
        unresolved = find_unresolved_foreshadows(foreshadows, payoffs, edges)
        assert len(unresolved) == 1
        assert unresolved[0].id == "f2"


class TestPayoffPairs:
    def test_get_outgoing(self):
        payoffs = [
            PayoffNode(id="p1", chapter=10, description="r1",
                       related_foreshadows=["f1"]),
            PayoffNode(id="p2", chapter=15, description="r2",
                       related_foreshadows=["f1"]),
        ]
        edges = [
            ForeshadowEdge(foreshadow_id="f1", target_id="p1",
                           edge_type=EdgeType.PAID_OFF_BY),
            ForeshadowEdge(foreshadow_id="f1", target_id="p2",
                           edge_type=EdgeType.PAID_OFF_BY),
        ]
        pairs = get_outgoing_payoff_pairs("f1", edges, payoffs)
        assert len(pairs) == 2


class TestForeshadowNetwork:
    def test_network_summary(self):
        network = ForeshadowNetwork(
            book_id="hlm",
            foreshadow_count=5,
            payoff_count=3,
            unresolved_count=2,
        )
        d = network.to_dict()
        assert d["foreshadow_count"] == 5
        assert d["unresolved_count"] == 2
        prompt = network.to_prompt_fragment()
        assert isinstance(prompt, str)

    def test_rel_types_registered(self):
        assert "HINTS_AT" in FORESHADOW_REL_TYPES
        assert "PAID_OFF_BY" in FORESHADOW_REL_TYPES
        assert "AMPLIFIES" in FORESHADOW_REL_TYPES
        assert "RESOLVES_IN" in FORESHADOW_REL_TYPES


# ── ProphecyParser tests ────────────────────────────────────────────────


class TestProphecyParser:
    def test_extract_prophecy_poem(self):
        text = "判词：玉带林中挂，金簪雪里埋。"
        results = extract_prophecies_from_text(text)
        assert len(results) > 0
        prophecy_types = {r["type"].value for r in results}
        assert "prophecy_poem" in prophecy_types

    def test_extract_dream_omen(self):
        text = "公子梦见仙人，恍惚中见一大石牌坊。"
        results = extract_prophecies_from_text(text)
        dream_types = {r["type"].value for r in results}
        assert "dream_omen" in dream_types

    def test_extract_lantern_riddle(self):
        text = "灯谜：阶下儿童仰面时，清明妆点最堪宜。"
        results = extract_prophecies_from_text(text)
        assert len(results) > 0

    def test_build_foreshadow_from_prophecy(self):
        prophecy = {
            "type": "prophecy_poem",
            "raw_text": "玉带林中挂，金簪雪里埋",
        }
        from core.foreshadow_network import ForeshadowType
        prophecy["type"] = ForeshadowType.PROPHECY_POEM
        node = build_foreshadow_from_prophecy(prophecy, source_chapter=5)
        assert node.type == ForeshadowType.PROPHECY_POEM
        assert node.source_chapter == 5
        assert len(node.linked_entities) == 0  # 无 linked_entity_hints 时为空

    def test_build_foreshadow_with_hints(self):
        prophecy = {
            "type": "prophecy_poem",
            "raw_text": "玉带林中挂，金簪雪里埋",
        }
        from core.foreshadow_network import ForeshadowType
        prophecy["type"] = ForeshadowType.PROPHECY_POEM
        hints = {"女主角": ["玉带林中挂"]}
        node = build_foreshadow_from_prophecy(
            prophecy, source_chapter=5,
            linked_entity_hints=hints,
        )
        assert "女主角" in node.linked_entities
