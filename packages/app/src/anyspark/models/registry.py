"""
anyspark.models.registry — 运行时模型配置注册表 + 动态模型 Provider（S47）。

解决"换供应商/换模型/选思考强度"（此前只有 .env 启动时静态配置）：

- ModelConfig：一个模型配置记录（供应商端点/模型名/key/窗口/温度/思考强度），可增删改
- ModelRegistry：SQLite 持久化（表 model_configs，与既有 store 同库）。空库时从
  .env 的 DEEPSEEK_* 播种默认 DeepSeek 配置，保证升级即用、旧行为不变。
- ModelProvider：实现 core Model 协议，**委托给注册表当前激活配置**——
  切换模型（activate）后，所有持有它的组件（Agent/图谱抽取/检测/探索/后台任务）
  即时跟随，无需重启、无需改组件代码（组件只认识 Model 协议）。

模型无关哲学保持：注册表管理的是"DeepSeek 兼容适配器的配置"，配置内容（供应商
端点/模型名）是自然语言数据可增删改，机制（表结构/激活语义/委托/缓存）硬编码。
换非 DeepSeek 兼容的供应商需新适配器（core Model 协议不变，YAGNI 不预建）。
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core import Message, ModelOutput
from anyspark.core.protocol import ToolSpec
from anyspark.models.deepseek import DEFAULT_BASE_URL, DEFAULT_MODEL, DeepSeekModel

DEFAULT_CONTEXT_WINDOW = int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", "65536"))
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7

# 模型配置 SQLite 表
_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_configs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key TEXT,
    context_window INTEGER NOT NULL,
    max_tokens INTEGER NOT NULL,
    temperature REAL NOT NULL,
    thinking TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def slugify(name: str) -> str:
    """显示名 → 稳定 id（小写字母数字连字符；冲突由调用方追加短随机后缀）。"""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


@dataclass
class ModelConfig:
    """一条模型配置记录（供应商端点 + 模型 + 行为参数）。"""

    id: str
    name: str
    base_url: str
    model: str
    api_key: str | None = None  # 缺省用环境变量 DEEPSEEK_API_KEY
    context_window: int = DEFAULT_CONTEXT_WINDOW
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE  # 后台组件默认温度（档位映射用于 chat）
    thinking: str | None = (
        None  # 该模型的默认思考强度（None=模型默认；off/low/medium/high/xhigh/max）
    )
    is_active: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("api_key")  # 列表接口不回传 key（安全；POST 才可写）
        return d

    def resolved_api_key(self) -> str | None:
        return self.api_key or os.getenv("DEEPSEEK_API_KEY")


def default_env_config() -> ModelConfig:
    """从 .env 的 DEEPSEEK_* 播种的默认配置（升级即用、旧行为不变）。"""
    return ModelConfig(
        id="default",
        name=f"DeepSeek（{DEFAULT_MODEL}）",
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        is_active=True,
    )


class ModelRegistry:
    """模型配置的 SQLite 持久化注册表（单连接 + 锁，与既有 store 一致）。

    语义：
    - 至少保留一条配置（删除时保底）；删除激活配置自动回落第一条
    - 激活（activate）切换当前默认——仅一个 is_active
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        self._lock = threading.Lock()
        # 单连接（:memory: 库下每连接独立会丢表，必须持有单连接）
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            # 空库播种：从 .env 建默认 DeepSeek（旧版本升上来直接可用）
            row = self._conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()
            if row[0] == 0:
                self._insert(self._conn, default_env_config())
            self._conn.commit()

    @staticmethod
    def _insert(conn: sqlite3.Connection, cfg: ModelConfig) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO model_configs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cfg.id,
                cfg.name,
                cfg.base_url,
                cfg.model,
                cfg.api_key,
                cfg.context_window,
                cfg.max_tokens,
                cfg.temperature,
                cfg.thinking,
                1 if cfg.is_active else 0,
                cfg.created_at,
                cfg.updated_at,
            ),
        )

    def _row_to_cfg(self, row: sqlite3.Row) -> ModelConfig:
        return ModelConfig(
            id=row["id"],
            name=row["name"],
            base_url=row["base_url"],
            model=row["model"],
            api_key=row["api_key"],
            context_window=row["context_window"],
            max_tokens=row["max_tokens"],
            temperature=row["temperature"],
            thinking=row["thinking"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list(self) -> list[ModelConfig]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_configs ORDER BY is_active DESC, created_at ASC"
            ).fetchall()
        return [self._row_to_cfg(r) for r in rows]

    def get(self, cfg_id: str) -> ModelConfig | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM model_configs WHERE id=?", (cfg_id,)).fetchone()
        return self._row_to_cfg(row) if row else None

    def active(self) -> ModelConfig:
        with self._lock:
            row = self._conn.execute("SELECT * FROM model_configs WHERE is_active=1").fetchone()
            if row is None:
                row = self._conn.execute("SELECT * FROM model_configs LIMIT 1").fetchone()
        if row is None:
            # 理论不可达（__init__ 已播种）；防御兜底
            cfg = default_env_config()
            with self._lock:
                self._insert(self._conn, cfg)
                self._conn.commit()
            return cfg
        return self._row_to_cfg(row)

    def upsert(self, cfg: ModelConfig) -> ModelConfig:
        """新增或更新（同 id 覆盖）。首条自动激活；激活状态只由 activate 管理。

        thinking 取值合法性在此校验（非法值抛 ValueError）。
        """
        from anyspark.models import validate_thinking

        cfg.thinking = validate_thinking(cfg.thinking)
        cfg.updated_at = _now()
        existing = self.get(cfg.id)
        with self._lock:
            if existing is None:
                cfg.created_at = _now()
                count = self._conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0]
                cfg.is_active = count == 0  # 首条自动激活
            else:
                cfg.is_active = existing.is_active  # 激活只由 activate 切换
            self._insert(self._conn, cfg)
            self._conn.commit()
        return cfg

    def delete(self, cfg_id: str) -> bool:
        """删除配置。保底：至少留一条（最后一条不可删）。删激活自动回落第一条。"""
        with self._lock:
            rows = self._conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()
            if rows[0] <= 1:
                return False
            cur = self._conn.execute("DELETE FROM model_configs WHERE id=?", (cfg_id,))
            if cur.rowcount == 0:
                return False
            # 删除的是激活配置 → 回落第一条（按创建序）
            active = self._conn.execute("SELECT * FROM model_configs WHERE is_active=1").fetchone()
            if active is None:
                first = self._conn.execute(
                    "SELECT * FROM model_configs ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                self._conn.execute(
                    "UPDATE model_configs SET is_active=1 WHERE id=?", (first["id"],)
                )
            self._conn.commit()
        return True

    def activate(self, cfg_id: str) -> ModelConfig | None:
        """切换当前激活配置（其余全部 is_active=0）。不存在返回 None。"""
        with self._lock:
            row = self._conn.execute("SELECT * FROM model_configs WHERE id=?", (cfg_id,)).fetchone()
            if row is None:
                return None
            self._conn.execute("UPDATE model_configs SET is_active=0")
            self._conn.execute("UPDATE model_configs SET is_active=1 WHERE id=?", (cfg_id,))
            self._conn.commit()
            # 返回更新后的快照（切换前 row 的 is_active 还是旧值）
            row = self._conn.execute("SELECT * FROM model_configs WHERE id=?", (cfg_id,)).fetchone()
        return self._row_to_cfg(row)


