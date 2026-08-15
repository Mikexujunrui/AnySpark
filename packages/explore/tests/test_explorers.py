"""anyspark.explore.explorers — 并行探索引擎测试（fake model，无网络）。"""

from anyspark.core.types import Message, ModelOutput
from anyspark.explore import ExplorationEngine, ExplorationStrategy


class ScriptedExplorer:
    """每个探索者返回不同内容（验证并行多样性）。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.called = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        i = self.called
        self.called += 1
        return ModelOutput(text=self._replies[i % len(self._replies)])


def test_parallel_exploration() -> None:
    model = ScriptedExplorer(
        [
            '{"title": "方向A", "summary": "A说明", "term": "流派A"}',
            '{"title": "方向B", "summary": "B说明", "term": "流派B"}',
            '{"title": "方向C", "summary": "C说明", "term": "流派C"}',
            '{"title": "方向D", "summary": "D说明", "term": "流派D"}',
        ]
    )
    strategy = ExplorationStrategy(seed="s", intent_confirmed={"concept": {}})
    engine = ExplorationEngine(model, n_explorers=4)
    cards = engine.explore(strategy)

    assert len(cards) == 4
    titles = {c.title for c in cards}
    assert titles == {"方向A", "方向B", "方向C", "方向D"}
    # 维度/来源差异化（三来源混合）
    sources = {c.source for c in cards}
    assert "grow" in sources and "template" in sources and "user" in sources
    assert model.called == 4  # 4 次独立调用
