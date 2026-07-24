# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Agent Configuration — per-agent model assignment and temperature settings.

Delegates to core.config for temperature values (single source of truth).
"""

import logging
import os

from core.config import config

logger = logging.getLogger(__name__)

# ── Agent descriptions for frontend display ──

AGENT_DESCRIPTIONS = {
    "write": "章节写作 Agent",
    "extract": "知识提取 Agent",
    "reviewer": "评审团 Agent",
    "interactive": "互动故事 Agent",
    "plan": "规划/大纲 Agent",
    "edit": "编辑/修改 Agent",
    "research": "研究/搜索 Agent",
    "consistency": "一致性检查 Agent",
}


def get_agent_config(agent_type: str, workspace_path: str = None) -> dict:
    """Get the resolved configuration for a specific agent type.

    Resolution order:
    1. core.config per_type values (single source of truth)
    2. Environment variables (AGENT_<TYPE>_MODEL, AGENT_<TYPE>_TEMPERATURE)
    """
    per_type = config.agent.per_type.get(
        agent_type,
        {
            "temperature": config.agent.default_temperature,
            "task_label": "general",
        },
    )

    result = {
        "model": "deepseek-pro",
        "temperature": per_type.get("temperature", config.agent.default_temperature),
        "task": per_type.get("task_label", "general"),
        "description": AGENT_DESCRIPTIONS.get(agent_type, "通用 Agent"),
    }

    # Environment variables (highest priority)
    env_prefix = f"AGENT_{agent_type.upper()}"
    env_model = os.getenv(f"{env_prefix}_MODEL")
    env_temp = os.getenv(f"{env_prefix}_TEMPERATURE")

    if env_model:
        result["model"] = env_model
    if env_temp:
        try:
            result["temperature"] = float(env_temp)
        except ValueError:
            pass

    return result


def get_agent_configs_for_frontend() -> dict:
    """Return agent configs in a format suitable for the frontend settings panel."""
    return {
        "agents": {
            agent_type: {
                "model": cfg["model"],
                "temperature": cfg["temperature"],
                "description": cfg["description"],
            }
            for agent_type, cfg in {at: get_agent_config(at) for at in AGENT_DESCRIPTIONS}.items()
        }
    }
