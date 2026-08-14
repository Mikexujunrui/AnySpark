"""S131 多协议适配器：协议注册表字段 + 三个新协议（anthropic/gemini/responses）转换测试。

转换函数为纯函数（无网络），直接断言；注册表协议字段走 SQLite。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from anyspark.core.protocol import ParamSpec, ToolSpec
from anyspark.core.types import Message
from anyspark.models.anthropic import (
    AnthropicModel,
    thinking_to_anthropic,
    to_anthropic_messages,
    to_anthropic_tool,
)
from anyspark.models.gemini import (
    GeminiModel,
    thinking_to_gemini,
    to_gemini_contents,
    to_gemini_tool,
)
from anyspark.models.registry import (
    ModelConfig,
    ModelProvider,
    ModelRegistry,
    validate_protocol,
)
from anyspark.models.responses import (
    ResponsesModel,
    thinking_to_responses,
    to_responses_input,
    to_responses_tool,
)


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test.db"


def _spec() -> ToolSpec:
    return ToolSpec(
        name="write_chapter",
        description="写章节",
        params=[ParamSpec(name="title", type="string", required=True)],
    )


def _messages() -> list[Message]:
    """带工具调用配对的完整消息流（system + user + assistant(tool_calls) + tool + assistant）。"""
    return [
        Message(role="system", content="你是小说家"),
        Message(role="user", content="写一段"),
        Message(
            role="assistant",
            content="好的",
            metadata={
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "write_chapter",
                        "arguments": {"title": "第一章"},
                    }
                ]
            },
        ),
        Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="完成"),
    ]


# ---------------------------------------------------------------------------
# 注册表 protocol 字段
# ---------------------------------------------------------------------------


def test_registry_protocol_defaults_openai() -> None:
    """旧配置/新配置缺省 protocol=openai（向后兼容）。"""
    reg = ModelRegistry(_db())
    assert reg.active().protocol == "openai"


def test_registry_protocol_crud_and_activate() -> None:
    reg = ModelRegistry(_db())
    cfg = ModelConfig(
        id="claude",
        name="Claude",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-4-5",
        thinking="high",
        protocol="anthropic",
    )
    reg.upsert(cfg)
    saved = reg.get("claude")
    assert saved is not None and saved.protocol == "anthropic"
    # to_dict 暴露 protocol（前端回填编辑表单用）
    assert saved.to_dict()["protocol"] == "anthropic"
    reg.activate("claude")
    assert reg.active().protocol == "anthropic"


def test_registry_protocol_upsert_validation() -> None:
    reg = ModelRegistry(_db())
    with pytest.raises(ValueError):
        reg.upsert(
            ModelConfig(
                id="bad",
                name="坏协议",
                base_url="http://x",
                model="m",
                protocol="bogus",
            )
        )


def test_registry_legacy_db_migration_adds_protocol_column() -> None:
    """旧库（无 protocol 列）打开后自动 ALTER 加列，默认 openai 不丢数据。"""
    db = _db()
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE model_configs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, base_url TEXT NOT NULL,
            model TEXT NOT NULL, api_key TEXT, context_window INTEGER NOT NULL,
            max_tokens INTEGER NOT NULL, temperature REAL NOT NULL, thinking TEXT,
            is_active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO model_configs VALUES ('default','DeepSeek','http://x','m','k',"
        "65536,8192,0.7,'medium',1,'t','t')"
    )
    conn.commit()
    conn.close()

    reg = ModelRegistry(db)
    assert reg.active().id == "default"
    assert reg.active().protocol == "openai"


def test_validate_protocol() -> None:
    assert validate_protocol("") == "openai"
    assert validate_protocol(None) == "openai"
    assert validate_protocol("ANTHROPIC") == "anthropic"
    with pytest.raises(ValueError):
        validate_protocol("ollama")  # 本地走 openai 协议（base_url 指本地端点）


# ---------------------------------------------------------------------------
# ModelProvider 按协议分发
# ---------------------------------------------------------------------------


def test_provider_builds_by_protocol() -> None:
    """ModelProvider.build 按激活配置 protocol 分发到对应适配器。"""
    reg = ModelRegistry(_db())
    # anthropic/gemini/responses 协议走内置工厂
    for protocol, cls in [
        ("anthropic", AnthropicModel),
        ("gemini", GeminiModel),
        ("responses", ResponsesModel),
    ]:
        reg.upsert(
            ModelConfig(
                id=f"m-{protocol}",
                name=protocol,
                base_url="http://localhost:1",
                model="m",
                api_key="k",
                protocol=protocol,
            )
        )
        reg.activate(f"m-{protocol}")
        inst = ModelProvider(reg).build()
        assert isinstance(inst, cls), f"{protocol} -> {type(inst)}"
    # openai 协议走注入工厂
    reg.upsert(
        ModelConfig(
            id="m-openai",
            name="openai",
            base_url="http://localhost:1",
            model="m",
            api_key="k",
            protocol="openai",
        )
    )
    reg.activate("m-openai")
    fake = object()

    def fake_factory(**kwargs: object) -> Any:
        return fake

    assert ModelProvider(reg, client_factory=fake_factory).build() is fake


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def test_anthropic_thinking_mapping() -> None:
    assert thinking_to_anthropic(None) is None
    assert thinking_to_anthropic("off") is None
    assert thinking_to_anthropic("low") == {"type": "enabled", "budget_tokens": 2048}
    assert thinking_to_anthropic("max") == {"type": "enabled", "budget_tokens": 32768}
    with pytest.raises(ValueError):
        thinking_to_anthropic("nonsense")


def test_anthropic_tool_conversion() -> None:
    tool = to_anthropic_tool(_spec())
    assert tool["name"] == "write_chapter"
    assert tool["input_schema"]["required"] == ["title"]
    assert tool["input_schema"]["properties"]["title"]["type"] == "string"


def test_anthropic_message_conversion() -> None:
    """system 上提 + assistant tool_calls → tool_use 块 + tool 消息合并为 user。"""
    system, conv = to_anthropic_messages(_messages())
    assert system == "你是小说家"
    assert [c["role"] for c in conv] == ["user", "assistant", "user", "assistant"]
    # assistant 第二个消息（含 tool_calls）→ tool_use 块
    asst = conv[1]
    assert asst["content"][0]["type"] == "text"
    assert asst["content"][1]["type"] == "tool_use"
    assert asst["content"][1]["name"] == "write_chapter"
    assert asst["content"][1]["input"] == {"title": "第一章"}
    # tool 消息 → user + tool_result（tool_use_id 配对）
    tool_user = conv[2]
    assert tool_user["content"][0]["type"] == "tool_result"
    assert tool_user["content"][0]["tool_use_id"] == "c1"
    assert tool_user["content"][0]["content"] == "已保存"


def test_anthropic_adjacent_same_role_merged() -> None:
    """连续同角色消息合并（Anthropic 严格交替 user/assistant）。"""
    msgs = [
        Message(role="user", content="a"),
        Message(role="user", content="b"),
        Message(role="assistant", content="x"),
        Message(role="assistant", content="y"),
    ]
    _, conv = to_anthropic_messages(msgs)
    assert [c["role"] for c in conv] == ["user", "assistant"]
    assert conv[0]["content"] == "a\nb"


def test_anthropic_thinking_forces_temperature_one() -> None:
    """thinking enabled 时 temperature 强制 1（Anthropic 硬性限制）。"""
    model = AnthropicModel(api_key="sk-test", thinking="high")
    assert model._thinking == {"type": "enabled", "budget_tokens": 8192}
    payload = model._payload(_messages(), [_spec()], stream=False)
    assert payload["temperature"] == 1.0
    assert payload["thinking"]["budget_tokens"] == 8192


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def test_gemini_thinking_mapping() -> None:
    assert thinking_to_gemini(None) is None
    assert thinking_to_gemini("off") == {"thinkingBudget": 0}
    assert thinking_to_gemini("high") == {"thinkingBudget": 8192}
    assert thinking_to_gemini("max") == {"thinkingBudget": 32768}
    with pytest.raises(ValueError):
        thinking_to_gemini("nonsense")


def test_gemini_tool_conversion() -> None:
    tool = to_gemini_tool(_spec())
    assert tool["name"] == "write_chapter"
    assert tool["parameters"]["required"] == ["title"]


def test_gemini_message_conversion() -> None:
    """system → systemInstruction；assistant tool_calls → functionCall；tool → functionResponse。"""
    system, contents = to_gemini_contents(_messages())
    assert system == "你是小说家"
    assert [c["role"] for c in contents] == ["user", "model", "user", "model"]
    # assistant 含 tool_calls → functionCall part
    model_msg = contents[1]
    assert model_msg["parts"][0]["text"] == "好的"
    assert model_msg["parts"][1]["functionCall"]["name"] == "write_chapter"
    assert model_msg["parts"][1]["functionCall"]["args"] == {"title": "第一章"}
    # tool → functionResponse
    tool_user = contents[2]
    assert tool_user["parts"][0]["functionResponse"]["name"] == "c1"


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def test_responses_thinking_mapping() -> None:
    assert thinking_to_responses(None) is None
    assert thinking_to_responses("off") is None
    assert thinking_to_responses("low") == {"effort": "low"}
    assert thinking_to_responses("xhigh") == {"effort": "high"}  # 封顶档位映射
    with pytest.raises(ValueError):
        thinking_to_responses("nonsense")


def test_responses_tool_conversion() -> None:
    """Responses 工具是扁平结构（type/name 平级，非 Completions 嵌套 function）。"""
    tool = to_responses_tool(_spec())
    assert tool["type"] == "function"
    assert tool["name"] == "write_chapter"
    assert tool["parameters"]["required"] == ["title"]


def test_responses_input_conversion() -> None:
    """system 消息 + assistant function_call item + tool function_call_output item。"""
    inp = to_responses_input(_messages())
    assert inp[0] == {"role": "system", "content": "你是小说家"}
    # assistant 文本 → 消息；tool_calls → 顶层 function_call item
    assert inp[1]["role"] == "assistant"
    assert inp[2]["type"] == "function_call"
    assert inp[2]["call_id"] == "c1"
    assert inp[2]["name"] == "write_chapter"
    # tool → function_call_output（配对）
    assert inp[3]["type"] == "function_call_output"
    assert inp[3]["call_id"] == "c1"
    assert inp[3]["output"] == "已保存"
