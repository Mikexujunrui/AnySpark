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


def test_anthropic_dangling_tool_use_removed() -> None:
    """S174：悬挂 tool_use 防御——assistant 声明了 tool_use 但后续无 tool_result
    → 移除未配对的 tool_use 块（否则 Anthropic 400 tool_use without tool_result）。"""

    msgs = [
        Message(role="user", content="提炼技能"),
        Message(
            role="assistant",
            content="",
            metadata={
                "tool_calls": [{"name": "skill_refine", "arguments": {}, "id": "call_00_xxx"}]
            },
        ),
        # 无 tool 消息——悬挂；直接接终答 assistant
        Message(role="assistant", content="完成"),
    ]
    _, conv = to_anthropic_messages(msgs)
    # 所有 assistant 的 tool_use 块应被移除（未配对）
    for c in conv:
        if c["role"] == "assistant" and isinstance(c["content"], list):
            assert not any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in c["content"]
            ), f"悬挂 tool_use 未移除: {c['content']}"


def test_anthropic_paired_tool_use_kept() -> None:
    """S174：正常配对的 tool_use 保留（防御不误伤）。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "write_chapter", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="写好了"),
    ]
    _, conv = to_anthropic_messages(msgs)
    asst = next(c for c in conv if c["role"] == "assistant" and isinstance(c["content"], list))
    assert any(
        isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == "c1"
        for b in asst["content"]
    )


def test_anthropic_system_only_falls_back_to_user() -> None:
    """S174：system-only 兜底——内部管道（资料消化/技能提炼）只传 [system]，
    system 上提后 messages 空 → Anthropic 400。降为 user 消息保调用可用。"""
    msgs = [Message(role="system", content="把以下材料消化成摘要卡：原文...")]
    system, conv = to_anthropic_messages(msgs)
    assert system is None  # system 降为 user
    assert len(conv) == 1
    assert conv[0]["role"] == "user"
    assert "消化成摘要卡" in conv[0]["content"]


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
    # tool → functionResponse（S176：name 从 assistant 声明补全为工具名，非 tool_call_id）
    tool_user = contents[2]
    assert tool_user["parts"][0]["functionResponse"]["name"] == "write_chapter"


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


# ---------------------------------------------------------------------------
# 防回归：全部工具 schema 严格校验（S136：mind_update locked 曾用 type="bool"）
# ---------------------------------------------------------------------------


def test_all_tool_schemas_valid_for_strict_apis(make_toolkit: Any) -> None:
    """全部工具参数 schema 合法——DeepSeek/OpenAI 官方 API 严格校验 JSON Schema。

    回归 S136：mind_update.locked 曾用 type="bool"（JSON Schema 非法类型），
    DashScope 宽容不报错、官方 API 直接 400。此测试锁死：参数类型只能是
    string/integer/number/boolean（与 core ParamSpec 契约一致）。
    """
    from anyspark.models.deepseek import to_openai_tool

    registry = make_toolkit()
    valid = {"string", "integer", "number", "boolean"}
    specs = registry.specs()
    assert len(specs) > 20, "工具集应非空（装配失败会漏测）"
    for spec in specs:
        tool = to_openai_tool(spec)
        props = tool["function"]["parameters"]["properties"]
        for pname, p in props.items():
            assert p["type"] in valid, (
                f"工具 {spec.name} 参数 {pname} 非法类型 {p['type']!r}——"
                "JSON Schema 合法类型仅 string/integer/number/boolean（官方 API 严格校验会 400）"
            )


def test_gemini_tool_name_backfilled_from_declaration() -> None:
    """S176：tool 消息缺 tool_name → 从 assistant 声明的 tool_calls 按 id 补工具名
    （loop 的 _append_tool_result 只设 tool_call_id 不设 tool_name）。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "write_chapter", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),  # 无 tool_name
        Message(role="assistant", content="完成"),
    ]
    _, contents = to_gemini_contents(msgs)
    fr = next(
        p["functionResponse"]
        for c in contents
        if c["role"] == "user"
        for p in c["parts"]
        if "functionResponse" in p
    )
    assert fr["name"] == "write_chapter"  # 补全为工具名，非 c1


