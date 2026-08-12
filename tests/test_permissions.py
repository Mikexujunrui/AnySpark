from core.permissions import AUTONOMOUS_CONFIRM_TOOLS, DANGEROUS_TOOLS, PermissionManager, PermissionRule


def test_default_allow():
    pm = PermissionManager()
    assert pm.check("search_knowledge") == "allow"
    assert pm.check("read_chapter") == "allow"


def test_dangerous_tools_ask():
    pm = PermissionManager()
    assert pm.check("delete_all_chapters") == "ask"
    assert pm.check("delete_chapter") == "ask"


def test_approve_once():
    pm = PermissionManager()
    pm.approve_once("delete_all_chapters")
    assert pm.check("delete_all_chapters") == "allow"


def test_reset_session():
    pm = PermissionManager()
    pm.approve_once("delete_all_chapters")
    pm.reset_session()
    assert pm.check("delete_all_chapters") == "ask"


def test_custom_rule_deny():
    pm = PermissionManager()
    pm.add_rule(PermissionRule(tool_name="write_chapter", action="deny"))
    assert pm.check("write_chapter") == "deny"


def test_custom_rule_allow():
    pm = PermissionManager()
    pm.add_rule(PermissionRule(tool_name="delete_all_chapters", action="allow"))
    assert pm.check("delete_all_chapters") == "allow"


def test_confirmation_message():
    pm = PermissionManager()
    msg = pm.get_confirmation_message("delete_all_chapters")
    assert "删除" in msg
    assert "不可撤销" in msg


def test_dangerous_tools_defined():
    assert "delete_all_chapters" in DANGEROUS_TOOLS
    assert "delete_chapter" in DANGEROUS_TOOLS


def test_autonomous_mode_allows_recoverable_edits_but_not_deletions():
    pm = PermissionManager()
    scope = pm.scope_key("book", "session")
    pm.set_autonomous(scope, True)

    assert pm.check("patch_chapter", scope) == "allow"
    assert pm.check("edit_chapter", scope) == "allow"
    assert pm.check("batch_edit_chapters", scope) == "allow"
    assert pm.check("delete_chapter", scope) == "ask"
    assert pm.check("purge_chapter_history", scope) == "ask"
    assert "delete_chapter" in AUTONOMOUS_CONFIRM_TOOLS


def test_autonomous_mode_is_isolated_per_book_session():
    pm = PermissionManager()
    first = pm.scope_key("book-a", "session")
    second = pm.scope_key("book-b", "session")
    pm.set_autonomous(first, True)

    assert pm.is_autonomous(first) is True
    assert pm.is_autonomous(second) is False
    assert pm.check("patch_chapter", first) == "allow"
    assert pm.check("patch_chapter", second) == "ask"
