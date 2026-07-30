import httpx
import pytest

from core.model_discovery import ModelDiscoveryError, discover_models, provider_base_url


def test_openai_discovery_falls_back_to_v1_and_deduplicates():
    requested = []

    def handler(request: httpx.Request):
        requested.append(str(request.url))
        assert request.headers["authorization"] == "Bearer sk-test"
        if request.url.path == "/models":
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-z"}, {"id": "gpt-a"}, {"id": "gpt-a"}]},
        )

    models, endpoint = discover_models(
        "openai",
        "sk-test",
        "https://gateway.example.com",
        transport=httpx.MockTransport(handler),
    )

    assert requested == [
        "https://gateway.example.com/models",
        "https://gateway.example.com/v1/models",
    ]
    assert models == ["gpt-a", "gpt-z"]
    assert endpoint.endswith("/v1/models")


def test_anthropic_discovery_uses_saved_compatible_headers():
    def handler(request: httpx.Request):
        assert str(request.url) == "https://api.anthropic.com/v1/models"
        assert request.headers["x-api-key"] == "sk-ant-test"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"data": [{"id": "claude-sonnet"}, {"id": "claude-opus"}]})

    models, _ = discover_models(
        "anthropic",
        "sk-ant-test",
        transport=httpx.MockTransport(handler),
    )
    assert models == ["claude-opus", "claude-sonnet"]


def test_gemini_discovery_uses_openai_compatibility_endpoint():
    def handler(request: httpx.Request):
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/openai/models"
        return httpx.Response(200, json={"data": [{"id": "gemini-flash"}, {"id": "gemini-pro"}]})

    models, _ = discover_models(
        "gemini",
        "gemini-key",
        transport=httpx.MockTransport(handler),
    )
    assert models == ["gemini-flash", "gemini-pro"]


def test_discovery_accepts_native_models_name_shape():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-flash"}, {"name": "models/gemini-pro"}]},
        )
    )
    models, _ = discover_models("openai", "key", "https://example.com/v1", transport=transport)
    assert models == ["gemini-flash", "gemini-pro"]


def test_discovery_requires_key_and_valid_url():
    with pytest.raises(ModelDiscoveryError, match="API Key"):
        discover_models("openai", "", "https://example.com/v1")
    with pytest.raises(ModelDiscoveryError, match="Base URL"):
        provider_base_url("openai", "not-a-url")


def test_official_provider_defaults():
    assert provider_base_url("openai") == "https://api.openai.com/v1"
    assert provider_base_url("anthropic") == "https://api.anthropic.com/v1"
    assert provider_base_url("gemini").endswith("/v1beta/openai")
