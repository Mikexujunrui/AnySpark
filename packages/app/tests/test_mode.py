"""S98 快速模式切换：模式存储 / 任务解析 / 槽位分流 / API 测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.models.mode import (
    DEFAULT_CUSTOM_MAP,
    ModeConfig,
    ModeResolver,
    ModeStore,
    task_to_type,
)
from anyspark.models.registry import ModelConfig, ModelRegistry


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test.db"


def _reg(db: Path) -> ModelRegistry:
    reg = ModelRegistry(db)
    # 注册两个槽位模型：pro（v4-pro）+ flash（v4-flash）
    reg.upsert(
        ModelConfig(
            id="v4-pro",
            name="DeepSeek Pro",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="deepseek-v4-pro",
            thinking="high",
        )
    )
    reg.upsert(
        ModelConfig(
            id="v4-flash",
            name="DeepSeek Flash",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="deepseek-v4-flash",
            thinking="medium",
        )
    )
    return reg


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------


def test_mode_store_defaults() -> None:
    store = ModeStore(_db())
    cfg = store.get()
    assert cfg.mode == "split"  # v3 默认模式
    assert cfg.slot_pro is None and cfg.slot_flash is None  # 未配=回退激活
    assert cfg.custom_map == DEFAULT_CUSTOM_MAP
    store.close()


def test_mode_store_save_validates() -> None:
    store = ModeStore(_db())
    store.save(
        ModeConfig(
            mode="custom",
            slot_pro="v4-pro",
            slot_flash="v4-flash",
            custom_map={"writing": "pro", "planning": "bad", "hack": "pro"},
        )
    )
    cfg = store.get()
    assert cfg.mode == "custom"
    assert cfg.custom_map["writing"] == "pro"
    assert cfg.custom_map["planning"] == "flash"  # 非法值回落默认
    assert "hack" not in cfg.custom_map  # 非任务类型剔除
    # 非法 mode 回落 split
    store.save(ModeConfig(mode="ultra"))
    assert store.get().mode == "split"
    store.close()


def test_task_to_type_mapping() -> None:
    assert task_to_type("writing") == "writing"
    assert task_to_type("workflow") == "writing"  # workflow 复用写作槽
    assert task_to_type("unknown-thing") == "general"


# ---------------------------------------------------------------------------
# 解析（模式 → 槽位 → 模型）
# ---------------------------------------------------------------------------


def test_resolver_quality_all_pro() -> None:
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(ModeConfig(mode="quality", slot_pro="v4-pro", slot_flash="v4-flash"))
    r = ModeResolver(store, reg)
    assert r.resolve("writing").id == "v4-pro"  # type: ignore[union-attr]
    assert r.resolve("research").id == "v4-pro"  # type: ignore[union-attr]


def test_resolver_flash_all_flash() -> None:
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(ModeConfig(mode="flash", slot_pro="v4-pro", slot_flash="v4-flash"))
    r = ModeResolver(store, reg)
    assert r.resolve("writing").id == "v4-flash"  # type: ignore[union-attr]


def test_resolver_split_creative_vs_other() -> None:
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(ModeConfig(mode="split", slot_pro="v4-pro", slot_flash="v4-flash"))
    r = ModeResolver(store, reg)
    assert r.resolve("writing").id == "v4-pro"  # type: ignore[union-attr]  # 创作→贵
    assert r.resolve("editing").id == "v4-pro"  # type: ignore[union-attr]
    assert r.resolve("research").id == "v4-flash"  # type: ignore[union-attr]  # 其他→便宜
    assert r.resolve("extraction").id == "v4-flash"  # type: ignore[union-attr]


def test_resolver_custom_uses_map() -> None:
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(
        ModeConfig(
            mode="custom",
            slot_pro="v4-pro",
            slot_flash="v4-flash",
            custom_map={
                "writing": "pro",
                "planning": "flash",
                "extraction": "flash",
                "editing": "pro",
                "general": "flash",
                "research": "flash",
            },
        )
    )
    r = ModeResolver(store, reg)
    assert r.resolve("writing").id == "v4-pro"  # type: ignore[union-attr]
    assert r.resolve("planning").id == "v4-flash"  # type: ignore[union-attr]


def test_resolver_unconfigured_slots_fallback_none() -> None:
    """槽位未配 → resolve 返回 None（调用方回退激活配置，现有行为不变）。"""
    reg = _reg(_db())
    store = ModeStore(_db())  # 默认无槽位
    r = ModeResolver(store, reg)
    assert r.resolve("writing") is None


def test_resolver_slot_model_missing_fallback_none() -> None:
    """槽位指向不存在的模型 → None（注册表删除后安全回退）。"""
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(ModeConfig(mode="quality", slot_pro="ghost", slot_flash="v4-flash"))
    r = ModeResolver(store, reg)
    assert r.resolve("writing") is None  # 指向的 v4-pro 不存在


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_mode_api_get_defaults() -> None:
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    r = client.get("/api/settings/mode").json()
    assert r["mode"] == "split"
    assert set(r["valid_modes"]) == {"quality", "split", "flash", "custom"}
    assert set(r["task_types"]) == {
        "writing",
        "planning",
        "extraction",
        "editing",
        "general",
        "research",
    }
    assert r["custom_map"]["writing"] == "pro"
    assert isinstance(r["models"], list) and len(r["models"]) >= 1


def test_mode_api_set_and_get() -> None:
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    # 先注册槽位模型
    client.post("/api/models", json={"name": "DeepSeek Pro", "model": "deepseek-v4-pro"})
    client.post("/api/models", json={"name": "DeepSeek Flash", "model": "deepseek-v4-flash"})

    r = client.post(
        "/api/settings/mode",
        json={
            "mode": "custom",
            "slot_pro": "deepseek-v4-pro",
            "slot_flash": "deepseek-v4-flash",
            "custom_map": {
                "writing": "pro",
                "planning": "flash",
                "extraction": "flash",
                "editing": "pro",
                "general": "flash",
                "research": "flash",
            },
        },
    ).json()
    assert r["ok"] is True and r["mode"] == "custom"

    got = client.get("/api/settings/mode").json()
    assert got["slot_pro"] == "deepseek-v4-pro"
    assert got["slot_flash"] == "deepseek-v4-flash"
    assert got["custom_map"]["editing"] == "pro"


def test_mode_api_single_field_switch() -> None:
    """模式按钮只传 mode——槽位保留现值。"""
    from anyspark.server.app import build_app

    client = TestClient(build_app(db_path=_db()))
    client.post("/api/settings/mode", json={"mode": "quality", "slot_pro": "x", "slot_flash": "y"})
    client.post("/api/settings/mode", json={"mode": "flash"})  # 只切模式
    got = client.get("/api/settings/mode").json()
    assert got["mode"] == "flash"
    assert got["slot_pro"] == "x" and got["slot_flash"] == "y"  # 槽位保留


def test_provider_build_for_task_divides() -> None:
    """provider.build_for_task：模式分流生效；未配槽位回退激活配置。"""
    import os

    from anyspark.models.registry import ModelProvider

    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test")
    reg = _reg(_db())
    store = ModeStore(_db())
    store.save(ModeConfig(mode="split", slot_pro="v4-pro", slot_flash="v4-flash"))
    provider = ModelProvider(reg, mode=ModeResolver(store, reg))
    assert provider.build_for_task("writing").model_name == "deepseek-v4-pro"
    assert provider.build_for_task("research").model_name == "deepseek-v4-flash"
    # 未配槽位（默认 store）→ 回退激活
    store2 = ModeStore(_db())
    provider2 = ModelProvider(reg, mode=ModeResolver(store2, reg))
    assert provider2.build_for_task("writing").model_name == "deepseek-v4-flash"  # 激活配置
    # 无 resolver → 始终激活配置
    provider3 = ModelProvider(reg)
    assert provider3.build_for_task("writing").model_name == "deepseek-v4-flash"
