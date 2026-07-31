# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

import json
import logging
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── Path resolution ──
# Packaged resources are immutable and live in sys._MEIPASS. User data must
# live somewhere writable and persistent:
#   macOS app: ~/Library/Application Support/AnySpark
#   Windows app: %APPDATA%\AnySpark
#   Linux app: ${XDG_DATA_HOME:-~/.local/share}/AnySpark
#   development: repository root
if getattr(sys, "frozen", False):
    RESOURCE_ROOT = Path(sys._MEIPASS).resolve()  # type: ignore[attr-defined]
else:
    RESOURCE_ROOT = Path(__file__).resolve().parent.parent.parent

_home_override = os.getenv("ANYSPARK_HOME", "").strip()
if _home_override:
    _project_root = Path(_home_override).expanduser().resolve()
elif getattr(sys, "frozen", False):
    if sys.platform == "darwin":
        _project_root = (Path.home() / "Library" / "Application Support" / "AnySpark").resolve()
    elif sys.platform == "win32":
        appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        appdata_root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        _project_root = (appdata_root / "AnySpark").resolve()
    else:
        xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
        data_home = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
        _project_root = (data_home / "AnySpark").resolve()
else:
    _project_root = RESOURCE_ROOT


def _packaged_version() -> str:
    version_file = RESOURCE_ROOT / "pyproject.toml"
    try:
        with version_file.open("rb") as handle:
            return str(tomllib.load(handle).get("project", {}).get("version", "unknown"))
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"


APP_VERSION = _packaged_version()


def _contains_user_data(data_dir: Path) -> bool:
    if not data_dir.is_dir():
        return False
    markers = ("books.json", "settings.json", "novel.db")
    if any((data_dir / marker).exists() for marker in markers):
        return True
    try:
        return any(path.is_file() and path.name != ".DS_Store" for path in data_dir.rglob("*"))
    except OSError:
        return False


