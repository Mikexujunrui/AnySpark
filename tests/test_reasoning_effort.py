# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for the reasoning-effort tier mapping and llm_client injection."""

import pytest

from core import llm_client
from core.reasoning import (
    EFFORT_TIERS,
    family_tiers,
    is_reasoning_model,
    normalize_reasoning_effort,
    reasoning_effort_to_params,
    resolve_family,
)
from core.settings import GenerationSettings

# ── mapping module ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "effort,expected",
    [
        ("off", "off"),
        ("minimal", "minimal"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("OFF", "off"),
        ("  high ", "high"),
        ("", "medium"),
        ("extreme", "medium"),
        (None, "medium"),
    ],
)
def test_normalize_reasoning_effort(effort, expected):
    assert normalize_reasoning_effort(effort) == expected


def test_effort_tiers_scale_order():
    assert EFFORT_TIERS == ("off", "minimal", "low", "medium", "high")


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o", False),
        ("claude-3-5-sonnet", False),
        ("deepseek-v4-pro", True),
        ("deepseek-reasoner", True),
        ("o1-mini", True),
        ("o3", True),
        ("o4-mini", True),
        ("gemini-2.5-flash", False),
    ],
)
def test_is_reasoning_model(model, expected):
    assert is_reasoning_model(model) is expected


def test_resolve_family_by_marker_and_provider():
    # Marker-matched families (openai surface) win over provider-only fallback.
    assert resolve_family("openai", "deepseek-v4-pro")["mode"] == "enum"
    assert resolve_family("openai", "o3-mini")["tiers"].get("minimal") is not None
    # Provider-only families (Anthropic/Gemini) act as fallback.
    assert resolve_family("anthropic", "claude-3-5-sonnet")["mode"] == "budget_anthropic"
    assert resolve_family("gemini", "gemini-2.5-flash")["mode"] == "budget_gemini"
    # Unmatched openai-compatible model → None.
    assert resolve_family("openai", "gpt-4o") is None


def test_family_tiers_vary_by_model():
    assert family_tiers("openai", "deepseek-v4-pro") == ["off", "low", "medium", "high"]
    assert family_tiers("openai", "o3-mini") == ["off", "minimal", "low", "medium", "high"]
    assert family_tiers("anthropic", "claude-x") == ["off", "low", "medium", "high"]
    assert family_tiers("gemini", "gemini-x") == ["off", "low", "medium", "high"]
    assert family_tiers("openai", "gpt-4o") == ["off"]


def test_off_returns_empty():
    assert reasoning_effort_to_params("openai", "o3", "off") == {}
    assert reasoning_effort_to_params("anthropic", "claude-x", "off") == {}
    assert reasoning_effort_to_params("gemini", "gemini-x", "off") == {}


def test_deepseek_uses_three_tier_reasoning_effort():
    params = reasoning_effort_to_params("openai", "deepseek-v4-pro", "high")
    assert params == {"extra_body": {"reasoning_effort": "high"}}
    params = reasoning_effort_to_params("openai", "deepseek-v4-pro", "low")
    assert params == {"extra_body": {"reasoning_effort": "low"}}


def test_deepseek_minimal_snaps_to_low():
    # deepseek has no "minimal"; nearest tier is low.
    params = reasoning_effort_to_params("openai", "deepseek-v4-pro", "minimal")
    assert params == {"extra_body": {"reasoning_effort": "low"}}


def test_openai_o_series_supports_minimal():
    params = reasoning_effort_to_params("openai", "o3-mini", "minimal")
    assert params == {"extra_body": {"reasoning_effort": "minimal"}}


def test_openai_compat_non_reasoning_model_gets_nothing():
    assert reasoning_effort_to_params("openai", "gpt-4o", "high") == {}


def test_anthropic_uses_thinking_budget():
    params = reasoning_effort_to_params("anthropic", "claude-x", "low")
    assert params == {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 2048}}}
    params = reasoning_effort_to_params("anthropic", "claude-x", "high")
    assert params["extra_body"]["thinking"]["budget_tokens"] == 16384


def test_gemini_uses_thinking_budget():
    params = reasoning_effort_to_params("gemini", "gemini-x", "low")
    assert params == {"extra_body": {"thinkingConfig": {"thinkingBudget": 1024}}}
    params = reasoning_effort_to_params("gemini", "gemini-x", "high")
    assert params["extra_body"]["thinkingConfig"]["thinkingBudget"] == 8192


