# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from dataclasses import dataclass

DANGEROUS_TOOLS = {
    "delete_all_chapters": {
        "level": "critical",
        "message": "即将删除本书全部章节，此操作不可撤销。",
    },
    "delete_chapter": {
        "level": "warn",
        "message": "即将删除章节，确认继续？",
    },
    "delete_entity": {
        "level": "warn",
        "message": "即将从知识库删除一个实体，确认继续？",
    },
    "delete_version": {
        "level": "warn",
        "message": "即将删除一个章节版本，确认继续？",
    },
    "delete_foreshadow": {
        "level": "warn",
        "message": "即将删除一个伏笔记录，确认继续？",
    },
    "delete_timeline_event": {
        "level": "warn",
        "message": "即将删除一个时间线事件，确认继续？",
    },
    "delete_worldbuilding_entry": {
        "level": "warn",
        "message": "即将删除一个世界观条目，确认继续？",
    },
    "purge_chapter_history": {
        "level": "critical",
        "message": "即将清空章节的所有历史版本，此操作不可撤销。",
    },
    "batch_edit_chapters": {
        "level": "warn",
        "message": "即将批量修改多个章节，确认继续？",
    },
}

PERMISSION_LEVELS = {
    "critical": True,
    "warn": True,
}


@dataclass
class PermissionRule:
    tool_name: str
    action: str = "ask"  # "allow" | "deny" | "ask"
    pattern: str = "*"


class PermissionManager:
    """Session-scoped permission manager with autonomous mode support.

    When ``autonomous_mode`` is True, ALL tools (including dangerous ones)
    are auto-approved without user confirmation. Use with caution — the Agent
    can irreversibly delete data."""

    def __init__(self):
        self._rules: list[PermissionRule] = []
        self._session_approved: set[str] = set()
        self._one_time_token: str | None = None  # approve for exactly one call
        self.autonomous_mode: bool = False

    def add_rule(self, rule: PermissionRule):
        self._rules.append(rule)

    def check(self, tool_name: str) -> str:
        # Autonomous mode: skip ALL permission checks (dangerous tools auto-approved)
        if self.autonomous_mode:
            return "allow"

        # Consume one-time token first (true "approve once")
        if self._one_time_token == tool_name:
            self._one_time_token = None
            return "allow"

        if tool_name in self._session_approved:
            return "allow"

        for rule in reversed(self._rules):
            if rule.tool_name == tool_name or rule.tool_name == "*":
                return rule.action

        # Query the tool registry for the dangerous flag (single source of truth).
        # Falls back to DANGEROUS_TOOLS dict for backward compatibility.
        from core.tools import registry
        tool = registry._tools.get(tool_name)
        if tool and tool.dangerous:
            return "ask"
        if tool_name in DANGEROUS_TOOLS:
            return "ask"

        return "allow"

    def approve_once(self, tool_name: str):
        self._one_time_token = tool_name

    def approve_session(self, tool_name: str):
        self._session_approved.add(tool_name)

    def reset_session(self):
        self._session_approved.clear()
        self._one_time_token = None

    def get_confirmation_message(self, tool_name: str) -> str:
        info = DANGEROUS_TOOLS.get(tool_name)
        if info:
            return info["message"]
        return f"工具 {tool_name} 需要确认才能执行。"


permission_manager = PermissionManager()
