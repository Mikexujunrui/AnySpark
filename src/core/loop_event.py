"""SSE loop event — the unit of communication between the agent loop and
its consumers (frontend SSE, headless runner, CLI).

Extracted from ``agent_loop.py`` so domain flows (``core/flows``) can emit
events without importing the loop module (which would create a cycle).
"""

import json
from dataclasses import dataclass, field


@dataclass
class LoopEvent:
    type: str
    data: dict = field(default_factory=dict)

    def to_sse(self) -> dict:
        return {"event": self.type, "data": json.dumps(self.data, ensure_ascii=False)}
