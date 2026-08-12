# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from dataclasses import dataclass
from inspect import signature

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

# Autonomous mode is intentionally useful, not cosmetic.  Versioned chapter
# edits such as patch_chapter/edit_chapter can be reverted from chapter
# history, so they run without interruption when the user explicitly enables
# autonomous mode.  Only destructive operations that remove source material
# or its recovery history keep an unconditional confirmation gate.
AUTONOMOUS_CONFIRM_TOOLS = frozenset(
    {
        "delete_all_chapters",
        "delete_chapter",
        "delete_entity",
        "delete_version",
        "delete_foreshadow",
        "delete_timeline_event",
        "delete_worldbuilding_entry",
        "purge_chapter_history",
    }
)

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
    """Session-scoped permission manager with safe autonomous operation.

    Autonomous mode may remove friction for ordinary and recoverable tools,
    but it never bypasses an irreversible deletion confirmation.
    """

    def __init__(self):
        self._rules: list[PermissionRule] = []
        self._session_approved: set[tuple[str, str]] = set()
        self._one_time_token: tuple[str, str] | None = None  # approve for exactly one call
        self._autonomous_sessions: dict[str, bool] = {}
        # Legacy/global default retained for CLI tools and backward-compatible
        # tests.  The desktop routes always set an explicit session value.
        self.autonomous_mode: bool = False

    def add_rule(self, rule: PermissionRule):
        self._rules.append(rule)

    @staticmethod
    def scope_key(book_id: str, session_id: str) -> str:
        return f"{book_id}:{session_id}"

    def set_autonomous(self, session_key: str, enabled: bool) -> None:
        self._autonomous_sessions[session_key] = bool(enabled)

    def is_autonomous(self, session_key: str = "") -> bool:
        if session_key and session_key in self._autonomous_sessions:
            return self._autonomous_sessions[session_key]
        return self.autonomous_mode

    def check(self, tool_name: str, session_key: str = "") -> str:
        from core.tools import registry

        tool = registry._tools.get(tool_name)
        dangerous = bool(tool and tool.dangerous) or tool_name in DANGEROUS_TOOLS

        # Recoverable mutations are exactly what autonomous mode is for.
        # Deletions and history purges still stop for a human decision.
        if self.is_autonomous(session_key):
            return "ask" if tool_name in AUTONOMOUS_CONFIRM_TOOLS else "allow"

        # Consume one-time token first (true "approve once")
        approval_key = (session_key, tool_name)
        if self._one_time_token == approval_key:
            self._one_time_token = None
            return "allow"

        if approval_key in self._session_approved:
            return "allow"

        for rule in reversed(self._rules):
            if rule.tool_name == tool_name or rule.tool_name == "*":
                return rule.action

        # Query the tool registry for the dangerous flag (single source of truth).
        # Falls back to DANGEROUS_TOOLS dict for backward compatibility.
        if dangerous:
            return "ask"

        return "allow"

    def check_for_session(self, tool_name: str, session_key: str) -> str:
        """Session-aware check with compatibility for one-argument hooks.

        A few integrations and tests replace ``check`` with a one-argument
        policy callback.  Keep that extension point working while native
        checks receive the book/session scope.
        """

        check_fn = self.check
        if len(signature(check_fn).parameters) < 2:
            return check_fn(tool_name)
        return check_fn(tool_name, session_key)

    def approve_once(self, tool_name: str, session_key: str = ""):
        self._one_time_token = (session_key, tool_name)

    def approve_session(self, tool_name: str, session_key: str = ""):
        self._session_approved.add((session_key, tool_name))

    def reset_session(self, session_key: str = ""):
        if not session_key:
            self._session_approved.clear()
            self._one_time_token = None
            self._autonomous_sessions.clear()
            return
        self._session_approved = {item for item in self._session_approved if item[0] != session_key}
        if self._one_time_token and self._one_time_token[0] == session_key:
            self._one_time_token = None
        self._autonomous_sessions.pop(session_key, None)

    def get_confirmation_message(self, tool_name: str) -> str:
        info = DANGEROUS_TOOLS.get(tool_name)
        if info:
            return info["message"]
        return f"工具 {tool_name} 需要确认才能执行。"


permission_manager = PermissionManager()
