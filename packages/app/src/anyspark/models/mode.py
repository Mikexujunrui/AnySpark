"""
anyspark.models.mode — 快速模式切换：任务 → 槽位 → 模型分配（S98）。

背景：老版本（v3）设置左侧有快速模式切换（quality/split/flash/custom）——不同任务
可用不同模型（简单任务用便宜模型、复杂任务用昂贵模型）。当前 V4 前端有按钮但后端
无实现（switchMode 把模式名当模型 id 去 activate，404 被 catch 吞掉）。本模块把
模式语义移植到 V4 模型注册表之上：

- 槽位（slot）：pro（贵模型）/ flash（便宜模型），各指向注册表一条模型配置 id
- 模式 4 种（VALID_MODES，语义沿用 v3）：
  - quality：全部任务 → pro 槽
  - flash：全部任务 → flash 槽
  - split：创作类任务（writing/planning/editing/workflow）→ pro，其余 → flash
  - custom：按任务类型查 custom_map（任务类型 → pro/flash）
- 任务类型 6 类（TASK_TYPES）：writing/planning/extraction/editing/general/research
- 槽位未配（NULL）/ 指向的模型不存在 → resolve 返回 None，调用方回退激活配置
  （现有行为不变，向后兼容——用户配了槽位才真正分流）

模型无关哲学保持：模式/槽位/映射是自然语言数据可增删改；解析逻辑（表结构/
分流规则）硬编码。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.db import connect as sqlite_connect

VALID_MODES = ("quality", "split", "flash", "custom")

TASK_TYPES = ("writing", "planning", "extraction", "editing", "general", "research")

# split 模式的创作类任务（v3 config.llm.creative_tasks 默认值）
CREATIVE_TASKS = ("writing", "planning", "editing", "workflow")

# 任务标签 → 任务类型（v3 settings._TASK_TO_TYPE；workflow 复用 writing 槽）
_TASK_TO_TYPE = {
    "writing": "writing",
    "planning": "planning",
    "extraction": "extraction",
    "editing": "editing",
    "general": "general",
    "research": "research",
    "workflow": "writing",
}

# custom 模式的默认任务类型 → 槽位映射（v3 GenerationSettings.custom_map 默认）
DEFAULT_CUSTOM_MAP = {
    "writing": "pro",
    "planning": "flash",
    "extraction": "flash",
    "editing": "pro",
    "general": "flash",
    "research": "flash",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mode_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'split',
    slot_pro TEXT,
    slot_flash TEXT,
    custom_map TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def task_to_type(task: str) -> str:
    """任务标签 → 任务类型（未知任务归 general）。"""
    return _TASK_TO_TYPE.get(task, "general")


@dataclass
class ModeConfig:
    """当前模式 + 槽位分配（slot 存注册表模型配置 id；None=未配，回退激活）。"""

    mode: str = "split"
    slot_pro: str | None = None
    slot_flash: str | None = None
    custom_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CUSTOM_MAP))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "slot_pro": self.slot_pro,
            "slot_flash": self.slot_flash,
            "custom_map": dict(self.custom_map),
            "valid_modes": list(VALID_MODES),
            "task_types": list(TASK_TYPES),
        }


class ModeStore:
    """模式配置的 SQLite 持久化（单行 id=1；与 models 注册表同库）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite_connect(self._db)
        with self._lock:
            self._conn.execute(_SCHEMA)
            row = self._conn.execute("SELECT COUNT(*) FROM mode_config").fetchone()
            if row[0] == 0:
                cfg = ModeConfig()
                self._conn.execute(
                    "INSERT INTO mode_config "
                    "(id, mode, slot_pro, slot_flash, custom_map, updated_at) "
                    "VALUES (1,?,?,?,?,?)",
                    (cfg.mode, cfg.slot_pro, cfg.slot_flash, json.dumps(cfg.custom_map), _now()),
                )
                self._conn.commit()

    def get(self) -> ModeConfig:
        with self._lock:
            row = self._conn.execute("SELECT * FROM mode_config WHERE id=1").fetchone()
        if row is None:
            return ModeConfig()  # 理论不可达（__init__ 已播种）
        try:
            custom = json.loads(row["custom_map"]) if row["custom_map"] else {}
        except (ValueError, TypeError):
            custom = {}
        return ModeConfig(
            mode=row["mode"] if row["mode"] in VALID_MODES else "split",
            slot_pro=row["slot_pro"],
            slot_flash=row["slot_flash"],
            custom_map={t: custom.get(t, DEFAULT_CUSTOM_MAP.get(t, "flash")) for t in TASK_TYPES},
        )

    def save(self, cfg: ModeConfig) -> ModeConfig:
        """保存（校验 mode 合法；custom_map 只取合法任务类型/槽位值）。"""
        if cfg.mode not in VALID_MODES:
            cfg.mode = "split"
        clean: dict[str, str] = {}
        for t in TASK_TYPES:
            v = cfg.custom_map.get(t)
            clean[t] = v if v in ("pro", "flash") else DEFAULT_CUSTOM_MAP.get(t, "flash")
        cfg.custom_map = clean
        with self._lock:
            self._conn.execute(
                "UPDATE mode_config "
                "SET mode=?, slot_pro=?, slot_flash=?, custom_map=?, updated_at=? WHERE id=1",
                (cfg.mode, cfg.slot_pro, cfg.slot_flash, json.dumps(clean), _now()),
            )
            self._conn.commit()
        return cfg

    def close(self) -> None:
        from contextlib import suppress

        with suppress(Exception):
            self._conn.close()


class ModeResolver:
    """任务 → 槽位模型配置（模式分流；槽位未配/模型不存在 → None 回退激活配置）。"""

    def __init__(self, store: ModeStore, registry: Any) -> None:
        self._store = store
        self._registry = registry  # ModelRegistry（避免循环 import，鸭子类型）

    def slot_model(self, slot_name: str) -> Any | None:
        """按槽位名取注册表模型配置；未配/不存在 → None。"""
        if slot_name not in ("pro", "flash"):
            return None
        cfg = self._store.get()
        cfg_id = cfg.slot_pro if slot_name == "pro" else cfg.slot_flash
        if not cfg_id:
            return None
        return self._registry.get(cfg_id)

    def resolve(self, task: str) -> Any | None:
        """按当前模式 + 任务解析槽位模型配置；无法分流 → None（调用方回退激活）。"""
        cfg = self._store.get()
        mode = cfg.mode
        if mode == "quality":
            slot = "pro"
        elif mode == "flash":
            slot = "flash"
        elif mode == "split":
            slot = "pro" if task in CREATIVE_TASKS else "flash"
        elif mode == "custom":
            slot = cfg.custom_map.get(task_to_type(task), "flash")
        else:
            slot = "flash"
        return self.slot_model(slot)
