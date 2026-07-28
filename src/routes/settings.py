"""Settings API routes for multi-provider configuration."""

import logging
import time

from fastapi import APIRouter, HTTPException
from httpx import Timeout
from openai import OpenAI
from pydantic import BaseModel

from core.llm_client import MODELS, reload_clients
from core.llm_client import get_mode as _llm_get_mode
from core.settings import (
    TASK_TYPES,
    VALID_MODES,
    VALID_PROVIDER_TYPES,
    BookOverrides,
    ModelSlot,
    ProviderConfig,
    get_settings,
    update_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


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


class BookSettingsUpdate(BaseModel):
    mode: str = ""
    slot_pro_provider_id: str = ""
    slot_pro_model: str = ""
    slot_flash_provider_id: str = ""
    slot_flash_model: str = ""


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
    if data.type == "openai" and not data.base_url:
        raise HTTPException(400, "base_url is required for openai-compatible providers")
    if not data.models:
        raise HTTPException(400, "At least one model is required")

    s = get_settings()
    provider = ProviderConfig(
        id=data.id.strip(),
        name=data.name.strip(),
        type=data.type,
        api_key=data.api_key,
        base_url=data.base_url,
        models=data.models,
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
        if not s.get_provider(data.slot_pro_provider_id):
            raise HTTPException(400, f"Provider not found: {data.slot_pro_provider_id}")
        s.slot_pro.provider_id = data.slot_pro_provider_id
    if data.slot_pro_model:
        s.slot_pro.model = data.slot_pro_model

    if data.slot_flash_provider_id:
        if not s.get_provider(data.slot_flash_provider_id):
            raise HTTPException(400, f"Provider not found: {data.slot_flash_provider_id}")
        s.slot_flash.provider_id = data.slot_flash_provider_id
    if data.slot_flash_model:
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
            base_url=provider.base_url or "https://api.openai.com/v1",
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

    override = BookOverrides(
        mode=data.mode,
        slot_pro_provider_id=data.slot_pro_provider_id,
        slot_pro_model=data.slot_pro_model,
        slot_flash_provider_id=data.slot_flash_provider_id,
        slot_flash_model=data.slot_flash_model,
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

    # Include info about whether overrides are active
    original_override = s.get_book_override(book_id)
    d["has_book_overrides"] = original_override is not None and not original_override.is_empty()
    return d
