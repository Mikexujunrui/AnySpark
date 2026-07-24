"""Tests for execute_workflow tool — workflow execution within agent conversation."""

import pytest

from core.workflow_engine import WorkflowEngine


@pytest.fixture
def workflow_engine():
    """Create a fresh workflow engine for testing."""
    return WorkflowEngine()


class TestWorkflowEngine:
    def test_build_workflow(self, workflow_engine):
        definition = {
            "name": "测试工作流",
            "steps": [
                {"type": "test_step", "label": "步骤1"},
                {"type": "test_step", "label": "步骤2"},
            ],
        }
        wf = workflow_engine.build("wf_001", definition)
        assert wf.id == "wf_001"
        assert wf.name == "测试工作流"
        assert len(wf.steps) == 2

    @pytest.mark.asyncio
    async def test_execute_workflow_no_handler(self, workflow_engine):
        """Steps without handlers should fail gracefully."""
        definition = {
            "name": "无处理器工作流",
            "steps": [{"type": "unknown_step", "label": "未知步骤"}],
        }
        workflow_engine.build("wf_002", definition)

        result = await workflow_engine.execute("wf_002", {})
        assert len(result) == 1
        assert "error" in result[0]
        assert "no handler" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_execute_workflow_with_handler(self, workflow_engine):
        """Steps with registered handlers should complete successfully."""

        async def test_handler(config, context, previous_results):
            return {"output": "success"}

        workflow_engine.register("test_step", test_handler)

        definition = {
            "name": "有处理器工作流",
            "steps": [{"type": "test_step", "label": "测试步骤"}],
        }
        workflow_engine.build("wf_003", definition)

        result = await workflow_engine.execute("wf_003", {"book_id": "test"})
        assert len(result) == 1
        assert result[0]["result"]["output"] == "success"

    @pytest.mark.asyncio
    async def test_execute_workflow_handler_exception(self, workflow_engine):
        """Handler exceptions should be caught and reported."""

        async def failing_handler(config, context, previous_results):
            raise ValueError("测试错误")

        workflow_engine.register("failing_step", failing_handler)

        definition = {
            "name": "失败工作流",
            "steps": [{"type": "failing_step", "label": "失败步骤"}],
        }
        workflow_engine.build("wf_004", definition)

        result = await workflow_engine.execute("wf_004", {})
        assert len(result) == 1
        assert "error" in result[0]
        assert "测试错误" in result[0]["error"]

    def test_get_status(self, workflow_engine):
        definition = {
            "name": "状态测试",
            "steps": [{"type": "test", "label": "步骤"}],
        }
        workflow_engine.build("wf_005", definition)

        status = workflow_engine.get_status("wf_005")
        assert status is not None
        assert status["id"] == "wf_005"
        assert status["name"] == "状态测试"
        assert status["status"] == "pending"

    def test_get_status_not_found(self, workflow_engine):
        status = workflow_engine.get_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_execute_workflow_sequential(self, workflow_engine):
        """Steps should execute in order, with results passed to subsequent steps."""
        execution_order = []

        async def step_a(config, context, previous_results):
            execution_order.append("A")
            return {"value": "from_A"}

        async def step_b(config, context, previous_results):
            execution_order.append("B")
            # Can access previous results
            assert len(previous_results) == 1
            assert previous_results[0]["result"]["value"] == "from_A"
            return {"value": "from_B"}

        workflow_engine.register("step_a", step_a)
        workflow_engine.register("step_b", step_b)

        definition = {
            "name": "顺序执行",
            "steps": [
                {"type": "step_a", "label": "A"},
                {"type": "step_b", "label": "B"},
            ],
        }
        workflow_engine.build("wf_006", definition)

        result = await workflow_engine.execute("wf_006", {})
        assert execution_order == ["A", "B"]
        assert len(result) == 2


class TestExecuteWorkflowTool:
    """Test _handle_workflow_tool with execute_workflow action."""

    @pytest.mark.asyncio
    async def test_execute_workflow_missing_id(self, monkeypatch):
        from tools.executor import _handle_workflow_tool

        result = await _handle_workflow_tool("execute_workflow", {}, "test_book")
        assert "错误" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, monkeypatch):
        from tools.executor import _handle_workflow_tool

        result = await _handle_workflow_tool("execute_workflow", {"workflow_id": "nonexistent"}, "test_book")
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_success(self, monkeypatch, tmp_path):
        from core.workflow_engine import engine as wf_engine
        from tools.executor import _handle_workflow_tool

        # Mock json_store to return a test workflow
        class MockJsonStore:
            def get_workflow(self, wid):
                return {
                    "id": wid,
                    "name": "测试工作流",
                    "steps": [{"id": "0", "type": "test", "label": "步骤1"}],
                }

        monkeypatch.setattr("tools.impl.workflow_tools.json_store", MockJsonStore())

        # Register a test handler
        async def test_handler(config, context, results):
            return {"done": True}

        wf_engine.register("test", test_handler)

        result = await _handle_workflow_tool("execute_workflow", {"workflow_id": "wf_test"}, "test_book")
        assert "开始执行" in result or "执行完毕" in result


class TestUpdateWorkflowTool:
    """Test update_workflow tool."""

    def test_update_workflow_storage(self, tmp_data_dir):
        """Test json_store.update_workflow method."""
        from core.errors import NotFoundError
        from data.json_store import json_store

        store = json_store
        store._global_wfs_file = tmp_data_dir / "workflows.json"

        # Create a workflow first
        wf = store.add_workflow("book1", "原始名称", [{"id": "0", "type": "test", "label": "步骤1"}])

        # Update name
        updated = store.update_workflow(wf["id"], {"name": "新名称"})
        assert updated["name"] == "新名称"
        assert "updatedAt" in updated

        # Update steps
        new_steps = [
            {"id": "0", "type": "step_a", "label": "A"},
            {"id": "1", "type": "step_b", "label": "B"},
        ]
        updated = store.update_workflow(wf["id"], {"steps": new_steps})
        assert len(updated["steps"]) == 2

        # Update non-existent
        with pytest.raises(NotFoundError):
            store.update_workflow("nonexistent", {"name": "x"})

    @pytest.mark.asyncio
    async def test_update_workflow_tool_missing_id(self, monkeypatch):
        from tools.executor import _handle_workflow_tool

        result = await _handle_workflow_tool("update_workflow", {}, "test_book")
        assert "错误" in result

    @pytest.mark.asyncio
    async def test_update_workflow_tool_no_updates(self, monkeypatch):
        from tools.executor import _handle_workflow_tool

        result = await _handle_workflow_tool("update_workflow", {"workflow_id": "wf_001"}, "test_book")
        assert "错误" in result
        assert "修改项" in result

    @pytest.mark.asyncio
    async def test_update_workflow_tool_success(self, monkeypatch, tmp_path):
        from tools.executor import _handle_workflow_tool

        class MockJsonStore:
            def update_workflow(self, wid, updates):
                return {
                    "id": wid,
                    "name": updates.get("name", "旧名称"),
                    "steps": updates.get("steps", []),
                }

        monkeypatch.setattr("tools.impl.workflow_tools.json_store", MockJsonStore())

        result = await _handle_workflow_tool(
            "update_workflow",
            {
                "workflow_id": "wf_test",
                "name": "新名称",
                "steps": [{"type": "test", "label": "步骤1"}],
            },
            "test_book",
        )
        assert "已更新" in result
        assert "新名称" in result