def test_gemini_dangling_function_call_removed() -> None:
    """S176：悬挂 functionCall 防御——model 声明 functionCall 但无 functionResponse → 移除。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "x", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="assistant", content="完成"),  # 无 tool 消息
    ]
    _, contents = to_gemini_contents(msgs)
    fcs = [p for c in contents if c["role"] == "model" for p in c["parts"] if "functionCall" in p]
    assert fcs == []


def test_gemini_system_only_falls_back_to_user() -> None:
    """S176：system-only → contents 空 → 降为 user（保内部管道可用）。"""
    _, contents = to_gemini_contents([Message(role="system", content="消化材料")])
    assert len(contents) == 1
    assert contents[0]["role"] == "user"


def test_responses_dangling_function_call_removed() -> None:
    """S176：Responses 悬挂 function_call 防御——无对应 function_call_output → 移除。"""
    from anyspark.models.responses import to_responses_input

    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "x", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="assistant", content="完成"),  # 无 tool 消息
    ]
    result = to_responses_input(msgs)
    fcs = [i for i in result if isinstance(i, dict) and i.get("type") == "function_call"]
    assert fcs == []


def test_anthropic_tool_result_separated_by_user_reordered() -> None:
    """S201：tool_result 被 user 消息隔开（steer 插话在 tool_result 前）→
    通用守卫 sanitize 先把插话重排到 tool 组之后（不再移除内容），
    Anthropic 转换得到 tool_use 紧邻 tool_result 的合法序列。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "wc", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="user", content="别写太血腥"),  # steer 插话在 tool_result 前
        Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="完成"),
    ]
    _, conv = to_anthropic_messages(msgs)
    # 重排后：tool_use 紧邻 tool_result（不再被插话隔开），内容不丢失
    # 找 tool_use 所在 assistant 与 tool_result 所在 user 的相邻关系
    ok = False
    for i, m in enumerate(conv):
        if m["role"] == "assistant" and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in m["content"]
        ):
            assert i + 1 < len(conv), f"tool_use 后无消息: {conv}"
            nxt = conv[i + 1]
            assert nxt["role"] == "user"
            blocks = nxt["content"] if isinstance(nxt["content"], list) else []
            assert any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks), (
                f"tool_use 后未紧跟 tool_result: {conv}"
            )
            ok = True
            break
    assert ok, "转换结果中没有 tool_use"
    # 插话内容保留（重排后仍在对话里）
    all_text = " ".join(str(m.get("content")) for m in conv)
    assert "别写太血腥" in all_text, f"插话丢失: {all_text}"