def test_invalid_effort_falls_back_to_medium():
    params = reasoning_effort_to_params("openai", "o3", "bogus")
    assert params == {"extra_body": {"reasoning_effort": "medium"}}


def test_custom_family_overrides_builtin():
    custom = {
        "deepseek": {
            "markers": ("deepseek",),
            "provider_types": ("openai",),
            "mode": "enum",
            "tiers": {"low": "light", "medium": "balanced", "high": "deep"},
        }
    }
    params = reasoning_effort_to_params("openai", "deepseek-v4-pro", "high", custom=custom)
    assert params == {"extra_body": {"reasoning_effort": "deep"}}


def test_custom_family_adds_new_mapping():
    custom = {
        "mygw": {
            "markers": ("mythink",),
            "provider_types": ("openai",),
            "mode": "enum",
            "tiers": {"low": "light", "medium": "balanced", "high": "deep"},
        }
    }
    params = reasoning_effort_to_params("openai", "mythink-1", "high", custom=custom)
    assert params == {"extra_body": {"reasoning_effort": "deep"}}
    assert family_tiers("openai", "mythink-1", custom=custom) == ["off", "low", "medium", "high"]


# ── GenerationSettings ───────────────────────────────────────────────────────


def test_generation_settings_normalizes_effort():
    g = GenerationSettings(reasoning_effort="HIGH").normalized()
    assert g.reasoning_effort == "high"
    g = GenerationSettings(reasoning_effort="weird").normalized()
    assert g.reasoning_effort == "medium"
    g = GenerationSettings(reasoning_effort="minimal").normalized()
    assert g.reasoning_effort == "minimal"


def test_generation_settings_roundtrip_keeps_custom_families():
    s = GenerationSettings(reasoning_effort="high").normalized()
    assert s.reasoning_effort == "high"


# ── llm_client injection ─────────────────────────────────────────────────────


def test_apply_reasoning_params_merges_extra_body(monkeypatch):
    def fake_settings():
        s = type("S", (), {"generation": GenerationSettings(reasoning_effort="high")})()
        return s

    monkeypatch.setattr(llm_client, "_settings", fake_settings)
    kwargs = {"temperature": 0.7, "max_tokens": 4096}
    result = llm_client._apply_reasoning_params(kwargs, "provider", "o3-mini")
    assert result["extra_body"] == {"reasoning_effort": "high"}
    assert result["temperature"] == 0.7


def test_apply_reasoning_params_merges_existing_extra_body(monkeypatch):
    def fake_settings():
        s = type("S", (), {"generation": GenerationSettings(reasoning_effort="low")})()
        return s

    monkeypatch.setattr(llm_client, "_settings", fake_settings)
    kwargs = {"extra_body": {"other": 1}}
    result = llm_client._apply_reasoning_params(kwargs, "provider", "o3-mini")
    assert result["extra_body"] == {"other": 1, "reasoning_effort": "low"}


def test_apply_reasoning_params_off_returns_kwargs_unchanged(monkeypatch):
    def fake_settings():
        s = type("S", (), {"generation": GenerationSettings(reasoning_effort="off")})()
        return s

    monkeypatch.setattr(llm_client, "_settings", fake_settings)
    kwargs = {"temperature": 0.7}
    assert llm_client._apply_reasoning_params(kwargs, "provider", "o3-mini") is kwargs


def test_apply_reasoning_params_anthropic_budget(monkeypatch):
    def fake_settings():
        s = type("S", (), {"generation": GenerationSettings(reasoning_effort="high")})()
        return s

    def fake_provider_type(provider_id):
        return "anthropic"

    monkeypatch.setattr(llm_client, "_settings", fake_settings)
    monkeypatch.setattr(llm_client, "_provider_type", fake_provider_type)
    result = llm_client._apply_reasoning_params(kwargs={"temperature": 0.7}, provider_id="p", model="claude-x")
    assert result["extra_body"] == {"thinking": {"type": "enabled", "budget_tokens": 16384}}


def test_portable_kwargs_drops_extra_body():
    kwargs = {"temperature": 1.0, "max_tokens": 384000, "extra_body": {"reasoning_effort": "high"}}
    portable = llm_client._portable_completion_kwargs(kwargs)
    assert "extra_body" not in portable
    assert portable["max_tokens"] == 16384


def test_provider_type_fallback():
    assert llm_client._provider_type("nonexistent") == "openai"
    assert llm_client._provider_type("") == "openai"