def _migrate_legacy_frozen_data(target_root: Path) -> str:
    """Copy legacy executable-adjacent data into the persistent user root.

    The operation is deliberately copy-only: source data is never removed, so
    an interrupted migration can be retried and the old portable installation
    remains a recovery copy.
    """
    if not getattr(sys, "frozen", False):
        return ""

    target_data = target_root / "data"
    if _contains_user_data(target_data):
        return ""

    candidates = [Path(sys.executable).resolve().parent, Path.cwd().resolve()]
    seen: set[Path] = set()
    for legacy_root in candidates:
        if legacy_root in seen or legacy_root == target_root:
            continue
        seen.add(legacy_root)
        legacy_data = legacy_root / "data"
        if not _contains_user_data(legacy_data):
            continue

        try:
            target_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(legacy_data, target_data, dirs_exist_ok=True)
            for filename in (".env", "config.json"):
                source = legacy_root / filename
                destination = target_root / filename
                if source.is_file() and not destination.exists():
                    shutil.copy2(source, destination)
            report = {
                "migrated_at": datetime.now().isoformat(),
                "source": str(legacy_root),
                "target": str(target_root),
                "source_preserved": True,
            }
            (target_root / "migration.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return str(legacy_root)
        except OSError as exc:
            logger.warning("Legacy AnySpark data migration failed from %s: %s", legacy_root, exc)
    return ""


def _backup_data_before_upgrade(target_root: Path, data_dir: Path) -> Path | None:
    """Create one recovery archive whenever a frozen app version changes."""
    if not getattr(sys, "frozen", False):
        return None

    marker = target_root / ".install-version"
    if not _contains_user_data(data_dir):
        # A clean install has nothing to back up, but recording its version now
        # prevents logs created later in the same release from looking like
        # legacy user data on the next launch.
        try:
            target_root.mkdir(parents=True, exist_ok=True)
            marker.write_text(APP_VERSION, encoding="utf-8")
        except OSError:
            pass
        return None

    try:
        previous_version = marker.read_text(encoding="utf-8").strip() if marker.exists() else "legacy"
    except OSError:
        previous_version = "legacy"

    if previous_version == APP_VERSION:
        return None

    backup_path: Path | None = None
    try:
        backup_dir = target_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_name = backup_dir / f"pre-upgrade_{previous_version}_to_{APP_VERSION}_{timestamp}"
        backup_path = Path(shutil.make_archive(str(base_name), "zip", root_dir=data_dir))
        temp_marker = Path(f"{marker}.tmp")
        temp_marker.write_text(APP_VERSION, encoding="utf-8")
        temp_marker.replace(marker)
    except OSError as exc:
        logger.warning("AnySpark pre-upgrade backup failed: %s", exc)
    return backup_path


_migrated_from = _migrate_legacy_frozen_data(_project_root)

# Load .env from project root next to the executable
load_dotenv(_project_root / ".env")
# Also try sys._MEIPASS (for PyInstaller EXE where .env might be bundled)
if getattr(sys, "frozen", False):
    load_dotenv(Path(sys._MEIPASS) / ".env")  # type: ignore[attr-defined]
# Also try CWD (for users who place .env in working directory)
load_dotenv(Path.cwd() / ".env")

PROJECT_ROOT: Path = _project_root
DATA_DIR: Path = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPGRADE_BACKUP_PATH = _backup_data_before_upgrade(PROJECT_ROOT, DATA_DIR)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
    threshold_ratio: float = 0.50
    protected_tail_tokens: int = 15000
    tail_turns_to_keep: int = 4
    max_tool_output_tokens: int = 30000


@dataclass
class AgentConfig:
    # Hard safety cap on agent loop rounds. 0 = unlimited (only used as a
    # global fallback; per-type values in ``per_type`` below set real caps).
    # Behaviour-based safety nets (doom-loop, drift detection, KB mutation
    # guard, hallucination detection) still terminate pathological loops.
    max_rounds: int = 0
    # Round count at which to start injecting progressive "wrap up" nudges.
    # 0 = unlimited (no progressive warnings).
    soft_round_limit: int = 0
    # Token budget hard cap: stop the loop when cumulative input+output tokens
    # exceed ``token_budget_ratio`` × model context limit. 0 = disabled.
    # Disabled by default — compaction (threshold_ratio) handles context
    # management by pruning/summarizing when actual context approaches the
    # model's window. Cumulative caps are too conservative for 1M-window
    # models where multi-round workflows legitimately exceed 900K cumulative.
    token_budget_ratio: float = 0.0
    max_workers: int = 8
    default_temperature: float = 0.3
    creative_temperature: float = 0.7
    extraction_temperature: float = 0.1
    doom_loop_threshold: int = 3
    # Toggle for the "lower temperature on pure tool chains" heuristic, so it
    # can be A/B tested against metrics rather than left on faith.
    adaptive_temperature: bool = True
    per_type: dict = field(
        default_factory=lambda: {
            # max_rounds: write放宽到100供长篇生成，其余30（大厂约50，写作场景放宽）
            "write": {"temperature": 0.3, "task_label": "writing", "max_rounds": 100},
            "plan": {"temperature": 0.3, "task_label": "planning", "max_rounds": 30},
            "extract": {"temperature": 0.1, "task_label": "extraction", "max_rounds": 30},
            "edit": {"temperature": 0.3, "task_label": "editing", "max_rounds": 30},
            "consistency": {"temperature": 0.1, "task_label": "extraction", "max_rounds": 30},
            "general": {"temperature": 0.3, "task_label": "general", "max_rounds": 30},
            "research": {"temperature": 0.2, "task_label": "research", "max_rounds": 30},
        }
    )


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
    cors_origins: list = field(
        default_factory=lambda: [
            "http://localhost:8190",
            "http://127.0.0.1:8190",
        ]
    )


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
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
