"""S47 运行时模型配置：注册表/Provider/思考强度透传/API 端点测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, ClassVar

import httpx2
import pytest
from fastapi.testclient import TestClient

from anyspark.core.types import Message
from anyspark.models.deepseek import DeepSeekModel, _apply_thinking
from anyspark.models.registry import ModelConfig, ModelProvider, ModelRegistry


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test.db"


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


def test_registry_seeds_env_default() -> None:
    """空库自动播种 .env 默认 DeepSeek 配置（升级即用、旧行为不变）。"""
    reg = ModelRegistry(_db())
    cfgs = reg.list()
    assert len(cfgs) == 1
    assert cfgs[0].is_active is True
    assert cfgs[0].model == "deepseek-v4-flash"


def test_registry_syncs_default_from_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """S173：启动同步 .env → default 配置——用户改 .env 的 base_url/model 重启后生效
    （种子只在空库播种一次；否则官方 key 打到旧端点 DashScope → 401）。
    只同步 id=default；界面添加的其他模型不受影响。"""
    import anyspark.models.registry as reg_mod

    db = _db()
    # 播种：默认 DashScope
    reg = reg_mod.ModelRegistry(db)
    assert reg.get("default").base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"  # type: ignore[union-attr]

    # 界面添加一个自定义模型（id != default）
    reg.upsert(
        reg_mod.ModelConfig(
            id="custom",
            name="自定义",
            base_url="http://127.0.0.1:11434/v1",
            model="m",
        )
    )

    # 用户改 .env → 官方 ds（monkeypatch registry 模块命名空间的常量）
    monkeypatch.setattr(reg_mod, "DEFAULT_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(reg_mod, "DEFAULT_MODEL", "deepseek-chat")

    # 重启（重新实例化）→ default 同步为官方，其他模型保留
    reg2 = reg_mod.ModelRegistry(db)
    d = reg2.get("default")
    assert d.base_url == "https://api.deepseek.com"  # type: ignore[union-attr]
    assert d.model == "deepseek-chat"  # type: ignore[union-attr]
    assert reg2.get("custom").base_url == "http://127.0.0.1:11434/v1"  # type: ignore[union-attr]


def test_registry_upsert_crud_and_activate() -> None:
    reg = ModelRegistry(_db())
    # 新增第二条（不自动激活）
    cfg = ModelConfig(
        id="v4-pro",
        name="DeepSeek Pro",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="deepseek-v4-pro",
        thinking="high",
    )
    reg.upsert(cfg)
    assert reg.get("v4-pro") is not None
    assert reg.active().id == "default"  # 首条仍是激活

    # 切换激活
    reg.activate("v4-pro")
    assert reg.active().id == "v4-pro"

    # 更新（保留激活状态）
    cfg2 = ModelConfig(
        id="v4-pro",
        name="DeepSeek Pro 改",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="deepseek-v4-pro",
        thinking="max",
    )
    reg.upsert(cfg2)
    assert reg.get("v4-pro").name == "DeepSeek Pro 改"  # type: ignore[union-attr]
    assert reg.active().id == "v4-pro"  # 更新不夺权


def test_registry_delete_keeps_at_least_one_and_falls_back() -> None:
    reg = ModelRegistry(_db())
    # 最后一条不可删
    assert reg.delete("default") is False
    assert reg.get("default") is not None
    # 新增后删激活 → 回落第一条
    reg.upsert(
        ModelConfig(
            id="other",
            name="Other",
            base_url="https://x.example/v1",
            model="other-model",
        )
    )
    reg.activate("other")
    assert reg.active().id == "other"
    assert reg.delete("other") is True
    assert reg.get("other") is None
    assert reg.active().id == "default"  # 自动回落


def test_registry_rejects_bad_thinking() -> None:
    reg = ModelRegistry(_db())
    with pytest.raises(ValueError):
        reg.upsert(
            ModelConfig(
                id="bad",
                name="Bad",
                base_url="https://x.example/v1",
                model="m",
                thinking="ultra",
            )
        )


# ---------------------------------------------------------------------------
# 思考强度参数映射
# ---------------------------------------------------------------------------


def test_apply_thinking_off_uses_extra_body() -> None:
    """off = 显式关闭思考——双平台参数（S136：DashScope 的 enable_thinking
    + DeepSeek 官方 thinking.type）。"""
    kwargs: dict[str, Any] = {}
    _apply_thinking(kwargs, "off")
    assert kwargs["extra_body"] == {
        "enable_thinking": False,
        "thinking": {"type": "disabled"},
    }
    assert "reasoning_effort" not in kwargs


def test_apply_thinking_level_uses_reasoning_effort() -> None:
    """low/medium/high/xhigh/max = OpenAI 标准参数顶层直传。"""
    for v in ("low", "medium", "high", "xhigh", "max"):
        kwargs: dict[str, Any] = {}
        _apply_thinking(kwargs, v)
        assert kwargs["reasoning_effort"] == v
        assert "extra_body" not in kwargs


def test_apply_thinking_none_passthrough() -> None:
    """None = 不传（模型默认行为，与旧版本完全一致）。"""
    kwargs: dict[str, Any] = {}
    _apply_thinking(kwargs, None)
    assert kwargs == {}


def test_deepseek_model_validate_thinking() -> None:
    with pytest.raises(ValueError):
        DeepSeekModel(api_key="sk-test", thinking="nonsense")


def test_deepseek_model_respond_passes_thinking(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """真实调用时 thinking 参数进入请求（monkeypatch client 验证 kwargs）。"""
    model = DeepSeekModel(api_key="sk-test", thinking="max")

    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(model._client.chat.completions, "create", fake_create)
    out = model.respond([Message(role="user", content="hi")], [])
    assert captured["reasoning_effort"] == "max"
    assert out.text == "你好"


class _FakeChoice:
    def __init__(self) -> None:
        self.finish_reason = "stop"
        self.message = _FakeMessage()


class _FakeMessage:
    content = "你好"
    tool_calls = None


class _FakeResponse:
    choices: ClassVar[list[_FakeChoice]] = [_FakeChoice()]


# ---------------------------------------------------------------------------
# httpx2 流式错误路径（回归：ResponseNotRead 防护）
# ---------------------------------------------------------------------------


class _ChunkedBytes(httpx2.SyncByteStream):
    """模拟分块到达的流式响应体（client.stream 场景）。"""

    def __init__(self, body: bytes) -> None:
        self._chunks = [body[i : i + 15] for i in range(0, len(body), 15)]
        self._i = 0

    def __iter__(self) -> _ChunkedBytes:
        return self

    def __next__(self) -> bytes:
        if self._i >= len(self._chunks):
            raise StopIteration
        c = self._chunks[self._i]
        self._i += 1
        return c

    def close(self) -> None:
        pass


class _StreamErrTransport(httpx2.BaseTransport):
    """模拟 API 返回非 200 的流式响应（错误 body 未 read 场景）。"""

    def __init__(self, status: int = 429, body: str = '{"error":"rate limited"}') -> None:
        self._status = status
        self._body = body.encode()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            self._status,
            headers={"Content-Type": "application/json"},
            stream=_ChunkedBytes(self._body),
            request=request,
        )


def test_anthropic_stream_error_no_response_not_read() -> None:
    """回归：httpx2 流式响应非 200 时错误详情可读（不再抛 ResponseNotRead）。"""
    from anyspark.models.anthropic import AnthropicModel

    model = AnthropicModel(api_key="sk-test", base_url="http://mock.test")
    model._client = httpx2.Client(
        transport=_StreamErrTransport(
            429, '{"error":{"type":"rate_limit_error","message":"slow down"}}'
        ),
        timeout=10,
    )
    with pytest.raises(RuntimeError) as ei:
        model.respond_stream([Message(role="user", content="hi")], [])
    msg = str(ei.value)
    assert "429" in msg
    assert "rate_limit_error" in msg
    assert "ResponseNotRead" not in msg and "streaming response content" not in msg


def test_gemini_stream_error_no_response_not_read() -> None:
    """回归：Gemini 流式非 200 错误路径同样防护。"""
    from anyspark.models.gemini import GeminiModel

    model = GeminiModel(api_key="sk-test", base_url="http://mock.test")
    model._client = httpx2.Client(
        transport=_StreamErrTransport(400, '{"error":{"code":400,"message":"bad"}}'),
        timeout=10,
    )
    with pytest.raises(RuntimeError) as ei:
        model.respond_stream([Message(role="user", content="hi")], [])
    msg = str(ei.value)
    assert "400" in msg
    assert '"message":"bad"' in msg
    assert "ResponseNotRead" not in msg and "streaming response content" not in msg


# ---------------------------------------------------------------------------
# Provider（运行时切换即时生效）
# ---------------------------------------------------------------------------


def test_provider_follows_activation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    reg = ModelRegistry(_db())
    reg.upsert(
        ModelConfig(
            id="pro",
            name="Pro",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="deepseek-v4-pro",
            context_window=131072,
            thinking="high",
        )
    )
    provider = ModelProvider(reg)
    assert provider.model_name == "deepseek-v4-flash"  # 种子激活

    reg.activate("pro")
    assert provider.model_name == "deepseek-v4-pro"  # 即时跟随
    assert provider.context_window == 131072

    inst = provider.build()
    assert inst.model_name == "deepseek-v4-pro"
    assert inst._thinking == "high"  # 配置默认思考强度生效


def test_provider_build_overrides_temperature_and_thinking(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    reg = ModelRegistry(_db())
    provider = ModelProvider(reg)
    base = provider.build()
    assert base._temperature == 0.7  # 配置默认

    low = provider.build(temperature=0.2, thinking="off")
    assert low._temperature == 0.2
    assert low._thinking == "off"
    # 缓存复用：同参不再重建
    assert provider.build(temperature=0.2, thinking="off") is low
    assert provider.build() is base


# ---------------------------------------------------------------------------
# API 端点（build_app 全链路）
# ---------------------------------------------------------------------------


def test_models_api_crud() -> None:
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    # 列表：种子默认激活
    r = client.get("/api/models").json()
    assert r["active_id"] == "default"
    assert len(r["models"]) == 1

    # 新增（slug 由 name 生成）
    r = client.post(
        "/api/models",
        json={
            "name": "DeepSeek V4 Pro",
            "model": "deepseek-v4-pro",
            "thinking": "max",
        },
    ).json()
    assert r["ok"] is True
    assert r["model"]["id"] == "deepseek-v4-pro"
    assert r["active"] is False  # 新增不夺权

    # 切换激活
    r = client.post("/api/models/deepseek-v4-pro/activate").json()
    assert r["ok"] is True and r["active"]["id"] == "deepseek-v4-pro"

    # 删除
    r = client.delete("/api/models/deepseek-v4-pro").json()
    assert r["ok"] is True
    assert client.get("/api/models").json()["active_id"] == "default"  # 回落

    # 最后一条不可删
    assert client.delete("/api/models/default").status_code == 400


def test_models_api_update_preserves_key() -> None:
    """编辑更新：同 id 覆盖可改思考强度/温度/窗口；api_key 留空不冲掉原 key。"""
    from anyspark.server.app import build_app

    db = _db()
    client = TestClient(build_app(db_path=db))
    r = client.post(
        "/api/models",
        json={
            "name": "Custom Key Model",
            "model": "deepseek-v4-pro",
            "api_key": "sk-custom-123",
            "thinking": "medium",
            "temperature": 0.5,
        },
    ).json()
    mid = r["model"]["id"]

    # 更新：改温度/思考强度，不传 api_key（列表接口不回传 key，编辑表单留空=不改）
    r = client.post(
        "/api/models",
        json={
            "id": mid,
            "name": "Custom Key Model",
            "model": "deepseek-v4-pro",
            "thinking": "max",
            "temperature": 0.2,
            "context_window": 131072,
            "max_tokens": 4096,
        },
    ).json()
    assert r["ok"] is True
    upd = r["model"]
    assert upd["thinking"] == "max"
    assert upd["temperature"] == 0.2
    assert upd["context_window"] == 131072
    assert upd["max_tokens"] == 4096
    assert "api_key" not in upd  # 列表/响应不回传 key（安全）

    # 底层注册表 key 未被冲掉
    from anyspark.models.registry import ModelRegistry

    reg = ModelRegistry(db)
    assert reg.get(mid).api_key == "sk-custom-123"  # type: ignore[union-attr]


def test_models_api_rejects_bad_thinking() -> None:
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    r = client.post(
        "/api/models",
        json={"name": "Bad", "model": "m", "thinking": "ultra"},
    )
    assert r.status_code == 400


def test_chat_rejects_unknown_model_id() -> None:
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    r = client.post("/api/chat", json={"message": "写《第1章》50字", "model_id": "nope"})
    assert r.status_code == 400
