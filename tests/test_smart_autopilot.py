"""Tests for smart autopilot features: intent classification, context accumulator, replan."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.autopilot import (
    AutopilotConfig,
    AutopilotPlanner,
    _classify_intent,
    _parse_chapter_indices,
)
from core.headless_loop import StepContextAccumulator
from core.task_queue import PersistentTask, TaskQueue, TaskStatus, TaskStep

# ── Intent Classification ──

class TestIntentClassification:
    """Test rule-based intent classification."""

    def test_classify_write_new(self):
        intent = _classify_intent("按大纲写完这本书", {})
        assert intent.intent_type == "write_new"
        assert intent.requires_writing is True
        assert intent.requires_outline is True

    def test_classify_write_new_continuation(self):
        intent = _classify_intent("续写后5章", {})
        assert intent.intent_type == "write_new"

    def test_classify_batch_edit(self):
        intent = _classify_intent("把第3-8章改得更紧凑", {})
        assert intent.intent_type == "batch_edit"
        assert intent.requires_edit is True

    def test_classify_batch_edit_modify(self):
        intent = _classify_intent("修改这几章的节奏", {})
        assert intent.intent_type == "batch_edit"

    def test_classify_global_replace(self):
        intent = _classify_intent("全书的小姐改成姑娘", {})
        assert intent.intent_type == "global_replace"

    def test_classify_global_replace_terminate(self):
        intent = _classify_intent("把所有'他'替换成'她'", {})
        assert intent.intent_type == "global_replace"

    def test_classify_style_change(self):
        intent = _classify_intent("全书改成古风文风", {})
        assert intent.intent_type == "style_change"

    def test_classify_targeted_edit(self):
        intent = _classify_intent("重写第3章让主角更立体", {})
        assert intent.intent_type == "targeted_edit"

    def test_classify_targeted_edit_single(self):
        intent = _classify_intent("把第5章结尾和第6章开头衔接好", {})
        assert intent.intent_type == "targeted_edit"

    def test_classify_analysis(self):
        intent = _classify_intent("检查全书时间线矛盾", {})
        assert intent.intent_type == "analysis"
        assert intent.requires_analysis is True

    def test_classify_analysis_consistency(self):
        intent = _classify_intent("分析全书一致性", {})
        assert intent.intent_type == "analysis"

    def test_classify_insert_content(self):
        intent = _classify_intent("在每章合适的地方加入天气描写", {})
        assert intent.intent_type == "insert_content"

    def test_classify_insert_supplement(self):
        intent = _classify_intent("在每章补充伏笔描写", {})
        assert intent.intent_type == "insert_content"

    def test_classify_mixed_fallback(self):
        """Unrecognizable instructions should fall back to mixed."""
        intent = _classify_intent("帮我把这个项目做好", {})
        assert intent.intent_type == "mixed"

    def test_classify_sequential_dependency(self):
        """Batch edit with coherence keywords should be sequential."""
        intent = _classify_intent("把第3-8章改得更连贯，前后呼应", {})
        assert intent.intent_type == "batch_edit"
        assert intent.sequential_dependency is True

    def test_classify_write_new_always_sequential(self):
        intent = _classify_intent("按大纲写完全书", {})
        assert intent.sequential_dependency is True


class TestChapterIndexParsing:
    """Test chapter index extraction from instructions."""

    def test_parse_hash_range(self):
        indices = _parse_chapter_indices("#3-#8")
        assert indices == [3, 4, 5, 6, 7, 8]

    def test_parse_hash_tilde_range(self):
        indices = _parse_chapter_indices("#3~#6")
        assert indices == [3, 4, 5, 6]

    def test_parse_chinese_range(self):
        indices = _parse_chapter_indices("第3-8章")
        assert indices == [3, 4, 5, 6, 7, 8]

    def test_parse_chinese_to_range(self):
        indices = _parse_chapter_indices("第3到8章")
        assert indices == [3, 4, 5, 6, 7, 8]

    def test_parse_hash_list(self):
        indices = _parse_chapter_indices("#3,#5,#7")
        assert indices == [3, 5, 7]

    def test_parse_single_chinese(self):
        indices = _parse_chapter_indices("第3章")
        assert indices == [3]

    def test_parse_no_indices(self):
        indices = _parse_chapter_indices("写完全书")
        assert indices == []

    def test_parse_dedup_and_sort(self):
        indices = _parse_chapter_indices("#5,#3,#5,#7")
        assert indices == [3, 5, 7]


# ── Planner Dispatch ──

class TestPlannerDispatch:
    """Test that plan() dispatches to correct builder based on intent."""

    @pytest.mark.asyncio
    async def test_plan_write_new(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {
            "chapters": [{"title": "第一章"}, {"title": "第二章"}]
        })
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="按大纲写完这本书",
            confirm_before_start=True,
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "write_new"
        assert plan["estimated_chapters"] == 2

    @pytest.mark.asyncio
    async def test_plan_global_replace(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [
            {"index": 1, "content": "x"}, {"index": 2, "content": "y"}
        ])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="把全书的小姐改成姑娘",
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "global_replace"
        # Should have find_replace_book step
        assert any("find_replace" in str(s.config.get("prompt", "")) for s in plan["steps"])

    @pytest.mark.asyncio
    async def test_plan_batch_edit(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [
            {"index": i, "content": f"chapter {i}"} for i in range(1, 10)
        ])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="把第3-5章改得更紧凑",
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "batch_edit"

    @pytest.mark.asyncio
    async def test_plan_targeted_edit(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [
            {"index": 3, "title": "第三章", "content": "x"}
        ])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="重写第3章让主角更立体",
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "targeted_edit"
        # Should have analyze + edit + checkpoint steps
        labels = [s.label for s in plan["steps"]]
        assert any("分析" in label for label in labels)
        assert any("精修" in label for label in labels)

    @pytest.mark.asyncio
    async def test_plan_analysis(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [
            {"index": i, "content": f"ch{i}"} for i in range(1, 5)
        ])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="检查全书时间线矛盾",
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "analysis"

    @pytest.mark.asyncio
    async def test_plan_style_change(self, tmp_data_dir, monkeypatch):
        from data.json_store import json_store
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test", instruction="全书改成古风文风",
        )
        plan = await planner.plan(config)
        assert plan["intent_type"] == "style_change"


# ── Step Context Accumulator ──

class TestStepContextAccumulator:
    """Test context passing between steps."""

    def test_record_and_retrieve(self):
        acc = StepContextAccumulator()
        step = TaskStep(id="s1", type="agent_loop", label="规划第1章",
                        config={"chapter_index": 1})
        result = {"text": "本章规划: 主角出场, 冲突引入", "success": True}
        acc.record("s1", step, result)

        assert "s1" in acc._results
        assert acc._results["s1"]["text"] == "本章规划: 主角出场, 冲突引入"

    def test_chapter_output_tracking(self):
        acc = StepContextAccumulator()
        step = TaskStep(id="s1", type="agent_loop", label="写作第1章",
                        config={"chapter_index": 1})
        result = {"text": "正文内容..." * 100}
        acc.record("s1", step, result)

        assert 1 in acc._chapter_outputs
        assert len(acc._chapter_outputs[1]) <= 500

    def test_build_context_injection_recent_steps(self):
        acc = StepContextAccumulator()
        for i in range(4):
            step = TaskStep(id=f"s{i}", type="agent_loop", label=f"步骤{i}",
                            config={})
            acc.record(f"s{i}", step, {"text": f"结果{i}"})

        target_step = TaskStep(id="s4", type="agent_loop", label="下一步",
                               config={})
        context = acc.build_context_injection(target_step, [])

        assert "最近完成的步骤" in context
        # Should show last 3 steps (not all 4)
        assert "步骤1" in context
        assert "步骤2" in context
        assert "步骤3" in context

    def test_build_context_injection_previous_chapter(self):
        acc = StepContextAccumulator()
        # Record chapter 1 output
        step1 = TaskStep(id="s1", type="agent_loop", label="写作第1章",
                         config={"chapter_index": 1})
        acc.record("s1", step1, {"text": "第1章的内容..."})

        # Build context for chapter 2
        step2 = TaskStep(id="s2", type="agent_loop", label="写作第2章",
                         config={"chapter_index": 2})
        context = acc.build_context_injection(step2, [])

        assert "前一章(第1章)摘要" in context
        assert "第1章的内容" in context

    def test_build_context_injection_empty(self):
        acc = StepContextAccumulator()
        step = TaskStep(id="s1", type="agent_loop", label="第一步", config={})
        context = acc.build_context_injection(step, [])
        assert context == ""

    def test_build_context_injection_explicit_bindings(self):
        acc = StepContextAccumulator()
        # Record a planning step
        plan_step = TaskStep(id="plan_s0", type="agent_loop", label="规划",
                             config={})
        acc.record("plan_s0", plan_step, {"text": "主角出场, 引入冲突"})

        # Build context with explicit binding
        write_step = TaskStep(id="write_s1", type="agent_loop", label="写作",
                              config={
                                  "context_bindings": [{
                                      "source_step_id": "plan_s0",
                                      "binding_type": "summary",
                                      "template": "规划结果: {result}",
                                  }]
                              })
        context = acc.build_context_injection(write_step, [])
        assert "规划结果:" in context
        assert "主角出场" in context

    def test_extract_summary_truncation(self):
        acc = StepContextAccumulator()
        long_text = "x" * 500
        summary = acc._extract_summary({"text": long_text}, max_len=300)
        assert len(summary) <= 303  # 300 + "..."

    def test_recent_steps_limit(self):
        acc = StepContextAccumulator()
        for i in range(10):
            step = TaskStep(id=f"s{i}", type="agent_loop", label=f"步骤{i}",
                            config={})
            acc.record(f"s{i}", step, {"text": f"结果{i}"})

        assert len(acc._recent_steps) == 5  # Max 5 recent


# ── Replace Remaining Steps ──

class TestReplaceRemainingSteps:
    """Test task_queue.replace_remaining_steps for replan support."""

    def test_replace_remaining(self, tmp_data_dir):
        tq = TaskQueue(data_dir=tmp_data_dir)
        steps = [
            TaskStep(id="s0", type="agent_loop", label="步骤0", config={}),
            TaskStep(id="s1", type="agent_loop", label="步骤1", config={}),
            TaskStep(id="s2", type="checkpoint", label="完成", config={"final": True}),
        ]
        task = PersistentTask(
            id="t1", type="autopilot", book_id="b1",
            session_id="s1", steps=steps,
        )
        tq.create_task(task)

        # Simulate: step 0 completed, now at step 1
        tq.advance_step("t1")

        # Replace remaining with new steps
        new_steps = [
            TaskStep(id="new_s0", type="agent_loop", label="新步骤", config={}),
            TaskStep(id="new_final", type="checkpoint", label="新完成", config={"final": True}),
        ]
        ok = tq.replace_remaining_steps("t1", new_steps)
        assert ok is True

        updated = tq.get_task("t1")
        assert len(updated.steps) == 3  # s0 (completed) + 2 new
        assert updated.steps[0].id == "s0"
        assert updated.steps[1].id == "new_s0"
        assert updated.steps[2].id == "new_final"
        assert updated.current_step_index == 1  # Still at index 1

    def test_replace_remaining_nonexistent(self, tmp_data_dir):
        tq = TaskQueue(data_dir=tmp_data_dir)
        ok = tq.replace_remaining_steps("nope", [])
        assert ok is False

    def test_replace_remaining_resets_failed(self, tmp_data_dir):
        tq = TaskQueue(data_dir=tmp_data_dir)
        task = PersistentTask(
            id="t1", type="autopilot", book_id="b1",
            session_id="s1",
            steps=[TaskStep(id="s0", type="agent_loop", label="步骤0", config={})],
            status=TaskStatus.FAILED,
        )
        tq.create_task(task)
        tq.update_task_status("t1", TaskStatus.FAILED, error="some error")

        new_steps = [TaskStep(id="new_s0", type="checkpoint", label="done", config={"final": True})]
        tq.replace_remaining_steps("t1", new_steps)

        updated = tq.get_task("t1")
        assert updated.status == TaskStatus.PENDING
        assert updated.error is None
