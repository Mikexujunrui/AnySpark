# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def load_workspace_overrides(cfg: "AppConfig", book_id: str = ""):
    """Load workspace-level config overrides from DATA_DIR/{book_id}/.novel/config.toml."""
    if not book_id:
        return
    workspace_config = DATA_DIR / book_id / ".novel" / "config.toml"
    if not workspace_config.exists():
        return
    import tomllib
    try:
        with open(workspace_config, "rb") as f:
            overrides = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return

    if "agent" in overrides:
        for k, v in overrides["agent"].items():
            if hasattr(cfg.agent, k):
                setattr(cfg.agent, k, v)
            elif k == "per_type" and isinstance(v, dict):
                for agent_name, agent_overrides in v.items():
                    if agent_name in cfg.agent.per_type:
                        cfg.agent.per_type[agent_name].update(agent_overrides)
    if "storage" in overrides:
        for k, v in overrides["storage"].items():
            if hasattr(cfg.storage, k):
                setattr(cfg.storage, k, v)
    if "llm" in overrides:
        for k, v in overrides["llm"].items():
            if hasattr(cfg.llm, k):
                setattr(cfg.llm, k, v)


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model_pro: str = "deepseek-v4-pro"
    model_flash: str = "deepseek-v4-flash"
    mode: str = "split"
    creative_tasks: tuple = ("writing", "planning", "editing", "workflow")


@dataclass
class RetryConfig:
    max_retries: int = 5
    initial_delay: float = 2.0
    max_delay: float = 30.0


@dataclass
class CompactionConfig:
    threshold_ratio: float = 0.85
    protected_tail_tokens: int = 80000
    tail_turns_to_keep: int = 5
    max_tool_output_tokens: int = 50000


@dataclass
class AgentConfig:
    # Hard safety cap — only hit if the agent fails to self-terminate.
    # Set high so natural stopping + soft nudge handles 99%+ of tasks.
    max_rounds: int = 200
    # Round count at which to start injecting progressive "wrap up" nudges.
    # The agent should naturally stop before this, but if it wanders past
    # this threshold, nudges gently encourage it to wrap up.
    soft_round_limit: int = 30
    max_workers: int = 8
    default_temperature: float = 0.3
    creative_temperature: float = 0.7
    extraction_temperature: float = 0.1
    doom_loop_threshold: int = 3
    # Toggle for the "lower temperature on pure tool chains" heuristic, so it
    # can be A/B tested against metrics rather than left on faith.
    adaptive_temperature: bool = True
    per_type: dict = field(default_factory=lambda: {
        "write": {"temperature": 0.3, "task_label": "writing"},
        "plan": {"temperature": 0.3, "task_label": "planning"},
        "extract": {"temperature": 0.1, "task_label": "extraction"},
        "edit": {"temperature": 0.3, "task_label": "editing"},
        "consistency": {"temperature": 0.1, "task_label": "extraction"},
        "general": {"temperature": 0.3, "task_label": "general"},
        "research": {"temperature": 0.2, "task_label": "research"},
    })


@dataclass
class StorageConfig:
    max_chapter_chars: int = 256000
    max_context_chars: int = 500000
    max_knowledge_summary_chars: int = 60000
    max_document_sample_chars: int = 200000
    max_extraction_chars: int = 500000
    max_style_sample_chars: int = 8000
    max_ref_chapter_chars: int = 50000
    max_source_text_chars: int = 10000


@dataclass
class WebSearchConfig:
    provider: str = ""
    exa_api_key: str = ""
    parallel_api_key: str = ""
    enabled: bool = True
    timeout: int = 25
    max_response_bytes: int = 256 * 1024


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8191
    cors_origins: list = field(default_factory=lambda: [
        "http://localhost:8190",
        "http://127.0.0.1:8190",
    ])


@dataclass
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "novel_agent_2024!"


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)


def _load_config() -> AppConfig:
    cfg = AppConfig()

    # ── LLM config: prefer settings.json, fallback to .env ──
    try:
        from .settings import get_settings
        s = get_settings()
        pro_slot = s.slot_pro
        flash_slot = s.slot_flash
        pro_provider = s.get_provider(pro_slot.provider_id)
        s.get_provider(flash_slot.provider_id)

        # Use pro slot as the "primary" for legacy code that reads config.llm.*
        if pro_provider:
            cfg.llm.api_key = pro_provider.api_key
            cfg.llm.base_url = pro_provider.base_url or "https://api.deepseek.com"
        else:
            cfg.llm.api_key = os.getenv("DEEPSEEK_API_KEY", "")
            cfg.llm.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        cfg.llm.model_pro = pro_slot.model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        cfg.llm.model_flash = flash_slot.model or os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash")
        cfg.llm.mode = s.mode
    except (ImportError, RuntimeError, AttributeError):
        # settings not available yet, fall back to env
        cfg.llm.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        cfg.llm.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        cfg.llm.model_pro = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        cfg.llm.model_flash = os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash")
        cfg.llm.mode = os.getenv("LLM_MODE", "split")

    cfg.neo4j.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    cfg.neo4j.user = os.getenv("NEO4J_USER", "neo4j")
    cfg.neo4j.password = os.getenv("NEO4J_PASSWORD", "novel_agent_2024!")

    cfg.web_search.provider = os.getenv("WEBSEARCH_PROVIDER", "")
    cfg.web_search.exa_api_key = os.getenv("EXA_API_KEY", "")
    cfg.web_search.parallel_api_key = os.getenv("PARALLEL_API_KEY", "")
    cfg.web_search.enabled = os.getenv("WEBSEARCH_ENABLED", "true").lower() != "false"

    port = os.getenv("SERVER_PORT", "8191")
    cfg.server.port = int(port)

    # CORS: comma-separated list of allowed origins (e.g. "https://mydomain.com,https://app.mydomain.com")
    cors_env = os.getenv("CORS_ORIGINS", "")
    if cors_env:
        cfg.server.cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        # Default: allow all origins (useful for dev/cloud deployment)
        cfg.server.cors_origins = ["*"]

    project_config_path = PROJECT_ROOT / "config.json"
    if project_config_path.exists():
        try:
            overrides = json.loads(project_config_path.read_text(encoding="utf-8"))
            if "agent" in overrides:
                for k, v in overrides["agent"].items():
                    if hasattr(cfg.agent, k):
                        setattr(cfg.agent, k, v)
            if "storage" in overrides:
                for k, v in overrides["storage"].items():
                    if hasattr(cfg.storage, k):
                        setattr(cfg.storage, k, v)
            if "server" in overrides:
                for k, v in overrides["server"].items():
                    if hasattr(cfg.server, k):
                        setattr(cfg.server, k, v)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load config.json from {project_config_path}: {e}")

    return cfg


config = _load_config()
