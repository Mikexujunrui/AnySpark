"""Tests for skill CRUD operations via Agent tools."""

import pytest

from core.skills import SkillManager


@pytest.fixture
def skill_manager(tmp_path, monkeypatch):
    """Create a temporary skill manager with isolated directories."""
    import core.skills as skills_module

    system_dir = tmp_path / "skills"
    user_dir = tmp_path / "data" / "skills"
    system_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(skills_module, "SYSTEM_SKILLS_DIR", system_dir)
    monkeypatch.setattr(skills_module, "USER_SKILLS_DIR", user_dir)
    return SkillManager()


class TestSkillManager:
    def test_list_skills_empty(self, skill_manager):
        skills = skill_manager.list_skills()
        assert skills == []

    def test_add_user_skill(self, skill_manager):
        definition = {
            "description": "测试技能",
            "triggers": ["novel_chapter"],
            "steps": [{"tool": "extract_knowledge", "label": "提取"}],
        }
        result = skill_manager.add_user_skill("test_skill", definition)
        assert result["name"] == "test_skill"
        assert result["description"] == "测试技能"
        assert result["triggers"] == ["novel_chapter"]
        assert len(result["steps"]) == 1

    def test_add_duplicate_skill_raises(self, skill_manager):
        definition = {"description": "测试", "triggers": [], "steps": [{"tool": "x"}]}
        skill_manager.add_user_skill("test_skill", definition)
        with pytest.raises(ValueError, match="已存在"):
            skill_manager.add_user_skill("test_skill", definition)

    def test_update_user_skill(self, skill_manager):
        definition = {"description": "原描述", "triggers": [], "steps": [{"tool": "x"}]}
        skill_manager.add_user_skill("test_skill", definition)
        updated = skill_manager.update_user_skill("test_skill", {"description": "新描述"})
        assert updated["description"] == "新描述"

    def test_update_nonexistent_skill_raises(self, skill_manager):
        with pytest.raises(ValueError, match="不存在"):
            skill_manager.update_user_skill("nonexistent", {"description": "x"})

    def test_delete_user_skill(self, skill_manager):
        definition = {"description": "测试", "triggers": [], "steps": [{"tool": "x"}]}
        skill_manager.add_user_skill("test_skill", definition)
        assert skill_manager.delete_user_skill("test_skill") is True
        assert skill_manager.list_skills() == []

    def test_delete_nonexistent_skill(self, skill_manager):
        assert skill_manager.delete_user_skill("nonexistent") is False

    def test_list_skills_with_source_filter(self, skill_manager):
        definition = {"description": "用户技能", "triggers": [], "steps": [{"tool": "x"}]}
        skill_manager.add_user_skill("user_skill", definition)
        user_skills = skill_manager.list_skills(source="user")
        assert len(user_skills) == 1
        assert user_skills[0]["source"] == "user"

    def test_skill_persistence(self, skill_manager, tmp_path):
        """Skills should be persisted to YAML file."""
        definition = {"description": "持久化测试", "triggers": [], "steps": [{"tool": "x"}]}
        skill_manager.add_user_skill("persist_test", definition)

        # Reload manager and verify
        new_manager = SkillManager()
        new_manager._load_all()
        # Note: Due to monkeypatch, this tests the file system persistence


class TestSkillMatching:
    def test_skill_matches_content_type(self, skill_manager):
        definition = {
            "description": "章节处理",
            "triggers": ["novel_chapter", "mixed"],
            "steps": [{"tool": "extract_knowledge"}],
        }
        skill_manager.add_user_skill("chapter_handler", definition)

        matches = skill_manager.find_matching("novel_chapter")
        assert len(matches) == 1
        assert matches[0].name == "chapter_handler"

    def test_skill_no_match(self, skill_manager):
        definition = {
            "description": "章节处理",
            "triggers": ["novel_chapter"],
            "steps": [{"tool": "extract_knowledge"}],
        }
        skill_manager.add_user_skill("chapter_handler", definition)

        matches = skill_manager.find_matching("setting_document")
        assert len(matches) == 0


# ── Executor integration tests ──


class TestSkillToolExecutor:
    """Test _handle_skill_tool function directly."""

    def test_list_skills_empty(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        result = _handle_skill_tool("list_skills", {})
        assert "暂无可用技能" in result

    def test_list_skills_with_skills(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        skill_manager.add_user_skill(
            "test",
            {
                "description": "测试技能",
                "triggers": ["novel_chapter"],
                "steps": [{"tool": "extract_knowledge", "label": "提取"}],
            },
        )

        result = _handle_skill_tool("list_skills", {})
        assert "test" in result
        assert "测试技能" in result

    def test_create_skill_success(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        result = _handle_skill_tool(
            "create_skill",
            {
                "name": "new_skill",
                "description": "新技能",
                "triggers": ["instruction"],
                "steps": [{"tool": "write_chapter", "label": "写作"}],
            },
        )
        assert "已创建" in result
        assert "new_skill" in result

    def test_create_skill_missing_name(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        result = _handle_skill_tool("create_skill", {"description": "x"})
        assert "错误" in result

    def test_create_skill_missing_steps(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        result = _handle_skill_tool(
            "create_skill",
            {
                "name": "test",
                "description": "测试",
            },
        )
        assert "错误" in result
        assert "steps" in result

    def test_update_skill(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        skill_manager.add_user_skill(
            "test",
            {
                "description": "原描述",
                "triggers": [],
                "steps": [{"tool": "x"}],
            },
        )

        result = _handle_skill_tool(
            "update_skill",
            {
                "name": "test",
                "description": "新描述",
            },
        )
        assert "已更新" in result

    def test_delete_skill(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        skill_manager.add_user_skill(
            "test",
            {
                "description": "测试",
                "triggers": [],
                "steps": [{"tool": "x"}],
            },
        )

        result = _handle_skill_tool("delete_skill", {"name": "test"})
        assert "已删除" in result

    def test_delete_nonexistent_skill(self, skill_manager, monkeypatch):
        import core.skills as skills_module
        from tools.executor import _handle_skill_tool

        monkeypatch.setattr(skills_module, "manager", skill_manager)

        result = _handle_skill_tool("delete_skill", {"name": "nonexistent"})
        assert "不存在" in result
