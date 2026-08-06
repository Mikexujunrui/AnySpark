"""
anyspark.server.recorder — 运行记录器（S49：完整运行日志，辅助修 bug + 训练心智模型素材）。

记录 Agent 每轮的完整快照（JSONL 追加）：
```
data/records/<conversation_id>/
├── meta.json      会话元数据（时间/模型/请求参数）
└── events.jsonl   每轮一行：{turn_index, prompt(完整上下文快照), output
                   (text/思维链reasoning/tool_calls), tool_results}
```

用途（主人拍板）：
- **修 bug**：完整可回放——出问题时的上下文/工具调用/思维链一目了然
- **训练心智模型**：上下文 + 思维链是行为学习的第一手素材
- **复盘**：看模型为什么做某决定（思维链保留但**不注入上下文**——推理过程
  不是输出，注入会污染上下文改变行为；是否注入看场景，默认不注入）

安全：记录在 data/records/（gitignored）；内容可能含正文——仅本机。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

RECORDS_ROOT = Path(__file__).resolve().parents[5] / "data" / "records"


class RunRecorder:
    """会话运行记录器（线程安全 JSONL 追加）。"""

    def __init__(self, root: Path = RECORDS_ROOT) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def session_dir(self, conv_id: str) -> Path:
        d = self.root / conv_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_meta(self, conv_id: str, meta: dict[str, Any]) -> Path:
        f = self.session_dir(conv_id) / "meta.json"
        with self._lock:
            f.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return f

    def append(self, conv_id: str, event: dict[str, Any]) -> Path:
        """追加一条事件（JSONL 行）。"""
        f = self.session_dir(conv_id) / "events.jsonl"
        with self._lock, f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return f

    def attach(self, agent: Any, conv_id: str, meta: dict[str, Any]) -> None:
        """订阅 Agent 的 record 事件：写 meta + 每轮事件追加 JSONL。"""
        self.write_meta(conv_id, meta)

        def _on_record(e: Any) -> None:
            payload = dict(e.payload)
            payload["ts"] = _now_iso()
            self.append(conv_id, payload)

        agent.events.on("record", _on_record)


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
