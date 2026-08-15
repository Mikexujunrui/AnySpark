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
from anyspark.core.db import connect as sqlite_connect
from anyspark.core.protocol import ToolSpec
from anyspark.models.deepseek import DEFAULT_BASE_URL, DEFAULT_MODEL, DeepSeekModel

DEFAULT_CONTEXT_WINDOW = int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", "65536"))
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7

# 兼容协议（S131 多协议扩展）：协议名 → 适配器工厂（见 _PROTOCOL_FACTORIES）
# - openai：OpenAI Chat Completions（绝大多数厂商 + 本地 Ollama/LM Studio/vLLM/llama.cpp）
# - anthropic：Anthropic Messages（Claude 直连/中转）
# - gemini：Google Generative AI（Gemini 直连）
# - responses：OpenAI Responses（GPT-5 系新 API）
PROTOCOLS: tuple[str, ...] = ("openai", "anthropic", "gemini", "responses")


# 模型配置 SQLite 表（S131：protocol 列加在末尾——旧库 ALTER ADD COLUMN 也追加到末尾，
# 新旧库列顺序一致，_insert 位置参数不受影响）
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
    updated_at TEXT NOT NULL,
    protocol TEXT NOT NULL DEFAULT 'openai'
);
"""

# 协议 → 适配器工厂（统一构造签名：base_url/api_key/model/temperature/max_tokens/
# context_window/thinking——DeepSeekModel 兼容该签名，新增适配器同款）
from anyspark.models.anthropic import AnthropicModel  # noqa: E402
from anyspark.models.gemini import GeminiModel  # noqa: E402
from anyspark.models.responses import ResponsesModel  # noqa: E402

_PROTOCOL_FACTORIES: dict[str, type] = {
    "openai": DeepSeekModel,
    "anthropic": AnthropicModel,
    "gemini": GeminiModel,
    "responses": ResponsesModel,
}


def validate_protocol(protocol: str | None) -> str:
    """校验协议取值；非法值抛 ValueError（配置错误应尽早暴露）。"""
    if not protocol:
        return "openai"
    v = str(protocol).strip().lower()
    if v not in PROTOCOLS:
        raise ValueError(f"非法协议 {protocol!r}：可选 {PROTOCOLS}")
    return v


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
    protocol: str = "openai"  # S131：兼容协议 openai/anthropic/gemini/responses
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
    """从 .env 的 DEEPSEEK_* 播种的默认配置（升级即用、旧行为不变）。

    S178：实时 os.getenv（非模块级常量）——load_dotenv 在 build_app 里（import 后），
    模块级 DEFAULT_BASE_URL/MODEL/CONTEXT_WINDOW 在 import 时已求值为旧 env，
    .env 改后不同步。实时读保证 .env 生效。"""
    import os

    return ModelConfig(
        id="default",
        name=f"DeepSeek（{os.getenv('DEEPSEEK_MODEL', DEFAULT_MODEL)}）",
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
        context_window=int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", str(DEFAULT_CONTEXT_WINDOW))),
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
        # S79：连接配置收敛到 anyspark.core.db.connect（WAL/timeout 一处定义）
        self._conn = sqlite_connect(self._db)
        with self._lock:
            self._conn.execute(_SCHEMA)
            # S131：旧库迁移——model_configs 缺 protocol 列 → ALTER 加列（默认 openai，
            # 旧配置全部按 OpenAI 兼容协议继续工作，行为零变化）
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(model_configs)")]
            if "protocol" not in cols:
                self._conn.execute(
                    "ALTER TABLE model_configs ADD COLUMN protocol TEXT NOT NULL DEFAULT 'openai'"
                )
            # 空库播种：从 .env 建默认 DeepSeek（旧版本升上来直接可用）
            row = self._conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()
            if row[0] == 0:
                seed = default_env_config()
                now = _now()
                # created == updated = “从未被界面修改”标记（S189：_sync_default_from_env
                # 据此决定 .env 是否仍有权覆盖；两次独立 _now() 调用有微秒差，必须统一）
                seed.created_at = now
                seed.updated_at = now
                self._insert(self._conn, seed)
            self._conn.commit()
        # S173：启动同步 .env → default 配置（播种只发生在空库；库已存在时用户改
        # .env 的 base_url/model 不生效——官方 key 打到旧端点 DashScope → 401）
        self._sync_default_from_env()

    def _sync_default_from_env(self) -> None:
        """S173/S178/S189：.env 的 DEEPSEEK_* 变更同步到库 default 配置。

        种子只在空库播种一次——库已存在时改 .env 重启，库里 default 的 base_url/
        model/context_window 仍是旧值。实时读 env（default_env_config）同步到
        id=default；api_key 走 resolved（库优先 .env 兜底）；界面添加的其他模型不受影响。

        S189 守卫：**界面已在运行时改过 default（updated_at != created_at）时不再同步**
        ——打包版 exe 目录 data/.env 固定了初始值（如阿里云 DashScope），若每次重启
        都强制覆盖，用户在界面配置的模型（如 Anthropic 中转）会被无声打回。
        .env 只是启动种子；界面接管后 .env 不再有优先权（.env.example 已声明
        “之后可在前端运行时增删改，无需改 .env 重启”）。只有 default 从未被界面
        改动过时，.env 才是唯一事实来源。
        """
        env_cfg = default_env_config()
        with self._lock:
            row = self._conn.execute(
                "SELECT base_url, model, context_window, created_at, updated_at"
                " FROM model_configs WHERE id='default'"
            ).fetchone()
            if row is None:
                return
            # 界面改过 default（upsert 刷新 updated_at 而保留 created_at）→ 不覆盖
            if row[4] != row[3]:
                return
            # S178：补 context_window 同步（旧版只同步 base_url/model，长上下文设置丢失）
            if (row[0], row[1], row[2]) != (
                env_cfg.base_url,
                env_cfg.model,
                env_cfg.context_window,
            ):
                self._conn.execute(
                    "UPDATE model_configs SET base_url=?, model=?, context_window=?"
                    " WHERE id='default'",
                    (env_cfg.base_url, env_cfg.model, env_cfg.context_window),
                )
                self._conn.commit()

    @staticmethod
    def _insert(conn: sqlite3.Connection, cfg: ModelConfig) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO model_configs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                cfg.protocol,
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
            protocol=row["protocol"],
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
        cfg.protocol = validate_protocol(cfg.protocol)
        cfg.updated_at = _now()
        existing = self.get(cfg.id)
        with self._lock:
            if existing is None:
                cfg.created_at = _now()
                count = self._conn.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0]
                cfg.is_active = count == 0  # 首条自动激活
            else:
                cfg.is_active = existing.is_active  # 激活只由 activate 切换
                # 编辑保留创建时间（S189：界面改 default 后 created_at 保持播种值、
                # updated_at 更新 → “界面已接管”标记可靠；且语义上编辑不改创建时间）
                cfg.created_at = existing.created_at
                # api_key 不回传给列表接口（to_dict 剔除）——编辑表单留空表示“不改 key”，
                # 此时保留原 key，避免前端编辑其他参数把已有自定义 key 冲掉。
                if cfg.api_key is None:
                    cfg.api_key = existing.api_key
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
    - 实例按 (config, protocol, temperature, thinking) 组合缓存——切模型/换参数后惰性重建
    - build(): 按激活配置构造适配器（供 chat 请求做档位温度/思考强度覆盖）
    """

    def __init__(
        self,
        registry: ModelRegistry,
        client_factory: Callable[..., DeepSeekModel] = DeepSeekModel,
        mode: Any | None = None,
    ) -> None:
        """mode: ModeResolver——按任务分流槽位模型（S98）；None=全部用激活配置。

        client_factory: openai 协议（Chat Completions）的工厂覆盖——测试可注入 fake；
        anthropic/gemini/responses 协议走内置工厂（_PROTOCOL_FACTORIES）。
        """
        self._registry = registry
        self._factory = client_factory
        self._mode = mode
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str, float, str | None, str], Any] = {}

    def build(self, temperature: float | None = None, thinking: str | None = None) -> Any:
        """按当前激活配置构造适配器（可覆盖温度/思考强度；None=用配置值）。"""
        cfg = self._registry.active()
        return self._build_cfg(cfg, temperature, thinking)

    def build_for_task(
        self,
        task: str,
        temperature: float | None = None,
        thinking: str | None = None,
    ) -> Any:
        """S98：按任务解析槽位模型构造（模式分流 quality/split/flash/custom）。

        槽位未配 / 指向的模型不存在 → 回退激活配置（向后兼容，现有行为不变）。
        """
        cfg = self._mode.resolve(task) if self._mode is not None else None
        if cfg is None:
            return self.build(temperature, thinking)
        return self._build_cfg(cfg, temperature, thinking)

    def _build_cfg(
        self,
        cfg: ModelConfig,
        temperature: float | None = None,
        thinking: str | None = None,
    ) -> Any:
        """按给定配置构造适配器（温度/思考覆盖；None=用配置值），同参缓存复用。

        S131：按 cfg.protocol 分发到对应协议工厂——openai 兼容（DeepSeekModel，
        覆盖绝大多数厂商 + 本地）/ anthropic（Claude）/ gemini（Gemini）/ responses（GPT-5 系）。
        缓存 key 含 protocol：同一 id 改协议后立即重建，不串用旧协议实例。
        """
        eff_temp = cfg.temperature if temperature is None else temperature
        eff_thinking = cfg.thinking if thinking is None else thinking
        # S178：缓存 key 含 updated_at——配置变更（upsert 改 base_url/api_key/model/
        # context_window 等）后 updated_at 变 → cache miss 重建，不返回旧实例。
        key = (cfg.id, cfg.protocol, eff_temp, eff_thinking, cfg.updated_at)
        with self._lock:
            inst = self._cache.get(key)
            if inst is None:
                # openai 协议用注入工厂（测试 fake）；其余协议走内置工厂
                factory = (
                    self._factory
                    if cfg.protocol == "openai"
                    else _PROTOCOL_FACTORIES.get(cfg.protocol)
                )
                if factory is None:
                    raise ValueError(f"不支持的协议 {cfg.protocol!r}：可选 {PROTOCOLS}")
                inst = factory(
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
        return self.build().respond(messages, tools)  # type: ignore[no-any-return]

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        return self.build().respond_stream(messages, tools, on_event)  # type: ignore[no-any-return]
