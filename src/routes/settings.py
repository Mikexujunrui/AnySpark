"""Settings API routes for multi-provider configuration."""

import logging
import time

from fastapi import APIRouter, HTTPException
from httpx import Timeout
from openai import OpenAI
from pydantic import BaseModel

from core.llm_client import MODELS, available_effort_tiers_for_task, reload_clients
from core.llm_client import get_mode as _llm_get_mode
from core.model_discovery import ModelDiscoveryError, discover_models, provider_base_url
from core.reasoning import EFFORT_TIERS
from core.settings import (
    TASK_TYPES,
    VALID_MODES,
    VALID_PROVIDER_TYPES,
    AppSettings,
    BookOverrides,
    GenerationSettings,
    ModelSlot,
    ProviderConfig,
    get_settings,
    update_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

# Display labels for the unified effort scale (frontend renders these).
EFFORT_TIER_LABELS = {
    "off": {"label": "关闭", "hint": "不注入思考参数，最快"},
    "minimal": {"label": "极简", "hint": "少量思考，最快可用档"},
    "low": {"label": "轻量", "hint": "快，浅层推理"},
    "medium": {"label": "标准", "hint": "默认档位"},
    "high": {"label": "深度", "hint": "慢，深度推理"},
}


def reasoning_tier_meta(settings: AppSettings) -> dict:
    """Return effort-tier metadata for the settings panel.

    ``scale`` lists all five scale rungs with display labels; ``families`` maps
    task labels to the tiers available for that model family so the UI can
    highlight which rungs the current model actually supports.
    """
    scale = [{"key": tier, **EFFORT_TIER_LABELS.get(tier, {"label": tier, "hint": ""})} for tier in EFFORT_TIERS]
    family_meta = {}
    for task in ("writing", "planning", "extraction", "editing", "general", "research"):
        family_meta[task] = available_effort_tiers_for_task(task)
    return {
        "scale": scale,
        "families": family_meta,
        "custom_count": len(settings.custom_family_tiers or {}),
    }


# ── Request models ──────────────────────────────────────────────────────────


class ProviderUpdate(BaseModel):
    id: str
    name: str
    type: str
    api_key: str = ""
    base_url: str = ""
    models: list[str] = []


class SlotUpdate(BaseModel):
    slot_pro_provider_id: str = ""
    slot_pro_model: str = ""
    slot_flash_provider_id: str = ""
    slot_flash_model: str = ""


class ModeUpdate(BaseModel):
    mode: str
    custom_map: dict | None = None


class TestRequest(BaseModel):
    provider_id: str


class ModelDiscoveryRequest(BaseModel):
    provider_id: str = ""
    type: str = "openai"
    api_key: str = ""
    base_url: str = ""


class BookSettingsUpdate(BaseModel):
    mode: str = ""
    slot_pro_provider_id: str = ""
    slot_pro_model: str = ""
    slot_flash_provider_id: str = ""
    slot_flash_model: str = ""


class GenerationSettingsUpdate(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.95
    frequency_penalty: float = 0.15
    presence_penalty: float = 0.0
    max_output_tokens: int = 65536
    reasoning_effort: str = "medium"


class ExperimentalFeaturesUpdate(BaseModel):
    author_dna_lab: bool = False

# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/settings")
def get_current_settings():
    """Return current settings with masked API keys."""
    s = get_settings()
    d = s.to_dict(mask_keys=True)
    d["models"] = MODELS
    d["valid_modes"] = list(VALID_MODES)
    d["valid_provider_types"] = list(VALID_PROVIDER_TYPES)
    d["task_types"] = list(TASK_TYPES)
    d["effort_tiers"] = reasoning_tier_meta(s)
    return d


@router.post("/settings/providers")
def upsert_provider(data: ProviderUpdate):
    """Add or update a provider."""
    if data.type not in VALID_PROVIDER_TYPES:
        raise HTTPException(400, f"Invalid provider type: {data.type}. Must be one of {VALID_PROVIDER_TYPES}")
    if not data.id.strip():
        raise HTTPException(400, "Provider id cannot be empty")
    if not data.name.strip():
        raise HTTPException(400, "Provider name cannot be empty")
    models = list(dict.fromkeys(model.strip() for model in data.models if model.strip()))
    if not models:
        raise HTTPException(400, "At least one model is required")
    try:
        base_url = provider_base_url(data.type, data.base_url)
    except ModelDiscoveryError as exc:
        raise HTTPException(400, str(exc))

    s = get_settings()
    provider = ProviderConfig(
        id=data.id.strip(),
        name=data.name.strip(),
        type=data.type,
        api_key=data.api_key,
        base_url=base_url,
        models=models,
    )

    # Check if provider is masked or empty → keep original key
    existing = s.get_provider(provider.id)
    if existing and (not data.api_key or data.api_key.endswith("****")):
        provider.api_key = existing.api_key

    # Update or add
    found = False
    for i, p in enumerate(s.providers):
        if p.id == provider.id:
            s.providers[i] = provider
            found = True
            break
    if not found:
        s.providers.append(provider)

    def _slot_is_usable(slot: ModelSlot) -> bool:
        assigned = s.get_provider(slot.provider_id)
        return bool(
            assigned
            and assigned.api_key.strip()
            and slot.model.strip()
            and (not assigned.models or slot.model in assigned.models)
        )

    # A freshly added, configured Provider should immediately work. This is
    # especially important on first setup, where both slots still reference
    # the keyless built-in placeholder and "connection test succeeded" would
    # otherwise be followed by a chat that never uses the new Provider.
    if provider.api_key.strip():
        for slot in (s.slot_pro, s.slot_flash):
            if not _slot_is_usable(slot):
                slot.provider_id = provider.id
                slot.model = provider.models[0]

    # Keep every slot valid when a provider's selected model set changes.
    for slot in (s.slot_pro, s.slot_flash):
        if slot.provider_id == provider.id and slot.model not in provider.models:
            slot.model = provider.models[0]
    for book_id, override in list(s.book_overrides.items()):
        if isinstance(override, dict):
            override = BookOverrides(**override)
            s.book_overrides[book_id] = override
        if override.slot_pro_provider_id == provider.id and override.slot_pro_model not in provider.models:
            override.slot_pro_model = provider.models[0]
        if override.slot_flash_provider_id == provider.id and override.slot_flash_model not in provider.models:
            override.slot_flash_model = provider.models[0]

    update_settings(s)
    reload_clients()
    return s.to_dict(mask_keys=True)


@router.delete("/settings/providers/{provider_id}")
def delete_provider(provider_id: str):
    """Delete a provider."""
    s = get_settings()
    s.providers = [p for p in s.providers if p.id != provider_id]

    # If the deleted provider was used in a slot, clear it
    if s.slot_pro.provider_id == provider_id:
        s.slot_pro = ModelSlot()
    if s.slot_flash.provider_id == provider_id:
        s.slot_flash = ModelSlot()

    update_settings(s)
    reload_clients()
    return s.to_dict(mask_keys=True)


@router.post("/settings/slots")
def update_slots(data: SlotUpdate):
    """Update pro/flash slot assignments."""
    s = get_settings()

    if data.slot_pro_provider_id:
        provider = s.get_provider(data.slot_pro_provider_id)
        if not provider:
            raise HTTPException(400, f"Provider not found: {data.slot_pro_provider_id}")
        if data.slot_pro_model and data.slot_pro_model not in provider.models:
            raise HTTPException(400, f"Model not found in provider: {data.slot_pro_model}")
        s.slot_pro.provider_id = data.slot_pro_provider_id
    if data.slot_pro_model:
        provider = s.get_provider(data.slot_pro_provider_id or s.slot_pro.provider_id)
        if not provider or data.slot_pro_model not in provider.models:
            raise HTTPException(400, f"Model not found in provider: {data.slot_pro_model}")
        s.slot_pro.model = data.slot_pro_model

    if data.slot_flash_provider_id:
        provider = s.get_provider(data.slot_flash_provider_id)
        if not provider:
            raise HTTPException(400, f"Provider not found: {data.slot_flash_provider_id}")
        if data.slot_flash_model and data.slot_flash_model not in provider.models:
            raise HTTPException(400, f"Model not found in provider: {data.slot_flash_model}")
        s.slot_flash.provider_id = data.slot_flash_provider_id
    if data.slot_flash_model:
        provider = s.get_provider(data.slot_flash_provider_id or s.slot_flash.provider_id)
        if not provider or data.slot_flash_model not in provider.models:
            raise HTTPException(400, f"Model not found in provider: {data.slot_flash_model}")
        s.slot_flash.model = data.slot_flash_model

    update_settings(s)
    reload_clients()
    return s.to_dict(mask_keys=True)


@router.post("/settings/mode")
def switch_mode(data: ModeUpdate):
    """Switch LLM mode."""
    if data.mode not in VALID_MODES:
        raise HTTPException(400, f"Invalid mode: {data.mode}. Must be one of {VALID_MODES}")

    s = get_settings()
    s.mode = data.mode
    if data.custom_map is not None:
        s.custom_map = data.custom_map

    update_settings(s)
    return s.to_dict(mask_keys=True)


@router.put("/settings/generation")
def update_generation_settings(data: GenerationSettingsUpdate):
    """Update prose-only generation controls.

    Tool-calling requests intentionally keep their conservative parameters so
    changing literary creativity cannot destabilize Agent tool selection.
    """
    s = get_settings()
    s.generation = GenerationSettings(**data.model_dump()).normalized()
    update_settings(s)
    return s.to_dict(mask_keys=True)


@router.put("/settings/experimental")
def update_experimental_features(data: ExperimentalFeaturesUpdate):
    """Persist explicit opt-ins for unfinished product experiments."""

    s = get_settings()
    flags = dict(s.experimental_features or {})
    flags["author_dna_lab"] = bool(data.author_dna_lab)
    s.experimental_features = flags
    update_settings(s)
    return s.to_dict(mask_keys=True)


@router.post("/settings/test")
def test_provider_connection(data: TestRequest):
    """Test a provider's API connection with a simple request."""
    s = get_settings()
    provider = s.get_provider(data.provider_id)
    if not provider:
        raise HTTPException(404, f"Provider not found: {data.provider_id}")

    try:
        start = time.time()
        client = OpenAI(
            api_key=provider.api_key,
            base_url=provider_base_url(provider.type, provider.base_url),
            timeout=Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0),
            max_retries=0,
        )
        resp = client.chat.completions.create(
            model=provider.models[0] if provider.models else "gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        elapsed = round(time.time() - start, 2)
        reply = resp.choices[0].message.content or ""
        return {
            "success": True,
            "latency_ms": int(elapsed * 1000),
            "reply": reply[:50],
            "model": resp.model,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)[:200],
        }


@router.post("/settings/models/discover")
def discover_provider_models(data: ModelDiscoveryRequest):
    """Fetch model IDs using either form credentials or a saved provider key."""
    if data.type not in VALID_PROVIDER_TYPES:
        raise HTTPException(400, f"不支持的 Provider 类型: {data.type}")

    api_key = data.api_key.strip()
    base_url = data.base_url.strip()
    if data.provider_id:
        existing = get_settings().get_provider(data.provider_id)
        if existing:
            if not api_key or api_key.endswith("****"):
                api_key = existing.api_key
            if not base_url:
                base_url = existing.base_url

    try:
        models, endpoint = discover_models(data.type, api_key, base_url)
    except ModelDiscoveryError as exc:
        raise HTTPException(400, str(exc))
    return {
        "success": True,
        "models": models,
        "count": len(models),
        "endpoint": endpoint,
    }


# ── Legacy compat: /api/mode ────────────────────────────────────────────────
# Kept for backward compatibility. New code should use /api/settings/mode.


class ModeSwitch(BaseModel):
    mode: str


@router.get("/mode")
def get_llm_mode():
    return {"mode": _llm_get_mode(), "models": MODELS}


@router.post("/mode")
def set_llm_mode(data: ModeSwitch):
    s = get_settings()
    if data.mode in VALID_MODES:
        s.mode = data.mode
        update_settings(s)
    return {"mode": get_mode_safe(), "models": MODELS}


def get_mode_safe() -> str:
    try:
        return get_settings().mode
    except Exception:
        return _llm_get_mode()


# ── Book-level settings (config layering) ──────────────────────────────────


@router.get("/books/{book_id}/settings")
def get_book_settings(book_id: str):
    """Get per-book setting overrides."""
    s = get_settings()
    override = s.get_book_override(book_id)
    if override:
        return {
            "book_id": book_id,
            "overrides": {
                "mode": override.mode,
                "slot_pro_provider_id": override.slot_pro_provider_id,
                "slot_pro_model": override.slot_pro_model,
                "slot_flash_provider_id": override.slot_flash_provider_id,
                "slot_flash_model": override.slot_flash_model,
            },
        }
    return {"book_id": book_id, "overrides": None}


@router.put("/books/{book_id}/settings")
def update_book_settings(book_id: str, data: BookSettingsUpdate):
    """Update per-book setting overrides."""
    s = get_settings()
    if data.mode and data.mode not in VALID_MODES:
        raise HTTPException(400, f"Invalid mode: {data.mode}")

    def _normalized_book_slot(provider_id: str, model: str, global_slot: ModelSlot) -> tuple[str, str]:
        effective_provider_id = provider_id or global_slot.provider_id
        provider = s.get_provider(effective_provider_id)
        if provider_id and provider is None:
            raise HTTPException(400, f"Provider not found: {provider_id}")
        if model:
            if provider is None or model not in provider.models:
                raise HTTPException(400, f"Model not found in provider: {model}")
            return provider_id, model
        if provider_id:
            if not provider.models:
                raise HTTPException(400, f"Provider has no models: {provider_id}")
            return provider_id, provider.models[0]
        return "", ""

    pro_provider_id, pro_model = _normalized_book_slot(
        data.slot_pro_provider_id,
        data.slot_pro_model,
        s.slot_pro,
    )
    flash_provider_id, flash_model = _normalized_book_slot(
        data.slot_flash_provider_id,
        data.slot_flash_model,
        s.slot_flash,
    )
    override = BookOverrides(
        mode=data.mode,
        slot_pro_provider_id=pro_provider_id,
        slot_pro_model=pro_model,
        slot_flash_provider_id=flash_provider_id,
        slot_flash_model=flash_model,
    )
    s.book_overrides[book_id] = override
    update_settings(s)

    return {
        "book_id": book_id,
        "overrides": {
            "mode": override.mode,
            "slot_pro_provider_id": override.slot_pro_provider_id,
            "slot_pro_model": override.slot_pro_model,
            "slot_flash_provider_id": override.slot_flash_provider_id,
            "slot_flash_model": override.slot_flash_model,
        },
    }


@router.delete("/books/{book_id}/settings")
def delete_book_settings(book_id: str):
    """Delete per-book overrides, resetting to global settings."""
    s = get_settings()
    if book_id in s.book_overrides:
        del s.book_overrides[book_id]
        update_settings(s)
    return {"book_id": book_id, "overrides": None, "message": "已重置为全局设置"}


@router.get("/settings/effective/{book_id}")
def get_effective_settings(book_id: str):
    """Get merged settings with book-level overrides applied."""
    s = get_settings()
    effective = s.get_effective(book_id)
    d = effective.to_dict(mask_keys=True)
    d["models"] = MODELS
    d["valid_modes"] = list(VALID_MODES)
    d["valid_provider_types"] = list(VALID_PROVIDER_TYPES)
    d["task_types"] = list(TASK_TYPES)
    d["effort_tiers"] = reasoning_tier_meta(effective)

    # Include info about whether overrides are active
    original_override = s.get_book_override(book_id)
    d["has_book_overrides"] = original_override is not None and not original_override.is_empty()
    return d
