"""Settings manager for multi-provider API configuration.

Persists provider configs, model slot assignments, and mode selection
to `data/settings.json`. Falls back to `.env` defaults on first run.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

VALID_MODES = ("quality", "split", "flash", "custom")
VALID_PROVIDER_TYPES = ("openai", "anthropic", "gemini")

TASK_TYPES = ("writing", "planning", "extraction", "editing", "general", "research")

# Maps llm_client task labels → custom_map keys
_TASK_TO_TYPE = {
    "writing": "writing",
    "planning": "planning",
    "extraction": "extraction",
    "editing": "editing",
    "general": "general",
    "research": "research",
    "workflow": "writing",  # workflow uses writing slot
}


@dataclass
class ProviderConfig:
    id: str                    # unique slug, e.g. "deepseek-main"
    name: str                  # display name
    type: str                  # "openai" | "anthropic" | "gemini"
    api_key: str = ""
    base_url: str = ""         # required for openai-compatible
    models: list = field(default_factory=list)  # available model names


@dataclass
class ModelSlot:
    provider_id: str = ""
    model: str = ""


@dataclass
class BookOverrides:
    """Per-book setting overrides that layer on top of global settings."""
    mode: str = ""                         # quality | split | flash | custom
    slot_pro_provider_id: str = ""
    slot_pro_model: str = ""
    slot_flash_provider_id: str = ""
    slot_flash_model: str = ""

    def is_empty(self) -> bool:
        return not any([
            self.mode, self.slot_pro_provider_id, self.slot_pro_model,
            self.slot_flash_provider_id, self.slot_flash_model,
        ])


@dataclass
class AppSettings:
    providers: list = field(default_factory=list)   # list[ProviderConfig]
    slot_pro: ModelSlot = field(default_factory=ModelSlot)
    slot_flash: ModelSlot = field(default_factory=ModelSlot)
    mode: str = "split"        # quality | split | flash | custom
    custom_map: dict = field(default_factory=lambda: {
        "writing": "pro",
        "planning": "flash",
        "extraction": "flash",
        "editing": "pro",
        "general": "flash",
        "research": "flash",
    })
    book_overrides: dict = field(default_factory=dict)  # {bookId: BookOverrides}
    update_check_enabled: bool = True  # whether to check GitHub for new releases
    memory_enabled: bool = True  # global toggle for the memory system (project + preferences)

    # ── helpers ──

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        for p in self.providers:
            if p.id == provider_id:
                return p
        return None

    def get_book_override(self, book_id: str) -> BookOverrides | None:
        """Get the overrides for a specific book, if any."""
        data = self.book_overrides.get(book_id)
        if not data:
            return None
        if isinstance(data, BookOverrides):
            return data
        return BookOverrides(**data)

    def get_effective(self, book_id: str) -> "AppSettings":
        """Return a merged AppSettings with book-level overrides applied."""
        override = self.get_book_override(book_id)
        if not override or override.is_empty():
            return self
        effective = AppSettings(
            providers=list(self.providers),
            slot_pro=ModelSlot(
                provider_id=override.slot_pro_provider_id or self.slot_pro.provider_id,
                model=override.slot_pro_model or self.slot_pro.model,
            ),
            slot_flash=ModelSlot(
                provider_id=override.slot_flash_provider_id or self.slot_flash.provider_id,
                model=override.slot_flash_model or self.slot_flash.model,
            ),
            mode=override.mode or self.mode,
            custom_map=dict(self.custom_map),
            update_check_enabled=self.update_check_enabled,
        )
        return effective

    def to_dict(self, mask_keys: bool = True) -> dict:
        """Serialize to JSON-safe dict. If mask_keys, api_key is masked."""
        d = asdict(self)
        if mask_keys:
            for p in d.get("providers", []):
                key = p.get("api_key", "")
                p["api_key"] = key[:4] + "****" if len(key) > 4 else "****" if key else ""
        # Convert BookOverrides objects to dicts
        if "book_overrides" in d:
            d["book_overrides"] = {
                k: asdict(v) if isinstance(v, BookOverrides) else v
                for k, v in d["book_overrides"].items()
            }
        return d

    @staticmethod
    def from_dict(d: dict) -> "AppSettings":
        providers = [ProviderConfig(**p) for p in d.get("providers", [])]
        slot_pro = ModelSlot(**d.get("slot_pro", {}))
        slot_flash = ModelSlot(**d.get("slot_flash", {}))
        mode = d.get("mode", "split")
        custom_map = d.get("custom_map", {})
        book_overrides = {}
        for k, v in d.get("book_overrides", {}).items():
            book_overrides[k] = BookOverrides(**v) if isinstance(v, dict) else v
        return AppSettings(
            providers=providers,
            slot_pro=slot_pro,
            slot_flash=slot_flash,
            mode=mode if mode in VALID_MODES else "split",
            custom_map=custom_map,
            book_overrides=book_overrides,
            update_check_enabled=d.get("update_check_enabled", True),
            memory_enabled=d.get("memory_enabled", True),
        )


def _default_from_env() -> AppSettings:
    """Build default settings from .env values (first-run fallback)."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model_pro = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    model_flash = os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash")
    mode = os.getenv("LLM_MODE", "split")

    provider = ProviderConfig(
        id="deepseek-default",
        name="DeepSeek (默认)",
        type="openai",
        api_key=api_key,
        base_url=base_url,
        models=[model_pro, model_flash],
    )
    return AppSettings(
        providers=[provider],
        slot_pro=ModelSlot(provider_id=provider.id, model=model_pro),
        slot_flash=ModelSlot(provider_id=provider.id, model=model_flash),
        mode=mode if mode in VALID_MODES else "split",
    )


def load_settings() -> AppSettings:
    """Load from settings.json, or create defaults from .env."""
    if not SETTINGS_FILE.exists():
        s = _default_from_env()
        save_settings(s)
        return s
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return AppSettings.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to load settings.json, using env defaults: {e}")
        return _default_from_env()


def save_settings(s: AppSettings):
    """Persist settings to data/settings.json."""
    DATA_DIR.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(s.to_dict(mask_keys=False), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Singleton ──

_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def update_settings(s: AppSettings):
    """Replace in-memory settings and persist."""
    global _settings
    _settings = s
    save_settings(s)


def resolve_slot(slot_name: str, settings: AppSettings) -> ModelSlot:
    """Return the ModelSlot for 'pro' or 'flash'."""
    if slot_name == "pro":
        return settings.slot_pro
    return settings.slot_flash


def task_to_type(task: str) -> str:
    """Map llm_client task label to custom_map key."""
    return _TASK_TO_TYPE.get(task, "general")
