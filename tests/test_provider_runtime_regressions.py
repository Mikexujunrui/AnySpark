import json
from pathlib import Path

import pytest

from core import llm_client, token_counter
from core.extractor import proposal_from_dict
from core.settings import AppSettings, BookOverrides, GenerationSettings, ModelSlot, ProviderConfig
from routes import chat as chat_routes
from routes import settings as settings_routes


def test_token_count_falls_back_when_frozen_encoder_plugin_is_missing(monkeypatch):
    monkeypatch.setattr(token_counter, "_encoder", None)
    monkeypatch.setattr(token_counter, "_encoder_unavailable", False)

    def missing_encoder(*_args, **_kwargs):
        raise ValueError("Plugins found: []")

    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", missing_encoder)
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", missing_encoder)

    assert token_counter.count_tokens("中文测试") >= 4
    assert token_counter.count_message_tokens([{"role": "user", "content": "模型必须收到请求"}]) > 0


def test_generation_output_limit_is_portable():
    assert GenerationSettings(max_output_tokens=384000).normalized().max_output_tokens == 65536
    assert llm_client._portable_completion_kwargs({"temperature": 1.0, "max_tokens": 384000}) == {
        "temperature": 1.0,
        "max_tokens": 16384,
    }


def test_first_configured_provider_replaces_unusable_default_slots(monkeypatch):
    settings = AppSettings(
        providers=[
            ProviderConfig(
                id="deepseek-default",
                name="DeepSeek 默认",
                type="openai",
                api_key="",
                base_url="https://api.deepseek.com",
                models=["deepseek-chat"],
            )
        ],
        slot_pro=ModelSlot("deepseek-default", "deepseek-chat"),
        slot_flash=ModelSlot("deepseek-default", "deepseek-chat"),
    )
    monkeypatch.setattr(settings_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(settings_routes, "update_settings", lambda value: value)
    monkeypatch.setattr(settings_routes, "reload_clients", lambda: None)

    response = settings_routes.upsert_provider(
        settings_routes.ProviderUpdate(
            id="working",
            name="Working Provider",
            type="openai",
            api_key="secret",
            base_url="http://127.0.0.1:18080/v1",
            models=["mock-model"],
        )
    )

    assert response["slot_pro"] == {"provider_id": "working", "model": "mock-model"}
    assert response["slot_flash"] == {"provider_id": "working", "model": "mock-model"}


def test_book_override_controls_model_resolution(monkeypatch):
    settings = AppSettings(
        providers=[
            ProviderConfig("global", "Global", "openai", "key", "http://global/v1", ["global-model"]),
            ProviderConfig("book", "Book", "openai", "key", "http://book/v1", ["book-model"]),
        ],
        slot_pro=ModelSlot("global", "global-model"),
        slot_flash=ModelSlot("global", "global-model"),
        mode="quality",
        book_overrides={
            "book-1": BookOverrides(
                slot_pro_provider_id="book",
                slot_pro_model="book-model",
            )
        },
    )
    import core.settings as settings_module

    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    with llm_client.llm_book_context("book-1"):
        assert llm_client._resolve("writing") == ("book", "book-model")
    assert llm_client._resolve("writing") == ("global", "global-model")


def test_stream_proposal_can_be_reused_without_second_extraction():
    proposal = proposal_from_dict(
        {
            "entities": [{"id": "e1", "type": "character", "name": "小明", "aliases": [], "data": {}}],
            "relations": [{"id": "r1", "from": "e1", "to": "e2", "type": "knows"}],
            "foreshadows": [{"id": "f1", "text": "旧钥匙", "hint": "会再次出现"}],
        }
    )
    assert proposal.entities[0].name == "小明"
    assert proposal.relations[0].type == "knows"
    assert proposal.foreshadows[0].hint == "会再次出现"


@pytest.mark.asyncio
async def test_write_shortcut_surfaces_worker_error(monkeypatch):
    def broken_stream(*_args, **_kwargs):
        raise RuntimeError("max_tokens is too large")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_routes, "write_stream", broken_stream)
    monkeypatch.setattr(chat_routes, "_persist_turn", lambda *_args, **_kwargs: None)

    events = [
        event
        async for event in chat_routes._write_shortcut(
            "测试",
            "strict",
            "book-1",
            "session-1",
            "/w 测试",
        )
    ]
    done = next(event for event in events if event["event"] == "done")
    payload = json.loads(done["data"])
    assert payload["success"] is False
    assert "max_tokens is too large" in payload["message"]


def test_desktop_specs_package_runtime_prompts_and_tiktoken_plugins():
    root = Path(__file__).resolve().parents[1]
    mac_spec = (root / "anyspark_macos.spec").read_text(encoding="utf-8")
    win_spec = (root / "novel.spec").read_text(encoding="utf-8")
    assert '("src/core/prompts", "core/prompts")' in mac_spec
    assert "tiktoken_ext.openai_public" in mac_spec
    assert "('src/core/prompts', 'core/prompts')" in win_spec
    assert "tiktoken_ext.openai_public" in win_spec
