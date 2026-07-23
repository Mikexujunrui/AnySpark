from core.permissions import DANGEROUS_TOOLS, PermissionManager, PermissionRule


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