def test_anthropic_partial_tool_use_pairing() -> None:
    """S182：同批多 tool_use 部分配对（c1 紧跟、c2 隔开）→ 保留 c1、移除 c2。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={
                "tool_calls": [
                    {"name": "a", "arguments": {}, "id": "c1"},
                    {"name": "b", "arguments": {}, "id": "c2"},
                ]
            },
        ),
        Message(role="tool", content="A", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="继续"),
        Message(role="tool", content="B", metadata={"tool_call_id": "c2"}),  # c2 隔开
        Message(role="assistant", content="完成"),
    ]
    _, conv = to_anthropic_messages(msgs)
    # c1 保留（紧跟配对），c2 移除
    asst = next(m for m in conv if m["role"] == "assistant" and isinstance(m["content"], list))
    ids = [b["id"] for b in asst["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
    assert ids == ["c1"], f"应只保留 c1: {ids}"


def test_anthropic_orphan_result_id_from_earlier_pair_not_leaked() -> None:
    """S189：孤儿 tool_result 穿透漏洞——旧防御把“任何一条 user 里的 tool_result id”
    全局累积放行，即使其 tool_use 早已被移除/截断（如跨协议切换后 id 错位、或历史
    压缩切断了配对）。此场景正是远端报错 messages.N.content.0: tool_use_id found in
    tool_result blocks 的根因之一：tool_result 的 id 在更早 assistant 声明过（理应
    合法），但其所在 user 的紧邻前一条 assistant 没有声明——必须整块移除。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "a", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="tool", content="A", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="继续"),  # 下一轮无工具声明
        # c2 的结果在非紧邻位置出现（c2 的声明被截断/跨协议重写丢失）——
        # 紧邻前一条 assistant 无声明 → c2 必须移除
        Message(
            role="tool",
            content="B",
            metadata={"tool_call_id": "call_00_AMViPwzwBTeTo78umhQ87951"},
        ),
        Message(role="assistant", content="完成"),
    ]
    _, conv = to_anthropic_messages(msgs)
    # 无该孤儿 id 的 tool_use 或 tool_result 残留
    for c in conv:
        blocks = c["content"] if isinstance(c["content"], list) else []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                assert b.get("id") != "call_00_AMViPwzwBTeTo78umhQ87951"
            if isinstance(b, dict) and b.get("type") == "tool_result":
                assert b.get("tool_use_id") != "call_00_AMViPwzwBTeTo78umhQ87951", (
                    f"孤儿 tool_result 应被移除: {b}"
                )
    # 正常配对的 c1 保留
    all_results = [
        b
        for c in conv
        if c["role"] == "user"
        for b in (c["content"] if isinstance(c["content"], list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert [b["tool_use_id"] for b in all_results] == ["c1"]


def test_anthropic_empty_result_id_removed() -> None:
    """S189：tool 消息缺 tool_call_id（历史/前端覆盖丢失）→ 空串 tool_use_id，
    无 assistant 声明可配对 → 整块移除（旧实现空串 id 会因“任意合法 id 集合”
    全局累积被误留 → 400）。"""
    msgs = [
        Message(role="user", content="写"),
        Message(
            role="assistant",
            content="",
            metadata={"tool_calls": [{"name": "a", "arguments": {}, "id": "c1"}]},
        ),
        Message(role="tool", content="A", metadata={"tool_call_id": "c1"}),
        Message(role="assistant", content="继续"),
        Message(role="tool", content="B", metadata={}),  # 缺 tool_call_id
        Message(role="assistant", content="完成"),
    ]
    _, conv = to_anthropic_messages(msgs)
    for c in conv:
        if c["role"] == "user" and isinstance(c["content"], list):
            for b in c["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    assert b.get("tool_use_id") != "", f"空 id tool_result 应移除: {b}"


def test_gemini_array_param_gets_items() -> None:
    """S204：Gemini functionDeclarations 对 array 参数必须提供 items——
    否则真实用户 400 `properties[xxx].items: missing field`（自定义工具 array 参数）。"""
    from anyspark.core.protocol import ParamSpec, ToolSpec

    spec = ToolSpec(
        name="batch_apply",
        description="批量应用补丁",
        params=[
            ParamSpec(name="patches", type="array", required=True, description="补丁列表"),
            ParamSpec(name="count", type="integer", required=False, description="数量"),
        ],
    )
    tool = to_gemini_tool(spec)
    params = tool["parameters"]
    # Gemini schema：type 大写枚举
    assert params["type"] == "OBJECT"
    patches = params["properties"]["patches"]
    assert patches["type"] == "ARRAY"
    assert "items" in patches, f"array 参数缺 items: {patches}"
    assert patches["items"]["type"] == "STRING"
    # 非 array 参数不受影响
    assert params["properties"]["count"]["type"] == "INTEGER"


def test_anthropic_thinking_blocks_preserved_in_roundtrip() -> None:
    """S232：thinking 块（含 signature）随 assistant 消息回传——

    开启 thinking + 工具调用时，Anthropic 要求完整原样回传 thinking 块
    （含 signature，不可修改），否则 400「thinking blocks cannot be modified」。
    旧实现丢弃 reasoning_blocks，只存 reasoning 文本，回传时 assistant 消息
    无 thinking 块 → 后续工具调用请求 400。
    """
    sig = "EqoBCgIACgoKCGNsaXBweS1vc2IKRWRpc29uLW9uLXRoZS1jbGlmZQo="
    msgs = [
        Message(role="user", content="写一章"),
        Message(
            role="assistant",
            content="好的，调用写章工具。",
            metadata={
                "tool_calls": [
                    {"name": "write_chapter", "arguments": {"title": "第一章"}, "id": "c1"}
                ],
                # S232：完整 thinking 块结构（含 signature）——回传必需
                "reasoning_blocks": [
                    {"type": "thinking", "thinking": "让我构思一下开头…", "signature": sig},
                ],
            },
        ),
        Message(role="tool", content="已保存", metadata={"tool_call_id": "c1"}),
    ]
    _, conv = to_anthropic_messages(msgs)
    asst = next(m for m in conv if m["role"] == "assistant" and isinstance(m["content"], list))
    # thinking 块必须位于 assistant 消息开头（thinking-first 约束）
    assert asst["content"][0]["type"] == "thinking"
    assert asst["content"][0]["thinking"] == "让我构思一下开头…"
    # signature 必须原样保留（不可改，否则 400）
    assert asst["content"][0]["signature"] == sig
    # thinking 块必须在 tool_use 之前
    types = [b.get("type") for b in asst["content"]]
    assert types.index("thinking") < types.index("tool_use")


def test_anthropic_redacted_thinking_preserved() -> None:
    """S232：redacted_thinking 块（内容不可读）也必须回传。"""
    msgs = [
        Message(role="user", content="分析一下"),
        Message(
            role="assistant",
            content="结论。",
            metadata={
                "tool_calls": [{"name": "search", "arguments": {}, "id": "c1"}],
                "reasoning_blocks": [
                    {"type": "redacted_thinking", "data": "EkQBCgEACgwIvgIQARgCIAE="},
                ],
            },
        ),
        Message(role="tool", content="", metadata={"tool_call_id": "c1"}),
    ]
    _, conv = to_anthropic_messages(msgs)
    asst = next(m for m in conv if m["role"] == "assistant" and isinstance(m["content"], list))
    assert asst["content"][0]["type"] == "redacted_thinking"
    assert asst["content"][0]["data"] == "EkQBCgEACgwIvgIQARgCIAE="


def test_anthropic_parse_content_captures_full_thinking_block() -> None:
    """S232：_parse_content 必须捕获完整 thinking 块（含 signature），

    不只文本——reasoning_blocks 用于回传，signature 不可丢。
    """
    from anyspark.models.anthropic import _parse_content

    content: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": "先想一步", "signature": "SIG123"},
        {"type": "text", "text": "回答"},
        {"type": "tool_use", "id": "c1", "name": "write", "input": {"x": 1}},
    ]
    text, tool_calls, reasoning, reasoning_blocks = _parse_content(content)
    assert text == "回答"
    assert reasoning == "先想一步"
    assert len(reasoning_blocks) == 1
    assert reasoning_blocks[0] == {
        "type": "thinking",
        "thinking": "先想一步",
        "signature": "SIG123",
    }
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "c1"


def test_anthropic_parse_content_redacted_thinking() -> None:
    """S232：redacted_thinking 块也纳入 reasoning_blocks（data 字段）。"""
    from anyspark.models.anthropic import _parse_content

    content: list[dict[str, Any]] = [
        {"type": "redacted_thinking", "data": "REDACTED_X"},
        {"type": "text", "text": "好"},
    ]
    _, _, _, reasoning_blocks = _parse_content(content)
    assert reasoning_blocks == [{"type": "redacted_thinking", "data": "REDACTED_X"}]
