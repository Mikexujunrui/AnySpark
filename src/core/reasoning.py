# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Model parameter tier mapping — thinking/reasoning strength.

Users pick from a single **five-tier scale** (``off / minimal / low / medium /
high``) regardless of which model is in use. Each *model family* then declares
the tiers it actually supports and how a tier maps onto that family's native
request parameters. This replaces the earlier fixed 4-tier scheme where every
model got ``off/low/medium/high`` even though real families differ:

  - DeepSeek (OpenAI-compat)  → ``reasoning_effort`` with 3 tiers
  - OpenAI o-series           → ``reasoning_effort`` with 4 tiers
  - Anthropic native          → ``thinking.budget_tokens`` (budget scale)
  - Gemini OpenAI-compat      → ``thinkingConfig.thinkingBudget`` (budget scale)

Family lookup is driven by ``provider_type`` plus model-name markers, and the
built-in table can be extended per-user through ``settings.json``
(``custom_family_tiers``). All parameters are injected via the OpenAI SDK
``extra_body`` so every provider path shares the same plumbing; gateways that
reject unknown keys are handled by the existing portable-kwargs fallback in
:mod:`core.llm_client`.
"""

from __future__ import annotations

from typing import Any

# ── Unified tier scale ──────────────────────────────────────────────────────
# ``off`` is common to every family; the other four are the strength rungs.
EFFORT_TIERS = ("off", "minimal", "low", "medium", "high")
EFFORT_ORDER = {tier: index for index, tier in enumerate(EFFORT_TIERS)}


def normalize_reasoning_effort(effort: str | None) -> str:
    """Coerce a user-supplied effort to a valid tier (default ``medium``)."""
    value = (effort or "").strip().lower()
    return value if value in EFFORT_ORDER else "medium"


# ── Built-in model family tiers ─────────────────────────────────────────────
# Each family config:
#   markers         — model-name substrings that identify the family
#   provider_types  — provider types this family applies to
#   mode            — "enum" | "budget_anthropic" | "budget_gemini"
#   tiers           — tier → native value (enum string, or token budget int)
_BUILTIN_FAMILIES: dict[str, dict[str, Any]] = {
    "deepseek": {
        "markers": ("deepseek",),
        "provider_types": ("openai",),
        "mode": "enum",
        "tiers": {"low": "low", "medium": "medium", "high": "high"},
    },
    "openai_o": {
        "markers": ("o1", "o3", "o4"),
        "provider_types": ("openai",),
        "mode": "enum",
        "tiers": {"minimal": "minimal", "low": "low", "medium": "medium", "high": "high"},
    },
    "anthropic": {
        "markers": (),
        "provider_types": ("anthropic",),
        "mode": "budget_anthropic",
        "tiers": {"low": 2048, "medium": 8192, "high": 16384},
    },
    "gemini": {
        "markers": (),
        "provider_types": ("gemini",),
        "mode": "budget_gemini",
        "tiers": {"low": 1024, "medium": 4096, "high": 8192},
    },
}


def _merged_families(custom: dict | None) -> dict[str, dict[str, Any]]:
    """Built-in families overlaid with user-supplied custom families."""
    families = {name: dict(cfg) for name, cfg in _BUILTIN_FAMILIES.items()}
    for name, cfg in (custom or {}).items():
        if isinstance(cfg, dict):
            merged = dict(families.get(name, {}))
            merged.update(cfg)
            families[name] = merged
    return families


def resolve_family(provider_type: str, model: str, custom: dict | None = None) -> dict[str, Any] | None:
    """Return the matching model-family tier config, or ``None``.

    Marker-matched families (e.g. DeepSeek / o-series on the OpenAI surface)
    take precedence; families keyed only by ``provider_type`` (Anthropic,
    Gemini) act as fallback so an unmatched model still gets budget mapping.
    """
    normalized = (model or "").lower()
    fallback: dict[str, Any] | None = None
    for cfg in _merged_families(custom).values():
        provider_types = cfg.get("provider_types") or ("openai",)
        if provider_type not in provider_types:
            continue
        markers = cfg.get("markers") or ()
        if markers:
            if any(marker in normalized for marker in markers):
                return cfg
        else:
            fallback = cfg
    return fallback


def family_tiers(provider_type: str, model: str, custom: dict | None = None) -> list[str]:
    """Return the tiers a family exposes, ``off`` first (for UI rendering)."""
    family = resolve_family(provider_type, model, custom)
    if family is None:
        return ["off"]
    return ["off"] + [tier for tier in EFFORT_TIERS if tier in (family.get("tiers") or {})]


def _nearest_tier(effort: str, available: set[str]) -> str:
    """Pick the closest supported tier by scale position (ties → higher)."""
    target = EFFORT_ORDER[effort]
    return min(available, key=lambda t: (abs(EFFORT_ORDER[t] - target), -EFFORT_ORDER[t]))


def _family_params(family: dict[str, Any], tier: str) -> dict[str, Any]:
    """Translate a family-resolved tier into an OpenAI-SDK kwargs fragment."""
    tiers = family.get("tiers") or {}
    value = tiers[tier]
    mode = family.get("mode", "enum")
    if mode == "budget_anthropic":
        return {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": value}}}
    if mode == "budget_gemini":
        return {"extra_body": {"thinkingConfig": {"thinkingBudget": value}}}
    return {"extra_body": {"reasoning_effort": value}}


def reasoning_effort_to_params(
    provider_type: str, model: str, effort: str = "medium", custom: dict | None = None
) -> dict[str, Any]:
    """Return request kwargs for the given reasoning tier.

    Returns an empty dict when the tier is ``off`` or no family matches the
    model. Unknown tiers snap to the nearest supported tier. The result is
    meant to be spread into ``client.chat.completions.create``.
    """
    tier = normalize_reasoning_effort(effort)
    if tier == "off":
        return {}
    family = resolve_family(provider_type, model, custom)
    if family is None:
        return {}
    tiers = family.get("tiers") or {}
    if tier not in tiers:
        tier = _nearest_tier(tier, set(tiers))
    return _family_params(family, tier)


def is_reasoning_model(model: str) -> bool:
    """Return whether ``model`` matches a known reasoning family."""
    return resolve_family("openai", model) is not None