class ModelProvider:
    """实现 core Model 协议：委托给注册表当前激活配置（运行时切换即时生效）。

    - respond / respond_stream / model_name / context_window 跟随当前激活配置
    - 实例按 (config, temperature, thinking) 组合缓存——切模型/换参数后惰性重建
    - build(): 按激活配置构造 DeepSeekModel（供 chat 请求做档位温度/思考强度覆盖）
    """

    def __init__(
        self,
        registry: ModelRegistry,
        client_factory: Callable[..., DeepSeekModel] = DeepSeekModel,
    ) -> None:
        self._registry = registry
        self._factory = client_factory
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, float, str | None], DeepSeekModel] = {}

    def build(self, temperature: float | None = None, thinking: str | None = None) -> DeepSeekModel:
        """按当前激活配置构造 DeepSeekModel（可覆盖温度/思考强度；None=用配置值）。"""
        cfg = self._registry.active()
        eff_temp = cfg.temperature if temperature is None else temperature
        eff_thinking = cfg.thinking if thinking is None else thinking
        key = (cfg.id, eff_temp, eff_thinking)
        with self._lock:
            inst = self._cache.get(key)
            if inst is None:
                inst = self._factory(
                    base_url=cfg.base_url,
                    api_key=cfg.resolved_api_key(),
                    model=cfg.model,
                    temperature=eff_temp,
                    max_tokens=cfg.max_tokens,
                    context_window=cfg.context_window,
                    thinking=eff_thinking,
                )
                self._cache[key] = inst
            return inst

    @property
    def active_config(self) -> ModelConfig:
        return self._registry.active()

    @property
    def model_name(self) -> str:
        return self.active_config.model

    @property
    def context_window(self) -> int:
        """动态反映当前激活配置的窗口（S26 预算按窗口；切模型后新窗口即时可见）。"""
        return self.active_config.context_window

    @property
    def inner(self) -> ModelProvider:
        """兼容 RetryingModel.inner 解包习惯（getattr(model, "inner", model)）。"""
        return self

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        return self.build().respond(messages, tools)

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        return self.build().respond_stream(messages, tools, on_event)
